"""Bridge tier — flow tests (5 tests).

These tests move real funds and exercise the core wrap/unwrap pipeline.
CleanupContext should be used when running this tier.
"""
from __future__ import annotations

import os
import time as _time
from pathlib import Path

from test_common import (
    ANVIL_URL, ATOMIC, BRIDGE_API_URL, ExecutionResult,
    FAIL,
    PASS, SKIP,
    _post,
    TK,
)
from ._types import TestDef, _r

# Import seed helpers for bridge flow operations
sys_path = str(Path(__file__).resolve().parent.parent)
import sys as _sys
if sys_path not in _sys.path:
    _sys.path.insert(0, sys_path)

from lib.seed_helpers import (
    _cast as _seed_cast,
    bridge_create_account,
    bridge_poll_claims,
    evm_claim,
    evm_token_balance,
    start_continuous_mining,
    stop_continuous_mining,
    wait_daemon_ready,
    zephyr_balance,
    zephyr_rpc,
    zephyr_transfer,
    GOV_WALLET_PORT,
    log_step,
)


# ── Bridge flow tests ───────────────────────────────────────────────


def check_wallet_01(probes: dict[str, bool]) -> ExecutionResult:
    """Bridge wallet creation: POST /bridge/address returns subaddress."""
    tid, lvl, lane = "WALLET-01", "bridge", "bridge"

    test_addr = os.environ.get("TEST_USER_1_ADDRESS", "")
    if not test_addr:
        return _r(tid, lvl, lane, SKIP, "TEST_USER_1_ADDRESS not set")

    sub_addr, err = bridge_create_account(BRIDGE_API_URL, test_addr)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Bridge account creation failed: {err}")
    if not sub_addr:
        return _r(tid, lvl, lane, FAIL, "No subaddress returned")

    return _r(tid, lvl, lane, PASS, f"Bridge account created, subaddress={sub_addr[:16]}...")


def _fund_eth_if_needed(address: str, min_eth: float = 0.1) -> tuple[bool, str | None]:
    """Ensure EVM address has enough ETH for gas, funding from deployer if needed."""
    stdout, err = _seed_cast(["balance", address, "--rpc-url", ANVIL_URL])
    if err or stdout is None:
        return False, f"Failed to check balance: {err}"
    try:
        bal_wei = int(stdout.strip())
    except (ValueError, TypeError):
        bal_wei = 0
    min_wei = int(min_eth * 1e18)
    if bal_wei >= min_wei:
        return True, None
    # Fund from deployer
    deployer_pk = os.environ.get("DEPLOYER_PRIVATE_KEY", "")
    if not deployer_pk:
        return False, "DEPLOYER_PRIVATE_KEY not set, cannot fund test account"
    _, err = _seed_cast([
        "send", address,
        "--value", "1ether",
        "--private-key", deployer_pk,
        "--rpc-url", ANVIL_URL,
    ])
    if err:
        return False, f"Failed to fund test account: {err}"
    return True, None


def _wrap_flow(
    probes: dict[str, bool],
    test_id: str,
    asset: str,
    token_symbol: str,
    amount: float,
) -> ExecutionResult:
    """Shared wrap flow: create addr -> transfer -> mine -> poll claims -> claim on EVM."""
    lvl, lane = "bridge", "bridge"

    test_addr = os.environ.get("TEST_USER_1_ADDRESS", "")
    test_pk = os.environ.get("TEST_USER_1_PK", "")
    if not test_addr or not test_pk:
        return _r(test_id, lvl, lane, SKIP, "TEST_USER_1_ADDRESS / TEST_USER_1_PK not set")

    token_addr = TK.get(token_symbol, "")
    if not token_addr:
        return _r(test_id, lvl, lane, SKIP, f"{token_symbol} address not found in config")

    # 0a. Verify token contract is deployed
    from test_common import _jpost
    code_resp, code_err = _jpost(
        ANVIL_URL,
        {"jsonrpc": "2.0", "method": "eth_getCode", "params": [token_addr, "latest"], "id": 1},
        timeout=5.0,
    )
    code = (code_resp or {}).get("result", "0x") if not code_err else "0x"
    if not code or code == "0x" or len(code) < 10:
        return _r(test_id, lvl, lane, FAIL,
                  f"{token_symbol} contract not deployed at {token_addr} (run make dev-setup first)")

    # 0b. Ensure test account has ETH for gas
    ok, err = _fund_eth_if_needed(test_addr)
    if not ok:
        return _r(test_id, lvl, lane, FAIL, f"Cannot fund test account with ETH: {err}")

    # 1. Get initial balance
    initial = evm_token_balance(token_addr, test_addr, ANVIL_URL)

    # 2. Create bridge account (idempotent)
    sub_addr, err = bridge_create_account(BRIDGE_API_URL, test_addr)
    if err or not sub_addr:
        return _r(test_id, lvl, lane, FAIL, f"Bridge account creation failed: {err}")

    # 3. Wait for daemon ready, send from gov
    log_step(f"[{test_id}] Waiting for daemon ready...")
    if not wait_daemon_ready(timeout=60):
        return _r(test_id, lvl, lane, FAIL, "Daemon not ready after 60s")

    log_step(f"[{test_id}] Sending {amount} {asset} to bridge subaddress...")
    tx_hash, err = zephyr_transfer(GOV_WALLET_PORT, sub_addr, amount, asset)
    if err:
        return _r(test_id, lvl, lane, FAIL, f"Transfer failed: {err}")

    # 4. Start mining, poll for claimable
    log_step(f"[{test_id}] Mining and waiting for claimable claims...")
    start_continuous_mining()

    claims, err = bridge_poll_claims(BRIDGE_API_URL, test_addr, 1, timeout=180)

    if err or not claims:
        stop_continuous_mining()
        return _r(test_id, lvl, lane, FAIL, f"No claimable claims after 180s: {err}")

    # 5. Claim on EVM
    log_step(f"[{test_id}] Claiming {len(claims)} claim(s) on EVM...")
    for claim in claims:
        _, claim_err = evm_claim(claim, test_pk, ANVIL_URL)
        if claim_err:
            stop_continuous_mining()
            return _r(test_id, lvl, lane, FAIL, f"EVM claim failed: {claim_err}")

    stop_continuous_mining()

    # 6. Verify balance increased
    final = evm_token_balance(token_addr, test_addr, ANVIL_URL)
    if final > initial:
        gained = (final - initial) / ATOMIC
        return _r(test_id, lvl, lane, PASS,
                  f"Wrap complete: {token_symbol} balance {initial / ATOMIC:.4f} -> {final / ATOMIC:.4f} (+{gained:.4f})")
    return _r(test_id, lvl, lane, FAIL,
              f"Balance did not increase: {initial / ATOMIC:.4f} -> {final / ATOMIC:.4f}")


def _unwrap_flow(
    probes: dict[str, bool],
    test_id: str,
    asset: str,
    token_symbol: str,
    amount_atomic: int,
    depends_wrap: str,
) -> ExecutionResult:
    """Shared unwrap flow: burn wToken -> bridge watcher relays -> native arrives."""
    lvl, lane = "bridge", "bridge"

    test_addr = os.environ.get("TEST_USER_1_ADDRESS", "")
    test_pk = os.environ.get("TEST_USER_1_PK", "")
    if not test_addr or not test_pk:
        return _r(test_id, lvl, lane, SKIP, "TEST_USER_1_ADDRESS / TEST_USER_1_PK not set")

    token_addr = TK.get(token_symbol, "")
    if not token_addr:
        return _r(test_id, lvl, lane, SKIP, f"{token_symbol} address not found in config")

    # Ensure test account has ETH for gas
    ok, fund_err = _fund_eth_if_needed(test_addr)
    if not ok:
        return _r(test_id, lvl, lane, FAIL, f"Cannot fund test account with ETH: {fund_err}")

    # Check wToken balance — skip if insufficient
    bal = evm_token_balance(token_addr, test_addr, ANVIL_URL)
    min_balance = amount_atomic
    if bal < min_balance:
        return _r(test_id, lvl, lane, SKIP,
                  f"Insufficient {token_symbol} balance ({bal / ATOMIC:.4f}), needs {depends_wrap} to pass first")

    # 1. Get test wallet Zephyr address for receiving
    TEST_WALLET_PORT = int(os.environ.get("DEVNET_TEST_WALLET_RPC", "48768"))
    addr_result, err = zephyr_rpc(TEST_WALLET_PORT, "get_address", {"account_index": 0})
    if err or not addr_result:
        return _r(test_id, lvl, lane, FAIL, f"Could not get test wallet address: {err}")
    zephyr_dest = addr_result.get("address", "")
    if not zephyr_dest:
        return _r(test_id, lvl, lane, FAIL, "No Zephyr address returned")

    initial_zeph = zephyr_balance(TEST_WALLET_PORT, asset)

    # 2. POST /unwraps/prepare to get payload + nonce
    log_step(f"[{test_id}] Preparing unwrap...")
    import json
    prep_status, prep_body, prep_err = _post(
        f"{BRIDGE_API_URL}/unwraps/prepare",
        {"token": token_addr, "amountWei": str(amount_atomic), "destination": zephyr_dest},
        timeout=15.0,
    )
    if prep_err and prep_status is None:
        return _r(test_id, lvl, lane, FAIL, f"Unwrap prepare failed: {prep_err}")

    try:
        prep_data = json.loads(prep_body or "{}")
    except Exception:
        return _r(test_id, lvl, lane, FAIL, f"Unwrap prepare returned invalid JSON (HTTP {prep_status})")

    payload = prep_data.get("payload", "")
    if not payload:
        return _r(test_id, lvl, lane, FAIL, f"No payload in unwrap prepare response: {prep_data}")

    # Generate random 32-byte nonce (client-side, like the frontend does)
    import secrets
    nonce = "0x" + secrets.token_hex(32)

    # 3. cast send burnWithData(amount, bytes, bytes32)
    log_step(f"[{test_id}] Burning {token_symbol} on EVM...")
    _, err = _seed_cast([
        "send", token_addr,
        "burnWithData(uint256,bytes,bytes32)",
        str(amount_atomic), payload, nonce,
        "--private-key", test_pk,
        "--rpc-url", ANVIL_URL,
    ])
    if err:
        return _r(test_id, lvl, lane, FAIL, f"burnWithData failed: {err}")

    # 4. Start mining, poll test wallet balance
    log_step(f"[{test_id}] Mining and waiting for {asset} to arrive...")
    start_continuous_mining()

    current = initial_zeph
    deadline = _time.time() + 120
    arrived = False
    while _time.time() < deadline:
        current = zephyr_balance(TEST_WALLET_PORT, asset)
        if current > initial_zeph:
            arrived = True
            break
        _time.sleep(5)

    stop_continuous_mining()

    if arrived:
        gained = current - initial_zeph
        return _r(test_id, lvl, lane, PASS,
                  f"Unwrap complete: {asset} balance {initial_zeph:.4f} -> {current:.4f} (+{gained:.4f})")
    return _r(test_id, lvl, lane, FAIL,
              f"{asset} balance did not increase after 120s (still {current:.4f})")


def check_wrap_01(probes: dict[str, bool]) -> ExecutionResult:
    """Full wrap flow: ZEPH -> wZEPH (create addr, transfer, mine, claim)."""
    return _wrap_flow(probes, "WRAP-01", "ZPH", "wZEPH", 100.0)


def check_unwrap_01(probes: dict[str, bool]) -> ExecutionResult:
    """Full unwrap flow: wZEPH -> ZEPH (burn, watcher relays, native arrives)."""
    return _unwrap_flow(probes, "UNWRAP-01", "ZPH", "wZEPH", 10_000_000_000_000, "WRAP-01")


def check_wrap_02(probes: dict[str, bool]) -> ExecutionResult:
    """Full wrap flow: ZSD -> wZSD."""
    return _wrap_flow(probes, "WRAP-02", "ZSD", "wZSD", 50.0)


def check_unwrap_02(probes: dict[str, bool]) -> ExecutionResult:
    """Full unwrap flow: wZSD -> ZSD."""
    return _unwrap_flow(probes, "UNWRAP-02", "ZSD", "wZSD", 5_000_000_000_000, "WRAP-02")


# ── Test Registry ────────────────────────────────────────────────────

TESTS: list[TestDef] = [
    TestDef("WALLET-01", "Bridge Wallet Creation", "bridge", "bridge", "bridge", check_wallet_01),
    TestDef("WRAP-01", "Wrap ZEPH -> wZEPH", "bridge", "bridge", "bridge", check_wrap_01),
    TestDef("UNWRAP-01", "Unwrap wZEPH -> ZEPH", "bridge", "bridge", "bridge", check_unwrap_01,
            depends_on=("WRAP-01",)),
    TestDef("WRAP-02", "Wrap ZSD -> wZSD", "bridge", "bridge", "bridge", check_wrap_02),
    TestDef("UNWRAP-02", "Unwrap wZSD -> ZSD", "bridge", "bridge", "bridge", check_unwrap_02,
            depends_on=("WRAP-02",)),
]
