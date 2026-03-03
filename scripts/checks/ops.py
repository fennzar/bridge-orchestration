"""Ops tier (T3): basic operations validation (3 tests).

Mutating tests that verify fund transfers, oracle control, and RR mode
transitions work correctly. Runs after dev-init with infra up.
"""
from __future__ import annotations

import time as _time
from pathlib import Path

from test_common import (
    ATOMIC, ExecutionResult,
    FAIL, GOV_W,
    NODE1_RPC, ORACLE_URL,
    PASS, TEST_W,
    _jget, _rpc,
    set_oracle_price,
)
from ._types import TestDef, _r

# Import seed helpers for XFER-01 and RR-01
_sys_path = str(Path(__file__).resolve().parent.parent)
import sys as _sys
if _sys_path not in _sys.path:
    _sys.path.insert(0, _sys_path)

from lib.seed_helpers import mine_blocks


# ── State-mutating operations (3 tests) ─────────────────────────────


def check_xfer_01(probes: dict[str, bool]) -> ExecutionResult:
    """Transfer Gov -> Test wallet (mines warm-up blocks if outputs locked)."""
    tid, lvl, lane = "XFER-01", "transfer", "ops"

    result, err = _rpc(TEST_W, "get_address", {"account_index": 0}, timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Could not get test wallet address: {err}")

    test_addr = (result or {}).get("address")
    if not test_addr:
        return _r(tid, lvl, lane, FAIL, "Could not get test wallet address")

    for attempt in range(1, 4):
        _rpc(GOV_W, "refresh", timeout=10.0)

        transfer_result, err = _rpc(GOV_W, "transfer", {
            "destinations": [{"amount": 100_000_000_000_000, "address": test_addr}],
            "source_asset": "ZPH",
            "destination_asset": "ZPH",
        }, timeout=10.0)

        if err is None and transfer_result:
            tx_hash = transfer_result.get("tx_hash")
            if tx_hash:
                _time.sleep(10)
                _rpc(TEST_W, "refresh", timeout=10.0)
                bal_result, _ = _rpc(TEST_W, "get_balance", {"account_index": 0}, timeout=10.0)
                test_bal = int((bal_result or {}).get("balance", 0))
                bal_str = f" (balance: {test_bal / ATOMIC:.4f} ZPH)" if test_bal > 0 else ""
                return _r(tid, lvl, lane, PASS, f"Transfer submitted - tx={tx_hash}{bal_str}")

        err_msg = str(err) if err else "unknown error"

        # Outputs locked after dev-reset — mine warm-up blocks (coinbase maturity=60)
        if "unlocked" in err_msg.lower() and attempt < 3:
            mine_blocks(65)
            _rpc(GOV_W, "refresh", timeout=10.0)
            continue

        if "ring" in err_msg.lower() and attempt < 3:
            _time.sleep(15)
            continue

        return _r(tid, lvl, lane, FAIL, f"Transfer failed - {err_msg}")

    return _r(tid, lvl, lane, FAIL, "Transfer failed after 3 retries")


def check_oracle_01(probes: dict[str, bool]) -> ExecutionResult:
    """Oracle price control: set/verify/restore."""
    tid, lvl, lane = "ORACLE-01", "oracle", "ops"

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


def check_rr_01(probes: dict[str, bool]) -> ExecutionResult:
    """RR mode transitions via oracle price change."""
    tid, lvl, lane = "RR-01", "rr", "ops"

    result, err = _rpc(NODE1_RPC, "get_reserve_info", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Could not get reserve info: {err}")

    current_rr = (result or {}).get("reserve_ratio", "0")

    # Drop oracle price and mine blocks so the new price takes effect
    set_oracle_price(0.60)
    mine_blocks(3)
    _time.sleep(2)

    result2, err2 = _rpc(NODE1_RPC, "get_reserve_info", timeout=10.0)
    new_rr = (result2 or {}).get("reserve_ratio", "0") if not err2 else "0"

    # Restore price and mine so it takes effect
    set_oracle_price(1.50)
    mine_blocks(3)

    try:
        rr_num = int(float(new_rr))
    except (ValueError, TypeError):
        rr_num = 999

    if rr_num < 7:
        return _r(tid, lvl, lane, PASS, f"RR responded to oracle change ({current_rr} -> {new_rr})")
    return _r(tid, lvl, lane, FAIL, f"RR did not change as expected ({current_rr} -> {new_rr})")


# ── Test Registry ────────────────────────────────────────────────────

TESTS: list[TestDef] = [
    TestDef("XFER-01", "Zephyr Transfer", "transfer", "ops", "ops", check_xfer_01),
    TestDef("ORACLE-01", "Oracle Price Control", "oracle", "ops", "ops", check_oracle_01),
    TestDef("RR-01", "RR Mode Transition", "rr", "ops", "ops", check_rr_01),
]
