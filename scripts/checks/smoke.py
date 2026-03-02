"""Smoke tier: post-setup health checks (19 tests).

These tests verify that apps are running and contracts are deployed.
Requires: make dev-setup + make dev (apps running, contracts deployed).
All read-only — no state mutation.
"""
from __future__ import annotations

import json
import os
import subprocess
import time as _time

from test_common import (
    ANVIL_URL, BRIDGE_API_URL, DEPLOYED_ADDRESSES_FILE,
    ENGINE_URL, ExecutionResult,
    FAIL, PASS, ROOT, SKIP,
    _cast, _get, _jget, _jpost,
)
from ._types import TestDef, _r


# ── Infrastructure (1 test) ──────────────────────────────────────────


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
    for name, url, port, _probe_key in services:
        s, _, _e = _get(url, timeout=5.0)
        if s == 200:
            parts.append(f"{name} ({port}): HTTP 200")
        else:
            parts.append(f"{name} ({port}): HTTP {s or '000'}")
            failed = True

    return _r(tid, lvl, lane, FAIL if failed else PASS, "; ".join(parts))


# ── Smoke (2 tests) ─────────────────────────────────────────────────


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


# ── Engine (6 tests) ────────────────────────────────────────────────


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


# ── Bridge (3 tests) ────────────────────────────────────────────────


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


# ── EVM (1 test) ────────────────────────────────────────────────────


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


# ── Engine Seed (1 test) ────────────────────────────────────────────


def check_engine_seed_01(probes: dict[str, bool]) -> ExecutionResult:
    """Engine CLI setup --dry-run: verify plan includes all 4 engine-seeded pools."""
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
        if pool_count >= 4:
            return _r(tid, lvl, lane, PASS, f"Dry run shows {pool_count} pool plans")
        return _r(tid, lvl, lane, FAIL, f"Expected 4+ pool plans, found {pool_count}")

    except subprocess.TimeoutExpired:
        return _r(tid, lvl, lane, FAIL, "CLI timed out after 30s")
    except FileNotFoundError:
        return _r(tid, lvl, lane, SKIP, "pnpm not found")


# ── L4 E2E (5 tests) ────────────────────────────────────────────────


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
    # Infrastructure
    TestDef("INFRA-04", "Application Services (Bridge-Web, Bridge-API, Engine)", "infra", "smoke", "infra", check_infra_04),
    # Smoke
    TestDef("SMOKE-04", "EVM Contracts Deployed", "smoke", "smoke", "smoke", check_smoke_04),
    TestDef("SMOKE-05", "Bridge API Health", "smoke", "smoke", "smoke", check_smoke_05),
    # Engine
    TestDef("ENGINE-01", "State Builder", "engine", "smoke", "engine", check_engine_01),
    TestDef("ENGINE-02", "Engine Status", "engine", "smoke", "engine", check_engine_02),
    TestDef("ENGINE-03", "Arbitrage Analysis", "engine", "smoke", "engine", check_engine_03),
    TestDef("ENGINE-04", "Balances", "engine", "smoke", "engine", check_engine_04),
    TestDef("ENGINE-05", "Runtime Info", "engine", "smoke", "engine", check_engine_05),
    TestDef("ENGINE-06", "Zephyr Network State", "engine", "smoke", "engine", check_engine_06),
    # Bridge
    TestDef("BRIDGE-01", "Bridge API Status", "bridge", "smoke", "bridge", check_bridge_01),
    TestDef("BRIDGE-02", "Claims Endpoint", "bridge", "smoke", "bridge", check_bridge_02),
    TestDef("BRIDGE-03", "Unwraps Endpoint", "bridge", "smoke", "bridge", check_bridge_03),
    # EVM
    TestDef("EVM-01", "Deployed Contracts", "evm", "smoke", "evm", check_evm_01),
    # Engine Seed
    TestDef("ENGINE-SEED-01", "Engine CLI Dry Run", "engine", "smoke", "engine", check_engine_seed_01),
    # L4 E2E
    TestDef("L4-03", "Engine State Updates with Chain", "e2e", "smoke", "e2e", check_l4_03),
    TestDef("L4-05", "Paper Account", "e2e", "smoke", "e2e", check_l4_05),
    TestDef("L4-06", "Quoter System", "e2e", "smoke", "e2e", check_l4_06),
    TestDef("L4-07", "MEXC Market Data", "e2e", "smoke", "e2e", check_l4_07),
    TestDef("L4-08", "LP Positions", "e2e", "smoke", "e2e", check_l4_08),
]
