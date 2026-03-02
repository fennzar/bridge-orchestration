"""Seed tier: stack bootstrapping verification (9 tests).

Adapted from L5 SEED checks (l5_checks/seed.py) + L4-SEED-01.
Read-only: verifies seeding results without mutating state.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from test_common import (
    ANVIL_URL, ATOMIC, BRIDGE_API_URL, ExecutionResult,
    FAIL, PASS, SKIP,
    _cast, _eth_call, _jget, _rpc, TK, CTX,
)
from ._types import TestDef, _r

ROOT = Path(__file__).resolve().parent.parent.parent

ENGINE_ADDRESS = os.environ.get("ENGINE_ADDRESS", "")
ENGINE_WALLET_PORT = 48771
SEL_BALANCE_OF = "0x70a08231"


def _balance_of(token_addr: str, account: str):
    """ERC-20 balanceOf via eth_call."""
    acct_pad = account.lower().replace("0x", "").zfill(64)
    r, e = _eth_call(token_addr, SEL_BALANCE_OF + acct_pad)
    if e or r is None:
        return None, e or "No response"
    try:
        return int(r, 16), None
    except (ValueError, TypeError):
        return None, f"Bad balanceOf: {r}"


def _load_pool_ids():
    """Load pool IDs from addresses config."""
    for fname in ["config/addresses.local.json", "config/addresses.json"]:
        p = ROOT / fname
        if p.exists():
            data = json.load(open(p))
            pools = data.get("pools", {})
            return {
                name: info.get("state", {}).get("poolId")
                for name, info in pools.items()
                if info.get("state", {}).get("poolId")
            }
    return None


def _need_engine_addr(test_id: str, lvl: str, lane: str):
    if not ENGINE_ADDRESS:
        return _r(test_id, lvl, lane, SKIP, "ENGINE_ADDRESS not set")
    return None


# ── Checks ───────────────────────────────────────────────────────────


def check_seed_01(probes: dict[str, bool]) -> ExecutionResult:
    """Engine Zephyr wallet is funded with all asset types."""
    tid, lvl, lane = "SEED-01", "seed", "seed"

    result, err = _rpc(
        f"http://127.0.0.1:{ENGINE_WALLET_PORT}/json_rpc",
        "get_balance",
        {"all_assets": True},
    )
    if err:
        return _r(tid, lvl, lane, FAIL, f"Engine wallet not responsive: {err}")
    if not isinstance(result, dict):
        return _r(tid, lvl, lane, FAIL, f"Unexpected balance response: {type(result).__name__}")

    entries = result.get("balances", [])
    balances = {}
    for entry in entries:
        asset = entry.get("asset_type", "ZPH")
        balances[asset] = int(entry.get("balance", 0))
    zero = [k for k in ("ZPH", "ZSD", "ZRS", "ZYS") if balances.get(k, 0) == 0]
    if zero:
        return _r(tid, lvl, lane, FAIL, f"Zero balances: {', '.join(zero)}")
    summary = ", ".join(f"{k}={v}" for k, v in balances.items())
    return _r(tid, lvl, lane, PASS, f"Engine wallet funded: {summary}")


def check_seed_02(probes: dict[str, bool]) -> ExecutionResult:
    """Bridge API recognises the engine EVM address."""
    tid, lvl, lane = "SEED-02", "seed", "seed"
    skip = _need_engine_addr(tid, lvl, lane)
    if skip:
        return skip

    data, err = _jget(f"{BRIDGE_API_URL}/claims/{ENGINE_ADDRESS}")
    if err:
        return _r(tid, lvl, lane, FAIL, f"Bridge API unreachable: {err}")
    if not isinstance(data, (list, dict)):
        return _r(tid, lvl, lane, FAIL, f"Unexpected response type: {type(data).__name__}")
    claims = data if isinstance(data, list) else data.get("claims", [])
    return _r(tid, lvl, lane, PASS, f"Bridge recognises engine address ({len(claims)} claims)")


def check_seed_03(probes: dict[str, bool]) -> ExecutionResult:
    """Engine received minted wrapped tokens (>= 4 assets on-chain)."""
    tid, lvl, lane = "SEED-03", "seed", "seed"
    skip = _need_engine_addr(tid, lvl, lane)
    if skip:
        return skip

    # Verify claims happened by checking on-chain balances (survives DB reset).
    # Wrapped tokens can only reach the engine via claimWithSignature mints,
    # so non-zero balances prove claims were completed.
    tokens = {"wZEPH": TK.get("wZEPH", ""), "wZSD": TK.get("wZSD", ""), "wZRS": TK.get("wZRS", ""), "wZYS": TK.get("wZYS", "")}
    funded: list[str] = []
    for symbol, addr in tokens.items():
        if not addr:
            continue
        bal, err = _balance_of(addr, ENGINE_ADDRESS)
        if err is None and isinstance(bal, int) and bal > 0:
            funded.append(symbol)

    if len(funded) >= 4:
        return _r(tid, lvl, lane, PASS, f"{len(funded)} completed claims (need >= 4)")
    return _r(tid, lvl, lane, FAIL, f"Only {len(funded)}/4 tokens minted to engine; funded={funded}")


def check_seed_04(probes: dict[str, bool]) -> ExecutionResult:
    """Engine holds non-zero balances for all 4 wrapped tokens."""
    tid, lvl, lane = "SEED-04", "seed", "seed"
    skip = _need_engine_addr(tid, lvl, lane)
    if skip:
        return skip

    results = {}
    for sym in ["wZEPH", "wZSD", "wZRS", "wZYS"]:
        addr = TK.get(sym, "")
        if not addr:
            return _r(tid, lvl, lane, FAIL, f"{sym} address not in config")
        bal, err = _balance_of(addr, ENGINE_ADDRESS)
        if err:
            return _r(tid, lvl, lane, FAIL, f"{sym} balanceOf error: {err}")
        results[sym] = bal
    zero = [k for k, v in results.items() if v == 0]
    if zero:
        return _r(tid, lvl, lane, FAIL, f"Zero wrapped balances: {', '.join(zero)}")
    summary = ", ".join(f"{k}={v}" for k, v in results.items())
    return _r(tid, lvl, lane, PASS, f"Wrapped token balances: {summary}")


def check_seed_05(probes: dict[str, bool]) -> ExecutionResult:
    """Engine holds non-zero USDC and USDT balances."""
    tid, lvl, lane = "SEED-05", "seed", "seed"
    skip = _need_engine_addr(tid, lvl, lane)
    if skip:
        return skip

    results = {}
    for sym in ["USDC", "USDT"]:
        addr = TK.get(sym, "")
        if not addr:
            return _r(tid, lvl, lane, FAIL, f"{sym} address not in config")
        bal, err = _balance_of(addr, ENGINE_ADDRESS)
        if err:
            return _r(tid, lvl, lane, FAIL, f"{sym} balanceOf error: {err}")
        results[sym] = bal
    zero = [k for k, v in results.items() if v == 0]
    if zero:
        return _r(tid, lvl, lane, FAIL, f"Zero mock-USD balances: {', '.join(zero)}")
    summary = ", ".join(f"{k}={v}" for k, v in results.items())
    return _r(tid, lvl, lane, PASS, f"Mock-USD balances: {summary}")


def check_seed_06(probes: dict[str, bool]) -> ExecutionResult:
    """All 5 pools have non-zero liquidity."""
    tid, lvl, lane = "SEED-06", "seed", "seed"

    pool_ids = _load_pool_ids()
    if not pool_ids:
        return _r(tid, lvl, lane, FAIL, "Could not load pool IDs from config")
    state_view = CTX.get("StateView", "")
    if not state_view:
        return _r(tid, lvl, lane, SKIP, "StateView address not in config")

    sel_get_liquidity = "0xfa6793d5"
    issues = []
    ok_pools = []
    for name, pid in sorted(pool_ids.items()):
        data = pid.replace("0x", "").zfill(64)
        r, err = _eth_call(state_view, sel_get_liquidity + data)
        if err or r is None:
            issues.append(f"{name}: {err or 'No response'}")
            continue
        try:
            liq = int(r, 16)
        except (ValueError, TypeError):
            issues.append(f"{name}: bad response {r}")
            continue
        if liq == 0:
            issues.append(f"{name}: liquidity=0")
        else:
            ok_pools.append(name)
    if issues:
        return _r(tid, lvl, lane, FAIL, "; ".join(issues))
    return _r(tid, lvl, lane, PASS, f"All {len(ok_pools)} pools have liquidity: {', '.join(ok_pools)}")


def check_seed_07(probes: dict[str, bool]) -> ExecutionResult:
    """All pools have non-zero sqrtPriceX96 (initialised with a price)."""
    tid, lvl, lane = "SEED-07", "seed", "seed"

    pool_ids = _load_pool_ids()
    if not pool_ids:
        return _r(tid, lvl, lane, FAIL, "Could not load pool IDs from config")
    state_view = CTX.get("StateView", "")
    if not state_view:
        return _r(tid, lvl, lane, SKIP, "StateView address not in config")

    sel_get_slot0 = "0xc815641c"
    issues = []
    ok_pools = []
    for name, pid in sorted(pool_ids.items()):
        data = pid.replace("0x", "").zfill(64)
        r, err = _eth_call(state_view, sel_get_slot0 + data)
        if err:
            issues.append(f"{name}: {err}")
            continue
        if not r or len(r) < 66:
            issues.append(f"{name}: empty slot0 response")
            continue
        try:
            sqrt_price = int(r[2:66], 16)
        except (ValueError, TypeError):
            issues.append(f"{name}: bad slot0 response")
            continue
        if sqrt_price == 0:
            issues.append(f"{name}: sqrtPriceX96=0")
        else:
            ok_pools.append(name)
    if issues:
        return _r(tid, lvl, lane, FAIL, "; ".join(issues))
    return _r(tid, lvl, lane, PASS, f"All {len(ok_pools)} pools initialised: {', '.join(ok_pools)}")


def check_seed_08(probes: dict[str, bool]) -> ExecutionResult:
    """Seed is idempotent -- no excessive duplicate claims."""
    tid, lvl, lane = "SEED-08", "seed", "seed"
    skip = _need_engine_addr(tid, lvl, lane)
    if skip:
        return skip

    data, err = _jget(f"{BRIDGE_API_URL}/claims/{ENGINE_ADDRESS}")
    if err:
        return _r(tid, lvl, lane, FAIL, f"Bridge API unreachable: {err}")
    claims = data if isinstance(data, list) else (data or {}).get("claims", [])
    if not isinstance(claims, list):
        return _r(tid, lvl, lane, FAIL, f"Unexpected claims type: {type(claims).__name__}")
    count = len(claims)
    if count <= 8:
        return _r(tid, lvl, lane, PASS, f"{count} total claims (<= 8, no excessive duplicates)")
    return _r(tid, lvl, lane, FAIL, f"{count} claims (> 8, possible duplicate seeding)")


def check_seed_09(probes: dict[str, bool]) -> ExecutionResult:
    """Verify seeding results: pools have liquidity, engine has inventory."""
    tid, lvl, lane = "SEED-09", "seed", "seed"
    skip = _need_engine_addr(tid, lvl, lane)
    if skip:
        return skip

    orch_dir = os.environ.get("ORCHESTRATION_PATH", "")
    addr_file = os.path.join(orch_dir, "config", "addresses.json") if orch_dir else ""
    if not addr_file or not os.path.exists(addr_file):
        return _r(tid, lvl, lane, SKIP, "addresses.json not found")

    addrs = json.loads(open(addr_file).read())
    rpc_url = ANVIL_URL
    tokens = addrs.get("tokens", {})
    details = []
    has_inventory = True

    for symbol in ("wZEPH", "wZSD", "wZRS", "wZYS"):
        token_info = tokens.get(symbol, {})
        token_addr = token_info.get("address", "")
        if not token_addr:
            continue
        stdout, err = _cast([
            "call", token_addr, "balanceOf(address)(uint256)",
            ENGINE_ADDRESS, "--rpc-url", rpc_url,
        ])
        if err or not stdout:
            has_inventory = False
            details.append(f"{symbol}=ERR")
            continue
        try:
            bal = int(stdout.strip().split()[0])
        except (ValueError, IndexError):
            bal = 0
        human = bal / ATOMIC
        details.append(f"{symbol}={human:.0f}")
        if bal == 0:
            has_inventory = False

    posm = addrs.get("contracts", {}).get("positionManager", "")
    lp_count = 0
    if posm:
        stdout, err = _cast([
            "call", posm, "balanceOf(address)(uint256)",
            ENGINE_ADDRESS, "--rpc-url", rpc_url,
        ])
        if not err and stdout:
            try:
                lp_count = int(stdout.strip().split()[0])
            except (ValueError, IndexError):
                lp_count = 0

    detail_str = ", ".join(details)
    if has_inventory and lp_count >= 4:
        return _r(tid, lvl, lane, PASS, f"Seeding verified: {lp_count} LP positions, inventory=[{detail_str}]")
    if lp_count < 4:
        return _r(tid, lvl, lane, FAIL, f"Only {lp_count} LP positions (expected 4+), inventory=[{detail_str}]")
    return _r(tid, lvl, lane, FAIL, f"Missing inventory: [{detail_str}]")


# ── Test Registry ────────────────────────────────────────────────────

TESTS: list[TestDef] = [
    TestDef("SEED-01", "Engine Zephyr Wallet Funded", "seed", "seed", "seed", check_seed_01),
    TestDef("SEED-02", "Bridge Recognises Engine Address", "seed", "seed", "seed", check_seed_02),
    TestDef("SEED-03", "Completed Claims (>= 4)", "seed", "seed", "seed", check_seed_03),
    TestDef("SEED-04", "Engine Wrapped Token Balances", "seed", "seed", "seed", check_seed_04),
    TestDef("SEED-05", "Engine USD Balances", "seed", "seed", "seed", check_seed_05),
    TestDef("SEED-06", "Pool Liquidity", "seed", "seed", "seed", check_seed_06),
    TestDef("SEED-07", "Pool Prices Initialised", "seed", "seed", "seed", check_seed_07),
    TestDef("SEED-08", "No Excessive Duplicate Claims", "seed", "seed", "seed", check_seed_08),
    TestDef("SEED-09", "LP Positions + Inventory", "seed", "seed", "seed", check_seed_09),
]
