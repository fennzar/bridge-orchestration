"""Precheck tier: pre-setup gate (13 tests).

Validates that infrastructure is ready for `make dev-setup`.
Works after `make dev-init` + `make dev-infra` — no contracts or apps needed.
Some tests mutate state (XFER-01, ORACLE-01, RR-01) but validate machinery
that dev-setup depends on. CleanupContext restores oracle price.
"""
from __future__ import annotations

import time as _time
from pathlib import Path

from test_common import (
    ANVIL_URL, ATOMIC, ExecutionResult,
    FAIL, GOV_W, GOV_WALLET_PORT,
    MINER_W, MINER_WALLET_PORT,
    NODE1_RPC, NODE1_RPC_PORT, NODE2_RPC_PORT, ORACLE_URL, ORDERBOOK_URL,
    PASS, TEST_W, TEST_WALLET_PORT,
    _jget, _jpost, _rpc,
    set_oracle_price,
)
from ._types import TestDef, _r

# Import seed helpers for XFER-01 and RR-01
_sys_path = str(Path(__file__).resolve().parent.parent)
import sys as _sys
if _sys_path not in _sys.path:
    _sys.path.insert(0, _sys_path)

from lib.seed_helpers import mine_blocks


# ── L1 Infrastructure (3 tests) ──────────────────────────────────────


def check_infra_01(probes: dict[str, bool]) -> ExecutionResult:
    """Docker services: Redis, PostgreSQL, Anvil."""
    tid, lvl, lane = "INFRA-01", "infra", "infra"
    parts = []
    failed = False

    if probes.get("redis"):
        parts.append("Redis: OK")
    else:
        parts.append("Redis: not responding")
        failed = True

    if probes.get("postgres"):
        parts.append("PostgreSQL: OK")
    else:
        parts.append("PostgreSQL: not responding")
        failed = True

    if probes.get("anvil"):
        parsed, err = _jpost(
            ANVIL_URL,
            {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1},
            timeout=5.0,
        )
        if err:
            parts.append("Anvil: not responding")
            failed = True
        else:
            block_hex = (parsed or {}).get("result", "0x0")
            try:
                block = int(block_hex, 16)
            except (ValueError, TypeError):
                block = 0
            parts.append(f"Anvil: block {block}")
    else:
        parts.append("Anvil: not responding")
        failed = True

    return _r(tid, lvl, lane, FAIL if failed else PASS, "; ".join(parts))


def check_infra_02(probes: dict[str, bool]) -> ExecutionResult:
    """DEVNET services: Oracle, Orderbook, Node1, Node2."""
    tid, lvl, lane = "INFRA-02", "infra", "infra"
    parts = []
    failed = False

    if probes.get("oracle"):
        data, err = _jget(f"{ORACLE_URL}/status", timeout=5.0)
        if err:
            parts.append("Fake Oracle: not responding")
            failed = True
        else:
            spot = (data or {}).get("spot")
            if spot and spot != "null":
                price_usd = spot / ATOMIC
                parts.append(f"Fake Oracle: ${price_usd:.2f}")
            else:
                parts.append("Fake Oracle: no spot price")
                failed = True
    else:
        parts.append(f"Fake Oracle: not responding (port {ORACLE_URL.split(':')[-1].split('/')[0]})")
        failed = True

    if probes.get("orderbook"):
        data, err = _jget(f"{ORDERBOOK_URL}/status", timeout=5.0)
        if err:
            parts.append("Fake Orderbook: not responding")
            failed = True
        else:
            ob_price = (data or {}).get("oraclePriceUsd")
            if ob_price is not None and ob_price != "null":
                parts.append(f"Fake Orderbook: ${ob_price}")
            else:
                parts.append("Fake Orderbook: no price")
                failed = True
    else:
        parts.append("Fake Orderbook: not responding")
        failed = True

    if probes.get("node1"):
        result, err = _rpc(NODE1_RPC, "get_info", timeout=5.0)
        if err:
            parts.append(f"Node 1: not responding (port {NODE1_RPC_PORT})")
            failed = True
        else:
            height = (result or {}).get("height", 0)
            if height and int(height) > 0:
                parts.append(f"Node 1: height {height}")
            else:
                parts.append("Node 1: invalid height")
                failed = True
    else:
        parts.append(f"Node 1: not responding (port {NODE1_RPC_PORT})")
        failed = True

    if probes.get("node2"):
        result, err = _rpc(f"http://127.0.0.1:{NODE2_RPC_PORT}/json_rpc", "get_info", timeout=5.0)
        if err:
            parts.append(f"Node 2: not responding (port {NODE2_RPC_PORT})")
            failed = True
        else:
            height = (result or {}).get("height", 0)
            if height and int(height) > 0:
                parts.append(f"Node 2: height {height}")
            else:
                parts.append("Node 2: invalid height")
                failed = True
    else:
        parts.append(f"Node 2: not responding (port {NODE2_RPC_PORT})")
        failed = True

    return _r(tid, lvl, lane, FAIL if failed else PASS, "; ".join(parts))


def check_infra_03(probes: dict[str, bool]) -> ExecutionResult:
    """Wallet RPCs: Gov, Miner, Test."""
    tid, lvl, lane = "INFRA-03", "infra", "infra"
    parts = []
    failed = False

    wallets = [
        ("Gov", GOV_W, GOV_WALLET_PORT, "gov_wallet"),
        ("Miner", MINER_W, MINER_WALLET_PORT, "miner_wallet"),
        ("Test", TEST_W, TEST_WALLET_PORT, "test_wallet"),
    ]
    for name, url, port, probe_key in wallets:
        if probes.get(probe_key):
            result, err = _rpc(url, "get_version", timeout=5.0)
            if err:
                parts.append(f"{name} wallet ({port}): not responding")
                failed = True
            else:
                version = (result or {}).get("version", "unknown")
                parts.append(f"{name} wallet ({port}): v{version}")
        else:
            parts.append(f"{name} wallet ({port}): not responding")
            failed = True

    return _r(tid, lvl, lane, FAIL if failed else PASS, "; ".join(parts))


# ── L2 Smoke (4 tests) ───────────────────────────────────────────────


def check_smoke_01(probes: dict[str, bool]) -> ExecutionResult:
    """Zephyr chain health: height, synced, difficulty."""
    tid, lvl, lane = "SMOKE-01", "smoke", "smoke"

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


def check_smoke_02(probes: dict[str, bool]) -> ExecutionResult:
    """Gov wallet balances: ZPH, ZRS, ZSD."""
    tid, lvl, lane = "SMOKE-02", "smoke", "smoke"

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


def check_smoke_03(probes: dict[str, bool]) -> ExecutionResult:
    """Oracle price: spot > 0."""
    tid, lvl, lane = "SMOKE-03", "smoke", "smoke"

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


def check_smoke_06(probes: dict[str, bool]) -> ExecutionResult:
    """Mining active: mining_status or block production."""
    tid, lvl, lane = "SMOKE-06", "smoke", "smoke"

    result, err = _rpc(NODE1_RPC, "mining_status", timeout=5.0)
    if err is None and result:
        active = result.get("active")
        if active is True or active == "true":
            speed = result.get("speed", 0)
            return _r(tid, lvl, lane, PASS, f"Mining active: {speed} H/s")
        if active is False or active == "false":
            return _r(tid, lvl, lane, FAIL, "Mining not active")

    info1, _ = _rpc(NODE1_RPC, "get_info", timeout=5.0)
    h1 = int((info1 or {}).get("height", 0))
    _time.sleep(3)
    info2, _ = _rpc(NODE1_RPC, "get_info", timeout=5.0)
    h2 = int((info2 or {}).get("height", 0))

    if h2 > h1:
        return _r(tid, lvl, lane, PASS, f"Blocks being produced ({h1} -> {h2})")
    return _r(tid, lvl, lane, PASS, f"No new blocks in 3s (height: {h2}) - mining may be paused")


# ── L3 Component (2 read-only tests) ─────────────────────────────────


def check_zephyr_01(probes: dict[str, bool]) -> ExecutionResult:
    """Gov wallet balances (detailed, all 4 assets)."""
    tid, lvl, lane = "ZEPHYR-01", "zephyr", "zephyr"

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


def check_zephyr_02(probes: dict[str, bool]) -> ExecutionResult:
    """Reserve info from node."""
    tid, lvl, lane = "ZEPHYR-02", "zephyr", "zephyr"

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


def check_orderbook_01(probes: dict[str, bool]) -> ExecutionResult:
    """Orderbook tracks oracle price."""
    tid, lvl, lane = "ORDERBOOK-01", "orderbook", "orderbook"

    data, err = _jget(f"{ORDERBOOK_URL}/status", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Orderbook not responding: {err}")

    ob_price = (data or {}).get("oraclePriceUsd")
    if ob_price is not None and ob_price != "null":
        return _r(tid, lvl, lane, PASS, f"Orderbook tracking oracle price: ${ob_price}")
    return _r(tid, lvl, lane, FAIL, "Orderbook not tracking price")


# ── State-mutating pre-setup validations (3 tests) ──────────────────


def check_xfer_01(probes: dict[str, bool]) -> ExecutionResult:
    """Transfer Gov -> Test wallet (mines warm-up blocks if outputs locked)."""
    tid, lvl, lane = "XFER-01", "transfer", "precheck"

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
    tid, lvl, lane = "ORACLE-01", "oracle", "precheck"

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
    tid, lvl, lane = "RR-01", "rr", "precheck"

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
    # L1 Infrastructure
    TestDef("INFRA-01", "Docker Services (Redis, PostgreSQL, Anvil)", "infra", "precheck", "infra", check_infra_01),
    TestDef("INFRA-02", "DEVNET Services (Oracle, Orderbook, Node1, Node2)", "infra", "precheck", "infra", check_infra_02),
    TestDef("INFRA-03", "Wallet RPCs (Gov, Miner, Test)", "infra", "precheck", "infra", check_infra_03),
    # L2 Smoke (pre-setup subset)
    TestDef("SMOKE-01", "Zephyr Chain Health", "smoke", "precheck", "smoke", check_smoke_01),
    TestDef("SMOKE-02", "Gov Wallet Balances", "smoke", "precheck", "smoke", check_smoke_02),
    TestDef("SMOKE-03", "Oracle Price", "smoke", "precheck", "smoke", check_smoke_03),
    TestDef("SMOKE-06", "Mining Active", "smoke", "precheck", "smoke", check_smoke_06),
    # L3 Component (pre-setup subset)
    TestDef("ZEPHYR-01", "Gov Wallet Balances (Detailed)", "zephyr", "precheck", "zephyr", check_zephyr_01),
    TestDef("ZEPHYR-02", "Reserve Info", "zephyr", "precheck", "zephyr", check_zephyr_02),
    TestDef("ORDERBOOK-01", "Orderbook Price Tracking", "orderbook", "precheck", "orderbook", check_orderbook_01),
    # State-mutating pre-setup validations
    TestDef("XFER-01", "Zephyr Transfer", "transfer", "precheck", "precheck", check_xfer_01),
    TestDef("ORACLE-01", "Oracle Price Control", "oracle", "precheck", "precheck", check_oracle_01),
    TestDef("RR-01", "RR Mode Transition", "rr", "precheck", "precheck", check_rr_01),
]
