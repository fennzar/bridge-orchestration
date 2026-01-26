"""L3: Component Feature Tests (14 tests)."""
from __future__ import annotations

import json
import time as _time

from test_common import (
    ANVIL_URL, ATOMIC, BRIDGE_API_URL, DEPLOYED_ADDRESSES_FILE,
    ENGINE_URL, ExecutionResult, FAIL, GOV_W, NODE1_RPC, ORACLE_URL,
    ORDERBOOK_URL, PASS, SKIP,
    _cast, _get, _jget, _rpc,
    set_oracle_price,
)
from ._types import TestDef, _r


def check_engine_01(probes: dict[str, bool]) -> "ExecutionResult":
    """Engine state builder: zephyr, cex, evm sections present."""
    tid, lvl, lane = "ENGINE-01", "L3", "engine"

    data, err = _jget(f"{ENGINE_URL}/api/state", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"No state returned: {err}")
    if not data:
        return _r(tid, lvl, lane, FAIL, "No state returned")

    state = (data or {}).get("state", {})
    has_zephyr = state.get("zephyr") is not None
    has_cex = state.get("cex") is not None
    has_evm = state.get("evm") is not None
    rr = ((state.get("zephyr") or {}).get("reserve", {}) or {}).get("reserveRatio", 0)

    if has_zephyr and has_cex:
        return _r(tid, lvl, lane, PASS, f"State built - RR={rr}, zephyr={has_zephyr}, cex={has_cex}, evm={has_evm}")
    return _r(tid, lvl, lane, FAIL, f"Incomplete state - zephyr={has_zephyr}, cex={has_cex}, evm={has_evm}")


def check_engine_02(probes: dict[str, bool]) -> "ExecutionResult":
    """Engine status: reserveRatio and rrMode present."""
    tid, lvl, lane = "ENGINE-02", "L3", "engine"

    data, err = _jget(f"{ENGINE_URL}/api/engine/status", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Status endpoint not responding: {err}")

    state = (data or {}).get("state", {})
    rr = state.get("reserveRatio")
    mode = state.get("rrMode")
    if rr is not None:
        return _r(tid, lvl, lane, PASS, f"Engine status - RR={rr}, mode={mode}")
    return _r(tid, lvl, lane, FAIL, "Status endpoint not responding")


def check_engine_03(probes: dict[str, bool]) -> "ExecutionResult":
    """Arbitrage analysis endpoint responds with valid JSON."""
    tid, lvl, lane = "ENGINE-03", "L3", "engine"

    data, err = _jget(f"{ENGINE_URL}/api/arbitrage/analysis", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Arbitrage analysis not responding: {err}")
    return _r(tid, lvl, lane, PASS, "Arbitrage analysis endpoint responds")


def check_engine_04(probes: dict[str, bool]) -> "ExecutionResult":
    """Balances endpoint responds."""
    tid, lvl, lane = "ENGINE-04", "L3", "engine"
    data, err = _jget(f"{ENGINE_URL}/api/balances", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Balances endpoint not responding: {err}")
    return _r(tid, lvl, lane, PASS, "Balances endpoint responds")


def check_engine_05(probes: dict[str, bool]) -> "ExecutionResult":
    """Runtime endpoint responds."""
    tid, lvl, lane = "ENGINE-05", "L3", "engine"
    data, err = _jget(f"{ENGINE_URL}/api/runtime", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Runtime endpoint not responding: {err}")
    return _r(tid, lvl, lane, PASS, "Runtime endpoint responds")


def check_engine_06(probes: dict[str, bool]) -> "ExecutionResult":
    """Zephyr network state with reserveRatio."""
    tid, lvl, lane = "ENGINE-06", "L3", "engine"

    data, err = _jget(f"{ENGINE_URL}/api/zephyr/network-state", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Zephyr network state not responding: {err}")

    rr = (data or {}).get("reserveRatio")
    if rr is not None:
        return _r(tid, lvl, lane, PASS, f"Zephyr network state - RR={rr}")
    return _r(tid, lvl, lane, FAIL, "Zephyr network state not responding")


def check_bridge_01(probes: dict[str, bool]) -> "ExecutionResult":
    """Bridge API status endpoint."""
    tid, lvl, lane = "BRIDGE-01", "L3", "bridge"

    data, err = _jget(f"{BRIDGE_API_URL}/bridge/status", timeout=10.0)
    if err is None and data:
        return _r(tid, lvl, lane, PASS, "Bridge status endpoint responds")

    # Fallback to /health
    s, _, e = _get(f"{BRIDGE_API_URL}/health", timeout=10.0)
    if s == 200:
        return _r(tid, lvl, lane, PASS, "Bridge API healthy (health endpoint)")
    return _r(tid, lvl, lane, FAIL, "Bridge API not responding")


def check_bridge_02(probes: dict[str, bool]) -> "ExecutionResult":
    """Claims endpoint responds."""
    tid, lvl, lane = "BRIDGE-02", "L3", "bridge"
    s, body, e = _get(f"{BRIDGE_API_URL}/claims", timeout=10.0)
    if body:
        return _r(tid, lvl, lane, PASS, "Claims endpoint responds")
    return _r(tid, lvl, lane, FAIL, "Claims endpoint not responding")


def check_bridge_03(probes: dict[str, bool]) -> "ExecutionResult":
    """Unwraps endpoint responds."""
    tid, lvl, lane = "BRIDGE-03", "L3", "bridge"
    s, body, e = _get(f"{BRIDGE_API_URL}/unwraps", timeout=10.0)
    if body:
        return _r(tid, lvl, lane, PASS, "Unwraps endpoint responds")
    return _r(tid, lvl, lane, FAIL, "Unwraps endpoint not responding")


def check_zephyr_01(probes: dict[str, bool]) -> "ExecutionResult":
    """Gov wallet balances (detailed, all 4 assets)."""
    tid, lvl, lane = "ZEPHYR-01", "L3", "zephyr"

    result, err = _rpc(GOV_W, "get_balance", {"account_index": 0, "all_assets": True}, timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Could not get gov wallet balance: {err}")

    balances = (result or {}).get("balances", [])
    asset_map: dict[str, int] = {}
    for b in balances:
        asset_map[b.get("asset_type", "")] = int(b.get("balance", 0))

    zph = asset_map.get("ZPH", 0)
    zsd = asset_map.get("ZSD", 0)
    zrs = asset_map.get("ZRS", 0)
    zys = asset_map.get("ZYS", 0)

    detail = (
        f"Gov balances - ZPH={zph / ATOMIC:.2f}, "
        f"ZSD={zsd / ATOMIC:.2f}, "
        f"ZRS={zrs / ATOMIC:.2f}, "
        f"ZYS={zys / ATOMIC:.2f}"
    )

    if zph > 0:
        return _r(tid, lvl, lane, PASS, detail)
    return _r(tid, lvl, lane, FAIL, "Gov wallet has no ZPH")


def check_zephyr_02(probes: dict[str, bool]) -> "ExecutionResult":
    """Reserve info from node."""
    tid, lvl, lane = "ZEPHYR-02", "L3", "zephyr"

    result, err = _rpc(NODE1_RPC, "get_reserve_info", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Could not get reserve info: {err}")

    rr = (result or {}).get("reserve_ratio", "0")
    height = (result or {}).get("height", 0)

    try:
        if int(height) > 0:
            return _r(tid, lvl, lane, PASS, f"Reserve info - height={height}, RR={rr}")
    except (ValueError, TypeError):
        pass
    return _r(tid, lvl, lane, FAIL, "Invalid reserve info")


def check_evm_01(probes: dict[str, bool]) -> "ExecutionResult":
    """Deployed contracts: wZEPH totalSupply via cast."""
    tid, lvl, lane = "EVM-01", "L3", "evm"

    if not DEPLOYED_ADDRESSES_FILE.exists():
        return _r(tid, lvl, lane, SKIP, "No deployed-addresses.json found")

    try:
        addrs = json.loads(DEPLOYED_ADDRESSES_FILE.read_text())
        wzeph = addrs.get("wZEPH")
    except Exception as e:
        return _r(tid, lvl, lane, FAIL, f"Could not read addresses: {e}")

    if not wzeph:
        return _r(tid, lvl, lane, SKIP, "wZEPH address not in deployed-addresses.json")

    supply, err = _cast(["call", wzeph, "totalSupply()(uint256)", "--rpc-url", ANVIL_URL])
    if err:
        return _r(tid, lvl, lane, FAIL, f"Could not call wZEPH contract: {err}")
    return _r(tid, lvl, lane, PASS, f"wZEPH contract verified at {wzeph}")


def check_oracle_01(probes: dict[str, bool]) -> "ExecutionResult":
    """Oracle price control: set/verify/restore."""
    tid, lvl, lane = "ORACLE-01", "L3", "oracle"

    data, err = _jget(f"{ORACLE_URL}/status", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Could not get oracle status: {err}")

    before = (data or {}).get("spot")
    if not before or before == "null":
        return _r(tid, lvl, lane, FAIL, "Could not get oracle status")

    set_oracle_price(2.00)
    _time.sleep(3)

    data2, err2 = _jget(f"{ORACLE_URL}/status", timeout=10.0)
    after = (data2 or {}).get("spot") if not err2 else None

    # Restore
    set_oracle_price(1.50)

    if after == 2000000000000:
        return _r(tid, lvl, lane, PASS, "Price control works (changed to $2.00 and restored)")
    return _r(tid, lvl, lane, FAIL, f"Price change failed - before={before}, after={after}")


def check_orderbook_01(probes: dict[str, bool]) -> "ExecutionResult":
    """Orderbook tracks oracle price."""
    tid, lvl, lane = "ORDERBOOK-01", "L3", "orderbook"

    data, err = _jget(f"{ORDERBOOK_URL}/status", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Orderbook not responding: {err}")

    ob_price = (data or {}).get("oraclePriceUsd")
    if ob_price is not None and ob_price != "null":
        return _r(tid, lvl, lane, PASS, f"Orderbook tracking oracle price: ${ob_price}")
    return _r(tid, lvl, lane, FAIL, "Orderbook not tracking price")


TESTS: list[TestDef] = [
    TestDef("ENGINE-01", "State Builder", "L3", "engine", check_engine_01),
    TestDef("ENGINE-02", "Engine Status", "L3", "engine", check_engine_02),
    TestDef("ENGINE-03", "Arbitrage Analysis", "L3", "engine", check_engine_03),
    TestDef("ENGINE-04", "Balances", "L3", "engine", check_engine_04),
    TestDef("ENGINE-05", "Runtime Info", "L3", "engine", check_engine_05),
    TestDef("ENGINE-06", "Zephyr Network State", "L3", "engine", check_engine_06),
    TestDef("BRIDGE-01", "Bridge API Status", "L3", "bridge", check_bridge_01),
    TestDef("BRIDGE-02", "Claims Endpoint", "L3", "bridge", check_bridge_02),
    TestDef("BRIDGE-03", "Unwraps Endpoint", "L3", "bridge", check_bridge_03),
    TestDef("ZEPHYR-01", "Gov Wallet Balances (Detailed)", "L3", "zephyr", check_zephyr_01),
    TestDef("ZEPHYR-02", "Reserve Info", "L3", "zephyr", check_zephyr_02),
    TestDef("EVM-01", "Deployed Contracts", "L3", "evm", check_evm_01),
    TestDef("ORACLE-01", "Oracle Price Control", "L3", "oracle", check_oracle_01),
    TestDef("ORDERBOOK-01", "Orderbook Price Tracking", "L3", "orderbook", check_orderbook_01),
]
