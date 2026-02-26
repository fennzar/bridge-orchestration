"""ZB-SEED: Liquidity Seeding Verification (8 tests)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from ._helpers import (
    PASS, FAIL, BLOCKED,
    _r, _needs, _jget, _eth_call, _rpc,
    API,
    TK, CTX,
)

ENGINE_ADDRESS = os.environ["ENGINE_ADDRESS"]
ENGINE_WALLET_PORT = 48771
SEL_BALANCE_OF = "0x70a08231"  # balanceOf(address)

ROOT = Path(__file__).resolve().parent.parent.parent


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


# ── Checks ───────────────────────────────────────────────────────────────


def check_seed_001(row, probes):
    """Engine Zephyr wallet is funded with all asset types."""
    b = _needs(row, probes, "zephyr_node")
    if b:
        return b
    result, err = _rpc(
        f"http://127.0.0.1:{ENGINE_WALLET_PORT}/json_rpc",
        "get_balance",
        {"all_assets": True},
    )
    if err:
        return _r(row, BLOCKED, f"Engine wallet not responsive: {err}")
    if not isinstance(result, dict):
        return _r(row, FAIL, f"Unexpected balance response: {type(result).__name__}")
    # Parse balances array: [{asset_type, balance, ...}, ...]
    entries = result.get("balances", [])
    balances = {}
    for entry in entries:
        asset = entry.get("asset_type", "ZPH")
        balances[asset] = int(entry.get("balance", 0))
    zero = [k for k in ("ZPH", "ZSD", "ZRS", "ZYS") if balances.get(k, 0) == 0]
    if zero:
        return _r(row, FAIL, f"Zero balances: {', '.join(zero)}")
    summary = ", ".join(f"{k}={v}" for k, v in balances.items())
    return _r(row, PASS, f"Engine wallet funded: {summary}")


def check_seed_002(row, probes):
    """Bridge API recognises the engine EVM address."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    data, err = _jget(f"{API}/claims/{ENGINE_ADDRESS}")
    if err:
        return _r(row, BLOCKED, f"Bridge API unreachable: {err}")
    if not isinstance(data, (list, dict)):
        return _r(row, FAIL, f"Unexpected response type: {type(data).__name__}")
    claims = data if isinstance(data, list) else data.get("claims", [])
    return _r(row, PASS, f"Bridge recognises engine address ({len(claims)} claims)")


def check_seed_003(row, probes):
    """At least 4 completed claims exist for the engine address."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    data, err = _jget(f"{API}/claims/{ENGINE_ADDRESS}")
    if err:
        return _r(row, BLOCKED, f"Bridge API unreachable: {err}")
    claims = data if isinstance(data, list) else (data or {}).get("claims", [])
    if not isinstance(claims, list):
        return _r(row, FAIL, f"Unexpected claims type: {type(claims).__name__}")
    done = [
        c for c in claims
        if isinstance(c, dict)
        and (c.get("status") or "").lower() in {"claimed", "completed"}
    ]
    if len(done) >= 4:
        return _r(row, PASS, f"{len(done)} completed claims (need >= 4)")
    if claims:
        statuses = [c.get("status", "?") for c in claims if isinstance(c, dict)]
        return _r(row, FAIL, f"Only {len(done)}/4 completed claims; statuses: {statuses}")
    return _r(row, FAIL, "No claims found for engine address")


def check_seed_004(row, probes):
    """Engine holds non-zero balances for all 4 wrapped tokens."""
    b = _needs(row, probes, "anvil")
    if b:
        return b
    results = {}
    for sym in ["wZEPH", "wZSD", "wZRS", "wZYS"]:
        bal, err = _balance_of(TK[sym], ENGINE_ADDRESS)
        if err:
            return _r(row, FAIL, f"{sym} balanceOf error: {err}")
        results[sym] = bal
    zero = [k for k, v in results.items() if v == 0]
    if zero:
        return _r(row, FAIL, f"Zero wrapped balances: {', '.join(zero)}")
    summary = ", ".join(f"{k}={v}" for k, v in results.items())
    return _r(row, PASS, f"Wrapped token balances: {summary}")


def check_seed_005(row, probes):
    """Engine holds non-zero USDC and USDT balances."""
    b = _needs(row, probes, "anvil")
    if b:
        return b
    results = {}
    for sym in ["USDC", "USDT"]:
        bal, err = _balance_of(TK[sym], ENGINE_ADDRESS)
        if err:
            return _r(row, FAIL, f"{sym} balanceOf error: {err}")
        results[sym] = bal
    zero = [k for k, v in results.items() if v == 0]
    if zero:
        return _r(row, FAIL, f"Zero mock-USD balances: {', '.join(zero)}")
    summary = ", ".join(f"{k}={v}" for k, v in results.items())
    return _r(row, PASS, f"Mock-USD balances: {summary}")


def check_seed_006(row, probes):
    """All 5 pools have non-zero liquidity."""
    b = _needs(row, probes, "anvil")
    if b:
        return b
    pool_ids = _load_pool_ids()
    if not pool_ids:
        return _r(row, BLOCKED, "Could not load pool IDs from config")
    state_view = CTX["StateView"]
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
        return _r(row, FAIL, "; ".join(issues))
    return _r(row, PASS, f"All {len(ok_pools)} pools have liquidity: {', '.join(ok_pools)}")


def check_seed_007(row, probes):
    """All pools have non-zero sqrtPriceX96 (initialised with a price)."""
    b = _needs(row, probes, "anvil")
    if b:
        return b
    pool_ids = _load_pool_ids()
    if not pool_ids:
        return _r(row, BLOCKED, "Could not load pool IDs from config")
    state_view = CTX["StateView"]
    sel_get_slot0 = "0xc815641c"
    issues = []
    ok_pools = []
    for name, pid in sorted(pool_ids.items()):
        data = pid.replace("0x", "").zfill(64)
        r, err = _eth_call(state_view, sel_get_slot0 + data)
        if err:
            issues.append(f"{name}: {err}")
            continue
        # getSlot0 returns (sqrtPriceX96, tick, protocolFee, lpFee)
        # sqrtPriceX96 is the first 32 bytes of the response
        if not r or len(r) < 66:  # "0x" + 64 hex chars minimum
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
        return _r(row, FAIL, "; ".join(issues))
    return _r(row, PASS, f"All {len(ok_pools)} pools initialised: {', '.join(ok_pools)}")


def check_seed_008(row, probes):
    """Seed is idempotent -- no excessive duplicate claims."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    data, err = _jget(f"{API}/claims/{ENGINE_ADDRESS}")
    if err:
        return _r(row, BLOCKED, f"Bridge API unreachable: {err}")
    claims = data if isinstance(data, list) else (data or {}).get("claims", [])
    if not isinstance(claims, list):
        return _r(row, FAIL, f"Unexpected claims type: {type(claims).__name__}")
    count = len(claims)
    if count <= 8:
        return _r(row, PASS, f"{count} total claims (<= 8, no excessive duplicates)")
    return _r(row, FAIL, f"{count} claims (> 8, possible duplicate seeding)")


# ── Export ───────────────────────────────────────────────────────────────

CHECKS = {
    "ZB-SEED-001": check_seed_001,
    "ZB-SEED-002": check_seed_002,
    "ZB-SEED-003": check_seed_003,
    "ZB-SEED-004": check_seed_004,
    "ZB-SEED-005": check_seed_005,
    "ZB-SEED-006": check_seed_006,
    "ZB-SEED-007": check_seed_007,
    "ZB-SEED-008": check_seed_008,
}


# ── Standalone runner ────────────────────────────────────────────────────

if __name__ == "__main__":
    """Run SEED checks standalone."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from test_common import _jpost, ANVIL_URL, NODE1_RPC

    # Minimal service probes
    probes = {"anvil": False, "bridge_api": False, "zephyr_node": False}
    try:
        p, e = _jpost(
            ANVIL_URL,
            {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1},
            timeout=3.0,
        )
        probes["anvil"] = e is None and p is not None and p.get("result") is not None
    except Exception:
        pass
    try:
        from test_common import _get, BRIDGE_API_URL
        s, _, _ = _get(f"{BRIDGE_API_URL}/health", timeout=3.0)
        probes["bridge_api"] = s == 200
    except Exception:
        pass
    try:
        from test_common import _rpc as _rpc_tc
        result, err = _rpc_tc(NODE1_RPC, "get_info", timeout=3.0)
        probes["zephyr_node"] = err is None and result is not None
    except Exception:
        pass

    from dataclasses import dataclass

    @dataclass
    class Row:
        test_id: str
        lane: str = "api-contract"
        status: str = "SCOPED-READY"
        priority: str = "P0"

    results = []
    for test_id, fn in sorted(CHECKS.items()):
        row = Row(test_id=test_id)
        result = fn(row, probes)
        results.append(result)
        color = (
            "\033[0;32m" if result.result == "PASS"
            else "\033[0;31m" if result.result == "FAIL"
            else "\033[1;33m"
        )
        print(f"{color}[{result.result}]\033[0m {result.test_id}: {result.detail}")

    from collections import Counter
    counts = Counter(r.result for r in results)
    print(
        f"\nResults: PASS={counts.get('PASS', 0)} "
        f"FAIL={counts.get('FAIL', 0)} "
        f"BLOCKED={counts.get('BLOCKED', 0)}"
    )
    sys.exit(1 if counts.get("FAIL", 0) > 0 else 0)
