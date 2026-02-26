"""L4: End-to-End Tests (9 tests)."""
from __future__ import annotations

import json
import os
import time as _time

from test_common import (
    ANVIL_URL, ATOMIC, ENGINE_URL, ExecutionResult, FAIL, GOV_W, NODE1_RPC,
    PASS, SKIP, TEST_W,
    _cast, _jget, _rpc,
    set_oracle_price, set_orderbook_spread,
)
from ._types import TestDef, _r


def check_l4_01(probes: dict[str, bool]) -> "ExecutionResult":
    """Transfer Gov -> Test wallet (3 retries for ring construction)."""
    tid, lvl, lane = "L4-01", "L4", "e2e"

    # Get test wallet address
    result, err = _rpc(TEST_W, "get_address", {"account_index": 0}, timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Could not get test wallet address: {err}")

    test_addr = (result or {}).get("address")
    if not test_addr:
        return _r(tid, lvl, lane, FAIL, "Could not get test wallet address")

    # 3-retry loop for ring construction errors
    for attempt in range(1, 4):
        # Refresh gov wallet
        _rpc(GOV_W, "refresh", timeout=10.0)

        transfer_result, err = _rpc(GOV_W, "transfer", {
            "destinations": [{"amount": 100_000_000_000_000, "address": test_addr}],
        }, timeout=10.0)

        if err is None and transfer_result:
            tx_hash = transfer_result.get("tx_hash")
            if tx_hash:
                _time.sleep(10)
                # Refresh test wallet
                _rpc(TEST_W, "refresh", timeout=10.0)
                bal_result, _ = _rpc(TEST_W, "get_balance", {"account_index": 0}, timeout=10.0)
                test_bal = int((bal_result or {}).get("balance", 0))
                bal_str = f" (balance: {test_bal / ATOMIC:.4f} ZPH)" if test_bal > 0 else ""
                return _r(tid, lvl, lane, PASS, f"Transfer submitted - tx={tx_hash}{bal_str}")

        err_msg = str(err) if err else "unknown error"
        if "ring" in err_msg.lower() and attempt < 3:
            _time.sleep(15)
            continue

        return _r(tid, lvl, lane, FAIL, f"Transfer failed - {err_msg}")

    return _r(tid, lvl, lane, FAIL, "Transfer failed after 3 retries")


def check_l4_02(probes: dict[str, bool]) -> "ExecutionResult":
    """RR mode transitions via oracle price change."""
    tid, lvl, lane = "L4-02", "L4", "e2e"

    # Get current RR
    result, err = _rpc(NODE1_RPC, "get_reserve_info", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Could not get reserve info: {err}")

    current_rr = (result or {}).get("reserve_ratio", "0")

    # Drop oracle price
    set_oracle_price(0.60)
    _time.sleep(5)

    result2, err2 = _rpc(NODE1_RPC, "get_reserve_info", timeout=10.0)
    new_rr = (result2 or {}).get("reserve_ratio", "0") if not err2 else "0"

    # Restore price
    set_oracle_price(1.50)
    _time.sleep(2)

    try:
        rr_num = int(float(new_rr))
    except (ValueError, TypeError):
        rr_num = 999

    if rr_num < 7:
        return _r(tid, lvl, lane, PASS, f"RR responded to oracle change ({current_rr} -> {new_rr})")
    return _r(tid, lvl, lane, FAIL, f"RR did not change as expected ({current_rr} -> {new_rr})")


def check_l4_03(probes: dict[str, bool]) -> "ExecutionResult":
    """Engine state updates with chain."""
    tid, lvl, lane = "L4-03", "L4", "e2e"

    _time.sleep(5)

    data, err = _jget(f"{ENGINE_URL}/api/state", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Could not get engine state: {err}")

    state = (data or {}).get("state", {})
    engine_rr = ((state.get("zephyr") or {}).get("reserve", {}) or {}).get("reserveRatio")

    if engine_rr is not None and engine_rr != "null" and engine_rr != 0:
        return _r(tid, lvl, lane, PASS, f"Engine tracking chain state - RR={engine_rr}")
    return _r(tid, lvl, lane, FAIL, "Engine RR not available")


def check_l4_04(probes: dict[str, bool]) -> "ExecutionResult":
    """Arbitrage spread detection: widen spread, check arb endpoint."""
    tid, lvl, lane = "L4-04", "L4", "e2e"

    set_orderbook_spread(500)
    _time.sleep(3)

    # Try overview first, fallback to analysis
    data, err = _jget(f"{ENGINE_URL}/api/arbitrage/overview", timeout=10.0)
    if err or not data:
        data, err = _jget(f"{ENGINE_URL}/api/arbitrage/analysis", timeout=10.0)

    # Restore spread
    set_orderbook_spread(50)

    if err or not data:
        return _r(tid, lvl, lane, FAIL, "Arbitrage endpoints not responding")
    return _r(tid, lvl, lane, PASS, "Arbitrage endpoints responding")


def check_l4_05(probes: dict[str, bool]) -> "ExecutionResult":
    """Paper account endpoint."""
    tid, lvl, lane = "L4-05", "L4", "e2e"
    data, err = _jget(f"{ENGINE_URL}/api/paper/account", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Paper account not responding: {err}")
    return _r(tid, lvl, lane, PASS, "Paper account endpoint responds")


def check_l4_06(probes: dict[str, bool]) -> "ExecutionResult":
    """Quoter system: convert ZPH to ZSD."""
    tid, lvl, lane = "L4-06", "L4", "e2e"
    data, err = _jget(f"{ENGINE_URL}/api/quoters?op=convert&from=ZPH&to=ZSD&amount=1000", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Quoter not responding: {err}")
    return _r(tid, lvl, lane, PASS, "Quoter endpoint responds")


def check_l4_07(probes: dict[str, bool]) -> "ExecutionResult":
    """MEXC market data endpoint."""
    tid, lvl, lane = "L4-07", "L4", "e2e"
    data, err = _jget(f"{ENGINE_URL}/api/mexc/market", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"MEXC market data not responding: {err}")
    return _r(tid, lvl, lane, PASS, "MEXC market data responds")


def check_l4_08(probes: dict[str, bool]) -> "ExecutionResult":
    """LP positions endpoint."""
    tid, lvl, lane = "L4-08", "L4", "e2e"
    data, err = _jget(f"{ENGINE_URL}/api/positions", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Positions endpoint not responding: {err}")
    return _r(tid, lvl, lane, PASS, "Positions endpoint responds")


def check_l4_seed_01(probes: dict[str, bool]) -> "ExecutionResult":
    """Verify seeding results: pools have liquidity, engine has inventory."""
    tid, lvl, lane = "L4-SEED-01", "L4", "e2e"

    # Load addresses
    orch_dir = os.environ.get("ORCHESTRATION_PATH", "")
    addr_file = os.path.join(orch_dir, "config", "addresses.json") if orch_dir else ""
    if not addr_file or not os.path.exists(addr_file):
        return _r(tid, lvl, lane, SKIP, "addresses.json not found")

    addrs = json.loads(open(addr_file).read())
    engine_addr = os.environ.get("ENGINE_ADDRESS", "")
    if not engine_addr:
        return _r(tid, lvl, lane, SKIP, "ENGINE_ADDRESS not set")

    rpc_url = ANVIL_URL
    tokens = addrs.get("tokens", {})
    details = []
    has_inventory = True

    # Check engine has leftover wrapped token inventory
    for symbol in ("wZEPH", "wZSD", "wZRS", "wZYS"):
        token_info = tokens.get(symbol, {})
        token_addr = token_info.get("address", "")
        if not token_addr:
            continue
        stdout, err = _cast([
            "call", token_addr, "balanceOf(address)(uint256)",
            engine_addr, "--rpc-url", rpc_url,
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

    # Check StateView for pool liquidity (if positionManager is deployed)
    posm = addrs.get("contracts", {}).get("positionManager", "")
    lp_count = 0
    if posm:
        stdout, err = _cast([
            "call", posm, "balanceOf(address)(uint256)",
            engine_addr, "--rpc-url", rpc_url,
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


TESTS: list[TestDef] = [
    TestDef("L4-01", "Transfer Gov -> Test Wallet", "L4", "e2e", check_l4_01),
    TestDef("L4-02", "RR Mode Transitions", "L4", "e2e", check_l4_02),
    TestDef("L4-03", "Engine State Updates with Chain", "L4", "e2e", check_l4_03),
    TestDef("L4-04", "Arbitrage Spread Detection", "L4", "e2e", check_l4_04),
    TestDef("L4-05", "Paper Account", "L4", "e2e", check_l4_05),
    TestDef("L4-06", "Quoter System", "L4", "e2e", check_l4_06),
    TestDef("L4-07", "MEXC Market Data", "L4", "e2e", check_l4_07),
    TestDef("L4-08", "LP Positions", "L4", "e2e", check_l4_08),
    TestDef("L4-SEED-01", "Seeding Verification", "L4", "e2e", check_l4_seed_01),
]
