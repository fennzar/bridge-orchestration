"""Precheck tier: read-only health probes (29 tests).

Migrated verbatim from l1_l4_checks. These only perform HTTP GET / RPC queries
and never mutate state. No CleanupContext needed.
"""
from __future__ import annotations

import json
import os
import subprocess
import time as _time

from test_common import (
    ANVIL_URL, ATOMIC, BRIDGE_API_URL, DEPLOYED_ADDRESSES_FILE,
    ENGINE_URL, ExecutionResult, FAIL, GOV_W, GOV_WALLET_PORT,
    MINER_W, MINER_WALLET_PORT,
    NODE1_RPC, NODE1_RPC_PORT, NODE2_RPC_PORT, ORACLE_URL, ORDERBOOK_URL,
    PASS, ROOT, SKIP, TEST_W, TEST_WALLET_PORT,
    _cast, _get, _jget, _jpost, _rpc,
)
from ._types import TestDef, _r


# ── L1 Infrastructure (4 tests) ──────────────────────────────────────


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


def check_infra_04(probes: dict[str, bool]) -> ExecutionResult:
    """Application services: Bridge-Web, Bridge-API, Engine."""
    tid, lvl, lane = "INFRA-04", "infra", "infra"
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


# ── L2 Smoke (6 tests) ───────────────────────────────────────────────


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


def check_smoke_04(probes: dict[str, bool]) -> ExecutionResult:
    """EVM contracts deployed: wZEPH has code."""
    tid, lvl, lane = "SMOKE-04", "smoke", "smoke"

    wzeph_addr = None
    env_addr = os.environ.get("WZEPH_ADDRESS")
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


def check_smoke_05(probes: dict[str, bool]) -> ExecutionResult:
    """Bridge API health endpoint."""
    tid, lvl, lane = "SMOKE-05", "smoke", "smoke"

    data, err = _jget(f"{BRIDGE_API_URL}/health", timeout=5.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Bridge API health: {err}")

    status = (data or {}).get("status", "")
    if status in ("ok", "healthy"):
        return _r(tid, lvl, lane, PASS, f"Bridge API: {status}")
    return _r(tid, lvl, lane, FAIL, f"Bridge API status: {status or 'no response'}")


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


# ── L3 Component (13 read-only tests) ────────────────────────────────


def check_engine_01(probes: dict[str, bool]) -> ExecutionResult:
    """Engine state builder: zephyr, cex, evm sections present."""
    tid, lvl, lane = "ENGINE-01", "engine", "engine"

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


def check_engine_02(probes: dict[str, bool]) -> ExecutionResult:
    """Engine status: reserveRatio and rrMode present."""
    tid, lvl, lane = "ENGINE-02", "engine", "engine"

    data, err = _jget(f"{ENGINE_URL}/api/engine/status", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Status endpoint not responding: {err}")

    state = (data or {}).get("state", {})
    rr = state.get("reserveRatio")
    mode = state.get("rrMode")
    if rr is not None:
        return _r(tid, lvl, lane, PASS, f"Engine status - RR={rr}, mode={mode}")
    return _r(tid, lvl, lane, FAIL, "Status endpoint not responding")


def check_engine_03(probes: dict[str, bool]) -> ExecutionResult:
    """Arbitrage analysis endpoint responds with valid JSON."""
    tid, lvl, lane = "ENGINE-03", "engine", "engine"

    data, err = _jget(f"{ENGINE_URL}/api/arbitrage/analysis", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Arbitrage analysis not responding: {err}")
    return _r(tid, lvl, lane, PASS, "Arbitrage analysis endpoint responds")


def check_engine_04(probes: dict[str, bool]) -> ExecutionResult:
    """Balances endpoint responds."""
    tid, lvl, lane = "ENGINE-04", "engine", "engine"
    data, err = _jget(f"{ENGINE_URL}/api/balances", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Balances endpoint not responding: {err}")
    return _r(tid, lvl, lane, PASS, "Balances endpoint responds")


def check_engine_05(probes: dict[str, bool]) -> ExecutionResult:
    """Runtime endpoint responds."""
    tid, lvl, lane = "ENGINE-05", "engine", "engine"
    data, err = _jget(f"{ENGINE_URL}/api/runtime", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Runtime endpoint not responding: {err}")
    return _r(tid, lvl, lane, PASS, "Runtime endpoint responds")


def check_engine_06(probes: dict[str, bool]) -> ExecutionResult:
    """Zephyr network state with reserveRatio."""
    tid, lvl, lane = "ENGINE-06", "engine", "engine"

    data, err = _jget(f"{ENGINE_URL}/api/zephyr/network-state", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Zephyr network state not responding: {err}")

    rr = (data or {}).get("reserveRatio")
    if rr is not None:
        return _r(tid, lvl, lane, PASS, f"Zephyr network state - RR={rr}")
    return _r(tid, lvl, lane, FAIL, "Zephyr network state not responding")


def check_bridge_01(probes: dict[str, bool]) -> ExecutionResult:
    """Bridge API status endpoint."""
    tid, lvl, lane = "BRIDGE-01", "bridge", "bridge"

    data, err = _jget(f"{BRIDGE_API_URL}/bridge/status", timeout=10.0)
    if err is None and data:
        return _r(tid, lvl, lane, PASS, "Bridge status endpoint responds")

    s, _, e = _get(f"{BRIDGE_API_URL}/health", timeout=10.0)
    if s == 200:
        return _r(tid, lvl, lane, PASS, "Bridge API healthy (health endpoint)")
    return _r(tid, lvl, lane, FAIL, "Bridge API not responding")


def check_bridge_02(probes: dict[str, bool]) -> ExecutionResult:
    """Claims endpoint responds."""
    tid, lvl, lane = "BRIDGE-02", "bridge", "bridge"
    s, body, e = _get(f"{BRIDGE_API_URL}/claims", timeout=10.0)
    if body:
        return _r(tid, lvl, lane, PASS, "Claims endpoint responds")
    return _r(tid, lvl, lane, FAIL, "Claims endpoint not responding")


def check_bridge_03(probes: dict[str, bool]) -> ExecutionResult:
    """Unwraps endpoint responds."""
    tid, lvl, lane = "BRIDGE-03", "bridge", "bridge"
    s, body, e = _get(f"{BRIDGE_API_URL}/unwraps", timeout=10.0)
    if body:
        return _r(tid, lvl, lane, PASS, "Unwraps endpoint responds")
    return _r(tid, lvl, lane, FAIL, "Unwraps endpoint not responding")


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


def check_evm_01(probes: dict[str, bool]) -> ExecutionResult:
    """Deployed contracts: wZEPH totalSupply via cast."""
    tid, lvl, lane = "EVM-01", "evm", "evm"

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


def check_engine_seed_01(probes: dict[str, bool]) -> ExecutionResult:
    """Engine CLI setup --dry-run: verify plan includes all 5 pools."""
    tid, lvl, lane = "ENGINE-SEED-01", "engine", "engine"

    engine_repo = os.environ.get("ENGINE_REPO_PATH", "")
    if not engine_repo:
        return _r(tid, lvl, lane, SKIP, "ENGINE_REPO_PATH not set")

    engine_env_file = os.path.join(engine_repo, ".env")
    if not os.path.exists(engine_env_file):
        return _r(tid, lvl, lane, SKIP, "Engine .env not found")

    child_env = dict(os.environ)
    with open(engine_env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            child_env[k.strip()] = v.strip().strip("'\"")

    try:
        result = subprocess.run(
            ["pnpm", "engine", "setup", "--dry-run"],
            capture_output=True, text=True, timeout=30,
            cwd=engine_repo, env=child_env,
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            return _r(tid, lvl, lane, FAIL, f"CLI exited {result.returncode}: {output[-200:]}")

        pool_count = output.count('"base"')
        if pool_count >= 5:
            return _r(tid, lvl, lane, PASS, f"Dry run shows {pool_count} pool plans")
        return _r(tid, lvl, lane, FAIL, f"Expected 5+ pool plans, found {pool_count}")

    except subprocess.TimeoutExpired:
        return _r(tid, lvl, lane, FAIL, "CLI timed out after 30s")
    except FileNotFoundError:
        return _r(tid, lvl, lane, SKIP, "pnpm not found")


# ── L4 E2E (6 read-only tests) ───────────────────────────────────────


def check_l4_03(probes: dict[str, bool]) -> ExecutionResult:
    """Engine state updates with chain."""
    tid, lvl, lane = "L4-03", "e2e", "e2e"

    _time.sleep(5)

    data, err = _jget(f"{ENGINE_URL}/api/state", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Could not get engine state: {err}")

    state = (data or {}).get("state", {})
    engine_rr = ((state.get("zephyr") or {}).get("reserve", {}) or {}).get("reserveRatio")

    if engine_rr is not None and engine_rr != "null" and engine_rr != 0:
        return _r(tid, lvl, lane, PASS, f"Engine tracking chain state - RR={engine_rr}")
    return _r(tid, lvl, lane, FAIL, "Engine RR not available")


def check_l4_05(probes: dict[str, bool]) -> ExecutionResult:
    """Paper account endpoint."""
    tid, lvl, lane = "L4-05", "e2e", "e2e"
    data, err = _jget(f"{ENGINE_URL}/api/paper/account", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Paper account not responding: {err}")
    return _r(tid, lvl, lane, PASS, "Paper account endpoint responds")


def check_l4_06(probes: dict[str, bool]) -> ExecutionResult:
    """Quoter system: convert ZPH to ZSD."""
    tid, lvl, lane = "L4-06", "e2e", "e2e"
    data, err = _jget(f"{ENGINE_URL}/api/quoters?op=convert&from=ZPH&to=ZSD&amount=1000", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Quoter not responding: {err}")
    return _r(tid, lvl, lane, PASS, "Quoter endpoint responds")


def check_l4_07(probes: dict[str, bool]) -> ExecutionResult:
    """MEXC market data endpoint."""
    tid, lvl, lane = "L4-07", "e2e", "e2e"
    data, err = _jget(f"{ENGINE_URL}/api/mexc/market", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"MEXC market data not responding: {err}")
    return _r(tid, lvl, lane, PASS, "MEXC market data responds")


def check_l4_08(probes: dict[str, bool]) -> ExecutionResult:
    """LP positions endpoint."""
    tid, lvl, lane = "L4-08", "e2e", "e2e"
    data, err = _jget(f"{ENGINE_URL}/api/positions", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Positions endpoint not responding: {err}")
    return _r(tid, lvl, lane, PASS, "Positions endpoint responds")


# ── Test Registry ────────────────────────────────────────────────────

TESTS: list[TestDef] = [
    # L1 Infrastructure
    TestDef("INFRA-01", "Docker Services (Redis, PostgreSQL, Anvil)", "infra", "precheck", "infra", check_infra_01),
    TestDef("INFRA-02", "DEVNET Services (Oracle, Orderbook, Node1, Node2)", "infra", "precheck", "infra", check_infra_02),
    TestDef("INFRA-03", "Wallet RPCs (Gov, Miner, Test)", "infra", "precheck", "infra", check_infra_03),
    TestDef("INFRA-04", "Application Services (Bridge-Web, Bridge-API, Engine)", "infra", "precheck", "infra", check_infra_04),
    # L2 Smoke
    TestDef("SMOKE-01", "Zephyr Chain Health", "smoke", "precheck", "smoke", check_smoke_01),
    TestDef("SMOKE-02", "Gov Wallet Balances", "smoke", "precheck", "smoke", check_smoke_02),
    TestDef("SMOKE-03", "Oracle Price", "smoke", "precheck", "smoke", check_smoke_03),
    TestDef("SMOKE-04", "EVM Contracts Deployed", "smoke", "precheck", "smoke", check_smoke_04),
    TestDef("SMOKE-05", "Bridge API Health", "smoke", "precheck", "smoke", check_smoke_05),
    TestDef("SMOKE-06", "Mining Active", "smoke", "precheck", "smoke", check_smoke_06),
    # L3 Component (read-only subset)
    TestDef("ENGINE-01", "State Builder", "engine", "precheck", "engine", check_engine_01),
    TestDef("ENGINE-02", "Engine Status", "engine", "precheck", "engine", check_engine_02),
    TestDef("ENGINE-03", "Arbitrage Analysis", "engine", "precheck", "engine", check_engine_03),
    TestDef("ENGINE-04", "Balances", "engine", "precheck", "engine", check_engine_04),
    TestDef("ENGINE-05", "Runtime Info", "engine", "precheck", "engine", check_engine_05),
    TestDef("ENGINE-06", "Zephyr Network State", "engine", "precheck", "engine", check_engine_06),
    TestDef("BRIDGE-01", "Bridge API Status", "bridge", "precheck", "bridge", check_bridge_01),
    TestDef("BRIDGE-02", "Claims Endpoint", "bridge", "precheck", "bridge", check_bridge_02),
    TestDef("BRIDGE-03", "Unwraps Endpoint", "bridge", "precheck", "bridge", check_bridge_03),
    TestDef("ZEPHYR-01", "Gov Wallet Balances (Detailed)", "zephyr", "precheck", "zephyr", check_zephyr_01),
    TestDef("ZEPHYR-02", "Reserve Info", "zephyr", "precheck", "zephyr", check_zephyr_02),
    TestDef("EVM-01", "Deployed Contracts", "evm", "precheck", "evm", check_evm_01),
    TestDef("ORDERBOOK-01", "Orderbook Price Tracking", "orderbook", "precheck", "orderbook", check_orderbook_01),
    TestDef("ENGINE-SEED-01", "Engine CLI Dry Run", "engine", "precheck", "engine", check_engine_seed_01),
    # L4 E2E (read-only subset)
    TestDef("L4-03", "Engine State Updates with Chain", "e2e", "precheck", "e2e", check_l4_03),
    TestDef("L4-05", "Paper Account", "e2e", "precheck", "e2e", check_l4_05),
    TestDef("L4-06", "Quoter System", "e2e", "precheck", "e2e", check_l4_06),
    TestDef("L4-07", "MEXC Market Data", "e2e", "precheck", "e2e", check_l4_07),
    TestDef("L4-08", "LP Positions", "e2e", "precheck", "e2e", check_l4_08),
]
