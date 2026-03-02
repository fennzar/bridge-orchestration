"""Bridge tier — health checks (28 tests).

Post-setup read-only health probes: app services, contracts, engine endpoints,
bridge API, seed verification. Merged from old smoke + seed tiers.
Requires: make dev-setup + make dev (apps running, contracts deployed).
"""
from __future__ import annotations

import json
import os
import subprocess
import time as _time
from pathlib import Path

from test_common import (
    ANVIL_URL, ATOMIC, BRIDGE_API_URL, DEPLOYED_ADDRESSES_FILE,
    ENGINE_URL, ExecutionResult,
    FAIL, PASS, ROOT, SKIP,
    _cast, _eth_call, _get, _jget, _jpost, _rpc,
    TK, CTX,
)
from ._types import TestDef, _r

_ROOT = Path(__file__).resolve().parent.parent.parent

ENGINE_ADDRESS = os.environ.get("ENGINE_ADDRESS", "")
ENGINE_WALLET_PORT = 48771
SEL_BALANCE_OF = "0x70a08231"


# ── Helpers ──────────────────────────────────────────────────────────


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
        p = _ROOT / fname
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


# ══════════════════════════════════════════════════════════════════════
# App + Contract Health (from old smoke tier)
# ══════════════════════════════════════════════════════════════════════


# ── Infrastructure (1 test) ──────────────────────────────────────────


def check_infra_04(probes: dict[str, bool]) -> ExecutionResult:
    """Application services: Bridge-Web, Bridge-API, Engine."""
    tid, lvl, lane = "INFRA-04", "infra", "bridge"
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
    tid, lvl, lane = "SMOKE-04", "smoke", "bridge"

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
    tid, lvl, lane = "SMOKE-05", "smoke", "bridge"

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
    tid, lvl, lane = "ENGINE-01", "engine", "bridge"

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
    tid, lvl, lane = "ENGINE-02", "engine", "bridge"

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
    tid, lvl, lane = "ENGINE-03", "engine", "bridge"

    data, err = _jget(f"{ENGINE_URL}/api/arbitrage/analysis", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Arbitrage analysis not responding: {err}")
    return _r(tid, lvl, lane, PASS, "Arbitrage analysis endpoint responds")


def check_engine_04(probes: dict[str, bool]) -> ExecutionResult:
    """Balances endpoint responds."""
    tid, lvl, lane = "ENGINE-04", "engine", "bridge"
    data, err = _jget(f"{ENGINE_URL}/api/balances", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Balances endpoint not responding: {err}")
    return _r(tid, lvl, lane, PASS, "Balances endpoint responds")


def check_engine_05(probes: dict[str, bool]) -> ExecutionResult:
    """Runtime endpoint responds."""
    tid, lvl, lane = "ENGINE-05", "engine", "bridge"
    data, err = _jget(f"{ENGINE_URL}/api/runtime", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Runtime endpoint not responding: {err}")
    return _r(tid, lvl, lane, PASS, "Runtime endpoint responds")


def check_engine_06(probes: dict[str, bool]) -> ExecutionResult:
    """Zephyr network state with reserveRatio."""
    tid, lvl, lane = "ENGINE-06", "engine", "bridge"

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
    tid, lvl, lane = "EVM-01", "evm", "bridge"

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
    tid, lvl, lane = "ENGINE-SEED-01", "engine", "bridge"

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
    tid, lvl, lane = "L4-03", "e2e", "bridge"

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
    tid, lvl, lane = "L4-05", "e2e", "bridge"
    data, err = _jget(f"{ENGINE_URL}/api/paper/account", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Paper account not responding: {err}")
    return _r(tid, lvl, lane, PASS, "Paper account endpoint responds")


def check_l4_06(probes: dict[str, bool]) -> ExecutionResult:
    """Quoter system: convert ZPH to ZSD."""
    tid, lvl, lane = "L4-06", "e2e", "bridge"
    data, err = _jget(f"{ENGINE_URL}/api/quoters?op=convert&from=ZPH&to=ZSD&amount=1000", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Quoter not responding: {err}")
    return _r(tid, lvl, lane, PASS, "Quoter endpoint responds")


def check_l4_07(probes: dict[str, bool]) -> ExecutionResult:
    """MEXC market data endpoint."""
    tid, lvl, lane = "L4-07", "e2e", "bridge"
    data, err = _jget(f"{ENGINE_URL}/api/mexc/market", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"MEXC market data not responding: {err}")
    return _r(tid, lvl, lane, PASS, "MEXC market data responds")


def check_l4_08(probes: dict[str, bool]) -> ExecutionResult:
    """LP positions endpoint."""
    tid, lvl, lane = "L4-08", "e2e", "bridge"
    data, err = _jget(f"{ENGINE_URL}/api/positions", timeout=10.0)
    if err:
        return _r(tid, lvl, lane, FAIL, f"Positions endpoint not responding: {err}")
    return _r(tid, lvl, lane, PASS, "Positions endpoint responds")


# ══════════════════════════════════════════════════════════════════════
# Seed Verification (from old seed tier)
# ══════════════════════════════════════════════════════════════════════


def check_seed_01(probes: dict[str, bool]) -> ExecutionResult:
    """Engine Zephyr wallet is funded with all asset types."""
    tid, lvl, lane = "SEED-01", "seed", "bridge"

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
    tid, lvl, lane = "SEED-02", "seed", "bridge"
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
    tid, lvl, lane = "SEED-03", "seed", "bridge"
    skip = _need_engine_addr(tid, lvl, lane)
    if skip:
        return skip

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
    tid, lvl, lane = "SEED-04", "seed", "bridge"
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
    tid, lvl, lane = "SEED-05", "seed", "bridge"
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
    tid, lvl, lane = "SEED-06", "seed", "bridge"

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
    tid, lvl, lane = "SEED-07", "seed", "bridge"

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
    tid, lvl, lane = "SEED-08", "seed", "bridge"
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
    tid, lvl, lane = "SEED-09", "seed", "bridge"
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
    # App + Contract Health (from old smoke tier)
    TestDef("INFRA-04", "Application Services (Bridge-Web, Bridge-API, Engine)", "infra", "bridge", "bridge", check_infra_04),
    TestDef("SMOKE-04", "EVM Contracts Deployed", "smoke", "bridge", "bridge", check_smoke_04),
    TestDef("SMOKE-05", "Bridge API Health", "smoke", "bridge", "bridge", check_smoke_05),
    TestDef("ENGINE-01", "State Builder", "engine", "bridge", "bridge", check_engine_01),
    TestDef("ENGINE-02", "Engine Status", "engine", "bridge", "bridge", check_engine_02),
    TestDef("ENGINE-03", "Arbitrage Analysis", "engine", "bridge", "bridge", check_engine_03),
    TestDef("ENGINE-04", "Balances", "engine", "bridge", "bridge", check_engine_04),
    TestDef("ENGINE-05", "Runtime Info", "engine", "bridge", "bridge", check_engine_05),
    TestDef("ENGINE-06", "Zephyr Network State", "engine", "bridge", "bridge", check_engine_06),
    TestDef("BRIDGE-01", "Bridge API Status", "bridge", "bridge", "bridge", check_bridge_01),
    TestDef("BRIDGE-02", "Claims Endpoint", "bridge", "bridge", "bridge", check_bridge_02),
    TestDef("BRIDGE-03", "Unwraps Endpoint", "bridge", "bridge", "bridge", check_bridge_03),
    TestDef("EVM-01", "Deployed Contracts", "evm", "bridge", "bridge", check_evm_01),
    TestDef("ENGINE-SEED-01", "Engine CLI Dry Run", "engine", "bridge", "bridge", check_engine_seed_01),
    TestDef("L4-03", "Engine State Updates with Chain", "e2e", "bridge", "bridge", check_l4_03),
    TestDef("L4-05", "Paper Account", "e2e", "bridge", "bridge", check_l4_05),
    TestDef("L4-06", "Quoter System", "e2e", "bridge", "bridge", check_l4_06),
    TestDef("L4-07", "MEXC Market Data", "e2e", "bridge", "bridge", check_l4_07),
    TestDef("L4-08", "LP Positions", "e2e", "bridge", "bridge", check_l4_08),
    # Seed Verification (from old seed tier)
    TestDef("SEED-01", "Engine Zephyr Wallet Funded", "seed", "bridge", "bridge", check_seed_01),
    TestDef("SEED-02", "Bridge Recognises Engine Address", "seed", "bridge", "bridge", check_seed_02),
    TestDef("SEED-03", "Completed Claims (>= 4)", "seed", "bridge", "bridge", check_seed_03),
    TestDef("SEED-04", "Engine Wrapped Token Balances", "seed", "bridge", "bridge", check_seed_04),
    TestDef("SEED-05", "Engine USD Balances", "seed", "bridge", "bridge", check_seed_05),
    TestDef("SEED-06", "Pool Liquidity", "seed", "bridge", "bridge", check_seed_06),
    TestDef("SEED-07", "Pool Prices Initialised", "seed", "bridge", "bridge", check_seed_07),
    TestDef("SEED-08", "No Excessive Duplicate Claims", "seed", "bridge", "bridge", check_seed_08),
    TestDef("SEED-09", "LP Positions + Inventory", "seed", "bridge", "bridge", check_seed_09),
]
