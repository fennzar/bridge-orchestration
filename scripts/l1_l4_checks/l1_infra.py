"""L1: Infrastructure Tests (4 tests)."""
from __future__ import annotations

import json

from test_common import (
    ANVIL_URL, ATOMIC, ExecutionResult, FAIL, GOV_W, GOV_WALLET_PORT,
    MINER_W, MINER_WALLET_PORT,
    NODE1_RPC, NODE1_RPC_PORT, NODE2_RPC_PORT, ORACLE_URL, ORDERBOOK_URL,
    PASS, SKIP, TEST_W, TEST_WALLET_PORT,
    _get, _jget, _jpost, _rpc,
)
from ._types import TestDef, _r


def check_infra_01(probes: dict[str, bool]) -> "ExecutionResult":
    """Docker services: Redis, PostgreSQL, Anvil."""
    tid, lvl, lane = "INFRA-01", "L1", "infra"
    parts = []
    failed = False

    # Redis
    if probes.get("redis"):
        parts.append("Redis: OK")
    else:
        parts.append("Redis: not responding")
        failed = True

    # PostgreSQL
    if probes.get("postgres"):
        parts.append("PostgreSQL: OK")
    else:
        parts.append("PostgreSQL: not responding")
        failed = True

    # Anvil
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


def check_infra_02(probes: dict[str, bool]) -> "ExecutionResult":
    """DEVNET services: Oracle, Orderbook, Node1, Node2."""
    tid, lvl, lane = "INFRA-02", "L1", "infra"
    parts = []
    failed = False

    # Fake Oracle
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

    # Fake Orderbook
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

    # Node 1
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
                parts.append(f"Node 1: invalid height")
                failed = True
    else:
        parts.append(f"Node 1: not responding (port {NODE1_RPC_PORT})")
        failed = True

    # Node 2
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


def check_infra_03(probes: dict[str, bool]) -> "ExecutionResult":
    """Wallet RPCs: Gov, Miner, Test."""
    tid, lvl, lane = "INFRA-03", "L1", "infra"
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


def check_infra_04(probes: dict[str, bool]) -> "ExecutionResult":
    """Application services: Bridge-Web, Bridge-API, Engine."""
    tid, lvl, lane = "INFRA-04", "L1", "infra"
    parts = []
    failed = False

    services = [
        ("Bridge-Web", "http://127.0.0.1:7050/", 7050, "bridge_web"),
        ("Bridge-API", "http://127.0.0.1:7051/health", 7051, "bridge_api"),
        ("Engine", "http://127.0.0.1:7000/", 7000, "engine"),
    ]
    for name, url, port, probe_key in services:
        s, _, e = _get(url, timeout=5.0)
        if s == 200:
            parts.append(f"{name} ({port}): HTTP 200")
        else:
            parts.append(f"{name} ({port}): HTTP {s or '000'}")
            failed = True

    return _r(tid, lvl, lane, FAIL if failed else PASS, "; ".join(parts))


TESTS: list[TestDef] = [
    TestDef("INFRA-01", "Docker Services (Redis, PostgreSQL, Anvil)", "L1", "infra", check_infra_01),
    TestDef("INFRA-02", "DEVNET Services (Oracle, Orderbook, Node1, Node2)", "L1", "infra", check_infra_02),
    TestDef("INFRA-03", "Wallet RPCs (Gov, Miner, Test)", "L1", "infra", check_infra_03),
    TestDef("INFRA-04", "Application Services (Bridge-Web, Bridge-API, Engine)", "L1", "infra", check_infra_04),
]
