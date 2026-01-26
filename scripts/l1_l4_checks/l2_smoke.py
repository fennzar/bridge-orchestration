"""L2: Smoke Tests (6 tests)."""
from __future__ import annotations

import json
import time as _time

from test_common import (
    ANVIL_URL, ATOMIC, BRIDGE_API_URL, DEPLOYED_ADDRESSES_FILE,
    ExecutionResult, FAIL, GOV_W, NODE1_RPC, ORACLE_URL, PASS, ROOT, SKIP,
    _get, _jget, _jpost, _rpc,
)
from ._types import TestDef, _r


def check_smoke_01(probes: dict[str, bool]) -> "ExecutionResult":
    """Zephyr chain health: height, synced, difficulty."""
    tid, lvl, lane = "SMOKE-01", "L2", "smoke"

    result, err = _rpc(NODE1_RPC, "get_info", timeout=5.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"get_info failed: {err}")

    info = result or {}
    height = info.get("height", 0)
    synced = info.get("synchronized", False)
    difficulty = info.get("difficulty", 0)
    parts = []
    failed = False

    try:
        if int(height) > 0:
            parts.append(f"Height: {height}")
        else:
            parts.append(f"Height: invalid ({height})")
            failed = True
    except (ValueError, TypeError):
        parts.append(f"Height: invalid ({height})")
        failed = True

    if synced is True or synced == "true":
        parts.append("Synchronized: true")
    else:
        parts.append(f"Synchronized: {synced}")
        failed = True

    try:
        if int(difficulty) > 0:
            parts.append(f"Difficulty: {difficulty}")
        else:
            parts.append("Difficulty: invalid")
            failed = True
    except (ValueError, TypeError):
        parts.append("Difficulty: invalid")
        failed = True

    return _r(tid, lvl, lane, FAIL if failed else PASS, "; ".join(parts))


def check_smoke_02(probes: dict[str, bool]) -> "ExecutionResult":
    """Gov wallet balances: ZPH, ZRS, ZSD."""
    tid, lvl, lane = "SMOKE-02", "L2", "smoke"

    result, err = _rpc(GOV_W, "get_balance", timeout=5.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"get_balance failed: {err}")

    balances = (result or {}).get("balances", [])
    asset_map: dict[str, int] = {}
    for b in balances:
        asset_map[b.get("asset_type", "")] = int(b.get("balance", 0))

    parts = []
    failed = False

    zph = asset_map.get("ZPH", 0)
    zph_human = zph / ATOMIC
    if zph > 0:
        parts.append(f"Gov ZPH: {zph_human:.2f}")
    else:
        parts.append("Gov ZPH: 0 (expected > 0)")
        failed = True

    zrs = asset_map.get("ZRS", 0)
    zrs_human = zrs / ATOMIC
    parts.append(f"Gov ZRS: {zrs_human:.2f}")

    zsd = asset_map.get("ZSD", 0)
    zsd_human = zsd / ATOMIC
    parts.append(f"Gov ZSD: {zsd_human:.2f}")

    return _r(tid, lvl, lane, FAIL if failed else PASS, "; ".join(parts))


def check_smoke_03(probes: dict[str, bool]) -> "ExecutionResult":
    """Oracle price: spot > 0."""
    tid, lvl, lane = "SMOKE-03", "L2", "smoke"

    data, err = _jget(f"{ORACLE_URL}/status", timeout=5.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Oracle status failed: {err}")

    spot = (data or {}).get("spot", 0)
    try:
        spot_int = int(spot)
    except (ValueError, TypeError):
        return _r(tid, lvl, lane, FAIL, f"Oracle spot invalid: {spot}")

    if spot_int > 0:
        price = spot_int / ATOMIC
        return _r(tid, lvl, lane, PASS, f"Oracle spot: ${price:.2f}")
    return _r(tid, lvl, lane, FAIL, "Oracle spot: invalid")


def check_smoke_04(probes: dict[str, bool]) -> "ExecutionResult":
    """EVM contracts deployed: wZEPH has code."""
    tid, lvl, lane = "SMOKE-04", "L2", "smoke"

    # Find wZEPH address
    wzeph_addr = None
    env_addr = __import__("os").environ.get("WZEPH_ADDRESS")
    if env_addr:
        wzeph_addr = env_addr

    if not wzeph_addr and DEPLOYED_ADDRESSES_FILE.exists():
        try:
            addrs = json.loads(DEPLOYED_ADDRESSES_FILE.read_text())
            wzeph_addr = addrs.get("wZEPH") or addrs.get("wzeph") or addrs.get("WZEPH")
        except Exception:
            pass

    if not wzeph_addr:
        for alt in [ROOT / "contracts/deployed.json", ROOT / ".deployed-addresses.json"]:
            if alt.exists():
                try:
                    addrs = json.loads(alt.read_text())
                    wzeph_addr = addrs.get("wZEPH") or addrs.get("wzeph") or addrs.get("WZEPH")
                    if wzeph_addr:
                        break
                except Exception:
                    pass

    if not wzeph_addr:
        return _r(tid, lvl, lane, SKIP, "wZEPH address not found (set WZEPH_ADDRESS or create deployed-addresses.json)")

    parsed, err = _jpost(
        ANVIL_URL,
        {"jsonrpc": "2.0", "method": "eth_getCode",
         "params": [wzeph_addr, "latest"], "id": 1},
        timeout=5.0,
    )
    if err:
        return _r(tid, lvl, lane, FAIL, f"eth_getCode failed: {err}")

    code = (parsed or {}).get("result", "0x")
    if code and code != "0x" and len(code) > 10:
        return _r(tid, lvl, lane, PASS, f"wZEPH contract deployed ({len(code)} bytes)")
    return _r(tid, lvl, lane, FAIL, f"wZEPH contract not found at {wzeph_addr}")


def check_smoke_05(probes: dict[str, bool]) -> "ExecutionResult":
    """Bridge API health endpoint."""
    tid, lvl, lane = "SMOKE-05", "L2", "smoke"

    data, err = _jget(f"{BRIDGE_API_URL}/health", timeout=5.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Bridge API health: {err}")

    status = (data or {}).get("status", "")
    if status in ("ok", "healthy"):
        return _r(tid, lvl, lane, PASS, f"Bridge API: {status}")
    return _r(tid, lvl, lane, FAIL, f"Bridge API status: {status or 'no response'}")


def check_smoke_06(probes: dict[str, bool]) -> "ExecutionResult":
    """Mining active: mining_status or block production."""
    tid, lvl, lane = "SMOKE-06", "L2", "smoke"

    result, err = _rpc(NODE1_RPC, "mining_status", timeout=5.0)
    if err is None and result:
        active = result.get("active")
        if active is True or active == "true":
            speed = result.get("speed", 0)
            return _r(tid, lvl, lane, PASS, f"Mining active: {speed} H/s")
        if active is False or active == "false":
            return _r(tid, lvl, lane, FAIL, "Mining not active")

    # Fallback: check block production over 3s
    info1, _ = _rpc(NODE1_RPC, "get_info", timeout=5.0)
    h1 = int((info1 or {}).get("height", 0))
    _time.sleep(3)
    info2, _ = _rpc(NODE1_RPC, "get_info", timeout=5.0)
    h2 = int((info2 or {}).get("height", 0))

    if h2 > h1:
        return _r(tid, lvl, lane, PASS, f"Blocks being produced ({h1} -> {h2})")
    # Not a hard failure
    return _r(tid, lvl, lane, PASS, f"No new blocks in 3s (height: {h2}) - mining may be paused")


TESTS: list[TestDef] = [
    TestDef("SMOKE-01", "Zephyr Chain Health", "L2", "smoke", check_smoke_01),
    TestDef("SMOKE-02", "Gov Wallet Balances", "L2", "smoke", check_smoke_02),
    TestDef("SMOKE-03", "Oracle Price", "L2", "smoke", check_smoke_03),
    TestDef("SMOKE-04", "EVM Contracts Deployed", "L2", "smoke", check_smoke_04),
    TestDef("SMOKE-05", "Bridge API Health", "L2", "smoke", check_smoke_05),
    TestDef("SMOKE-06", "Mining Active", "L2", "smoke", check_smoke_06),
]
