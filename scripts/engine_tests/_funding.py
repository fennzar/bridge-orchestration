"""Layer 4: Bridge wrap flow for EXEC test wallet funding.

Imports from _api and _pool. No dependency on _patterns.
"""
from __future__ import annotations

import os
import subprocess
import time

from _api import (
    API, ANVIL_URL, TK, ATOMIC,
    TEST_WALLET_ADDRESS, TEST_WALLET_PK,
    _cast, _jget, _jpost,
    balance_of,
)

from _pool import ZEPHYR_CLI

__all__ = [
    "ensure_test_wallet_funded",
]

# Native asset name → wrapped token name
_NATIVE_TO_WRAPPED = {
    "ZPH": "wZEPH",
    "ZSD": "wZSD",
    "ZRS": "wZRS",
    "ZYS": "wZYS",
}


def _ensure_test_wallet_has_eth(min_eth: float = 1.0) -> None:
    """Send ETH from deployer to test wallet if balance is low."""
    if not TEST_WALLET_ADDRESS:
        return
    deployer_pk = os.environ.get("DEPLOYER_PRIVATE_KEY", "")
    if not deployer_pk:
        return
    # Check current ETH balance
    stdout, err = _cast([
        "balance", TEST_WALLET_ADDRESS, "--rpc-url", ANVIL_URL,
    ], timeout=10.0)
    if err or not stdout:
        return
    try:
        bal_wei = int(stdout.strip())
        if bal_wei >= int(min_eth * 1e18):
            return  # Already has enough
    except (ValueError, TypeError):
        return
    # Send 10 ETH from deployer
    _cast([
        "send", TEST_WALLET_ADDRESS,
        "--value", "10ether",
        "--private-key", deployer_pk,
        "--rpc-url", ANVIL_URL,
    ], timeout=30.0)


def _bridge_create_address(evm_addr: str) -> tuple[str | None, str | None]:
    """Create bridge wrap account. Returns (zephyr_subaddress, error)."""
    data, err = _jpost(
        f"{API}/bridge/address",
        {"evmAddress": evm_addr},
        timeout=10.0,
    )
    if err:
        return None, err
    addr = (data or {}).get("zephyrAddress") or (data or {}).get("address")
    if not addr:
        return None, f"No address in response: {data}"
    return addr, None


def _bridge_poll_claims(evm_addr: str, expected: int, timeout: float = 180.0) -> tuple[list | None, str | None]:
    """Poll bridge claims until expected count are claimable. Returns (claims, error)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        data, err = _jget(f"{API}/claims/{evm_addr}", timeout=10.0)
        if err:
            time.sleep(5)
            continue
        claims = data if isinstance(data, list) else (data or {}).get("claims", [])
        claimable = [c for c in claims if c.get("status") == "claimable"]
        if len(claimable) >= expected:
            return claimable, None
        time.sleep(5)
    return None, f"Timeout after {timeout}s waiting for {expected} claimable claims"


def _bridge_claim(claim: dict, pk: str) -> tuple[str | None, str | None]:
    """Call claimWithSignature on the token contract. Returns (stdout, error)."""
    token_addr = claim["token"]
    to = claim["to"]
    amount = str(claim["amountWei"])
    zeph_tx_id = claim["zephTxId"]
    tx_hash = zeph_tx_id if zeph_tx_id.startswith("0x") else f"0x{zeph_tx_id}"
    deadline = str(claim["deadline"])
    sig = claim["signature"]
    return _cast([
        "send", token_addr,
        "claimWithSignature(address,uint256,bytes32,uint256,bytes)",
        to, amount, tx_hash, deadline, sig,
        "--private-key", pk, "--rpc-url", ANVIL_URL,
    ], timeout=30.0)


def _cli(*args: str, timeout: float = 30.0) -> tuple[str | None, str | None]:
    """Run a zephyr-cli command. Returns (stdout, error)."""
    try:
        r = subprocess.run(
            [ZEPHYR_CLI, *args],
            capture_output=True, text=True, timeout=timeout,
        )
        if r.returncode != 0:
            return None, (r.stderr.strip() or r.stdout.strip()
                          or f"exit code {r.returncode}")
        return r.stdout.strip(), None
    except subprocess.TimeoutExpired:
        return None, f"zephyr-cli {args[0]} timed out after {timeout}s"
    except Exception as e:
        return None, str(e)


# CLI transfer command per asset type (matches zephyr-cli naming)
_CLI_TRANSFER_CMD: dict[str, str] = {
    "ZPH": "transfer",
    "ZSD": "stable_transfer",
    "ZRS": "reserve_transfer",
    "ZYS": "yield_transfer",
}


def _zephyr_transfer(wallet_name: str, dest_addr: str,
                     amount_atomic: int, asset: str) -> tuple[str | None, str | None]:
    """Send native Zephyr asset to address via zephyr-cli. Returns (output, error).

    Uses the asset-specific CLI transfer command (e.g. stable_transfer for ZSD).
    Amount is converted from atomic (1e12) to float for the CLI.
    """
    cmd = _CLI_TRANSFER_CMD.get(asset)
    if not cmd:
        return None, f"Unknown asset: {asset}"
    amount_human = amount_atomic / ATOMIC
    return _cli(cmd, wallet_name, dest_addr, str(amount_human), timeout=60.0)


def _wait_daemon_ready(timeout: float = 60.0) -> bool:
    """Wait until the Zephyr daemon is synchronized and wallets can respond.

    Stops any active mining first (mining causes persistent "daemon is busy"),
    then polls via zephyr-cli info for synchronized=True.
    """
    _cli("mine", "stop")
    time.sleep(2)

    deadline = time.time() + timeout
    while time.time() < deadline:
        out, err = _cli("info", timeout=10.0)
        if err or not out:
            time.sleep(3)
            continue
        # Parse "synchronized: True/False" from CLI output
        if "synchronized: True" in out:
            return True
        time.sleep(3)
    return False


def ensure_test_wallet_funded(token_name: str, min_amount_atomic: int) -> tuple[int | None, str | None]:
    """Ensure the test wallet has enough wrapped tokens via bridge wrap flow.

    If the test wallet already has >= min_amount_atomic of the token,
    returns immediately. Otherwise, wraps native tokens through the bridge.

    Args:
        token_name: wrapped token name (e.g. "wZSD")
        min_amount_atomic: minimum balance needed (in atomic units, 1e12)

    Returns (current_balance, error).
    """
    if not TEST_WALLET_ADDRESS or not TEST_WALLET_PK:
        return None, "TEST_USER_1_ADDRESS / TEST_USER_1_PK not set in .env"

    token_addr = TK.get(token_name)
    if not token_addr:
        return None, f"Token {token_name} not in config"

    # Ensure test wallet has ETH for gas (claim + swap txns)
    _ensure_test_wallet_has_eth()

    # Check current balance — skip if already funded
    bal, _ = balance_of(token_addr, TEST_WALLET_ADDRESS)
    if bal is not None and bal >= min_amount_atomic:
        return bal, None

    # Derive native asset name from token name
    native_asset = None
    for native, wrapped in _NATIVE_TO_WRAPPED.items():
        if wrapped == token_name:
            native_asset = native
            break
    if not native_asset:
        return None, f"No native asset mapping for {token_name}"

    # Amount to wrap (add 10% buffer over minimum)
    wrap_amount_atomic = int(min_amount_atomic * 1.1)

    # Step 1: Create bridge address for test wallet
    bridge_addr, err = _bridge_create_address(TEST_WALLET_ADDRESS)
    if err or not bridge_addr:
        return None, f"Bridge address creation failed: {err}"

    # Step 2: Stop mining & wait for daemon to become available
    if not _wait_daemon_ready(timeout=60):
        return None, "Daemon not ready (busy/syncing) after 60s"

    # Step 3: Send native tokens from gov wallet to bridge subaddress
    _, err = _zephyr_transfer(
        "gov", bridge_addr,
        wrap_amount_atomic, native_asset,
    )
    if err:
        return None, f"Gov→bridge transfer failed: {err}"

    # Step 3.5: Restart mining so the transfer confirms and bridge watcher detects it
    _cli("mine", "start")
    time.sleep(5)  # Give a few blocks to confirm

    # Step 4: Poll for claimable status
    claims, err = _bridge_poll_claims(
        TEST_WALLET_ADDRESS, expected=1, timeout=180,
    )
    if err or not claims:
        return None, f"Claims not ready: {err or 'no claims'}"

    # Step 5: Claim wrapped tokens on EVM
    for claim in claims:
        _, err = _bridge_claim(claim, TEST_WALLET_PK)
        if err:
            return None, f"Claim failed: {err}"

    # Verify final balance
    time.sleep(2)
    bal, _ = balance_of(token_addr, TEST_WALLET_ADDRESS)
    if bal is not None and bal >= min_amount_atomic:
        return bal, None
    return bal, f"Balance after claim ({bal}) still below minimum ({min_amount_atomic})"
