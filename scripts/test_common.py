"""Shared test infrastructure for L1-L4 runners.

Provides HTTP helpers, service probes, oracle control, colored output,
and JSON reporting. Stdlib-only (no third-party deps).
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time as _time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, TypedDict
from urllib.error import HTTPError
from urllib.request import Request, urlopen

# ── Result Types ──────────────────────────────────────────────────────────

PASS = "PASS"
FAIL = "FAIL"
BLOCKED = "BLOCKED"
SKIP = "SKIP"

ResultStatus = Literal["PASS", "FAIL", "BLOCKED", "SKIP"]


class _TestResultOptional(TypedDict, total=False):
    module: str
    category: str


class TestResult(_TestResultOptional):
    test_id: str
    result: str
    detail: str


@dataclass
class ExecutionResult:
    test_id: str
    result: str  # PASS / FAIL / BLOCKED / SKIP
    detail: str
    level: str   # L1..L4
    lane: str
    priority: str


# ── Load .env (stdlib-only, no dotenv dependency) ────────────────────────

ROOT = Path(__file__).resolve().parent.parent

_env_file = ROOT / ".env"
if _env_file.exists():
    import re as _re
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _key, _, _val = _line.partition("=")
        _key = _key.strip()
        _val = _val.strip().strip("'\"")
        # Expand ${VAR} and $VAR references
        _val = _re.sub(
            r"\$\{([^}]+)\}|\$([A-Za-z_][A-Za-z0-9_]*)",
            lambda m: os.environ.get(m.group(1) or m.group(2), ""),
            _val,
        )
        if _key and _key not in os.environ:
            os.environ[_key] = _val

# ── Constants ─────────────────────────────────────────────────────────────

# Ports (DEVNET defaults, overridable via env)
NODE1_RPC_PORT = int(os.environ.get("DEVNET_NODE1_RPC", "47767"))
NODE2_RPC_PORT = int(os.environ.get("DEVNET_NODE2_RPC", "47867"))
ORACLE_PORT = int(os.environ.get("DEVNET_ORACLE_PORT", "5555"))
ORDERBOOK_PORT = int(os.environ.get("FAKE_ORDERBOOK_PORT", "5556"))
GOV_WALLET_PORT = int(os.environ.get("DEVNET_GOV_WALLET_RPC", "48769"))
MINER_WALLET_PORT = int(os.environ.get("DEVNET_MINER_WALLET_RPC", "48767"))
TEST_WALLET_PORT = int(os.environ.get("DEVNET_TEST_WALLET_RPC", "48768"))
BRIDGE_WALLET_PORT = int(os.environ.get("DEVNET_BRIDGE_WALLET_RPC", "48770"))

# Service URLs
NODE1_RPC = f"http://127.0.0.1:{NODE1_RPC_PORT}/json_rpc"
NODE2_RPC = f"http://127.0.0.1:{NODE2_RPC_PORT}/json_rpc"
ORACLE_URL = f"http://127.0.0.1:{ORACLE_PORT}"
ORDERBOOK_URL = f"http://127.0.0.1:{ORDERBOOK_PORT}"
GOV_W = f"http://127.0.0.1:{GOV_WALLET_PORT}/json_rpc"
MINER_W = f"http://127.0.0.1:{MINER_WALLET_PORT}/json_rpc"
TEST_W = f"http://127.0.0.1:{TEST_WALLET_PORT}/json_rpc"
BRIDGE_W = f"http://127.0.0.1:{BRIDGE_WALLET_PORT}/json_rpc"
ANVIL_URL = "http://127.0.0.1:8545"
BRIDGE_API_URL = "http://127.0.0.1:7051"
ENGINE_URL = "http://127.0.0.1:7000"
BRIDGE_WEB_URL = "http://127.0.0.1:7050"

DEPLOYED_ADDRESSES_FILE = ROOT / "deployed-addresses.json"

# Token + contract addresses — loaded dynamically from config/addresses.json
# (falls back to empty if file not found; tests that need addresses will FAIL
#  visibly rather than pass against stale hardcoded values)
def _load_addresses() -> tuple[dict[str, str], dict[str, str]]:
    """Load token and contract addresses from config/addresses.json."""
    addr_file = ROOT / "config" / "addresses.json"
    if not addr_file.exists():
        return {}, {}
    try:
        data = json.loads(addr_file.read_text())
        tokens = {k: v["address"] for k, v in data.get("tokens", {}).items() if "address" in v}
        # Map camelCase keys from JSON to PascalCase used by L5 tests
        _ctx_map = {
            "poolManager": "PoolManager",
            "positionManager": "PositionManager",
            "stateView": "StateView",
            "v4Quoter": "V4Quoter",
            "swapRouter": "SwapRouter",
            "permit2": "Permit2",
        }
        contracts: dict[str, str] = {}
        for k, v in data.get("contracts", {}).items():
            if isinstance(v, str):
                contracts[_ctx_map.get(k) or k] = v
        return tokens, contracts
    except Exception:
        return {}, {}

TK, CTX = _load_addresses()

ATOMIC = 1_000_000_000_000  # 1e12 — Zephyr uses 12 decimal places

# Short URL aliases (used by L5 modules)
API = BRIDGE_API_URL
ENGINE = ENGINE_URL
WEB = BRIDGE_WEB_URL
ANVIL = ANVIL_URL
ZNODE = NODE1_RPC
ORACLE = ORACLE_URL
OBOOK = ORDERBOOK_URL


@dataclass
class L5Result:
    """Result type for L5 edge-case checks (different fields from L1-L4)."""
    test_id: str
    result: str   # PASS / FAIL / BLOCKED
    detail: str
    lane: str
    status: str   # SCOPED-READY / SCOPED-EXPAND / SCOPED-TBC
    priority: str


# ── HTTP / RPC Helpers ────────────────────────────────────────────────────

def _get(url: str, timeout: float = 10.0) -> tuple[int | None, str | None, str | None]:
    """GET request. Returns (status, body, error)."""
    try:
        req = Request(url, method="GET")
        with urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace"), None
    except HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return e.code, body, str(e)
    except Exception as e:
        return None, None, str(e)


def _post(url: str, payload: Any, headers: dict[str, str] | None = None, timeout: float = 10.0) -> tuple[int | None, str | None, str | None]:
    """POST JSON request. Returns (status, body, error)."""
    try:
        hdrs = {"Content-Type": "application/json"}
        if headers:
            hdrs.update(headers)
        data = json.dumps(payload).encode()
        req = Request(url, method="POST", headers=hdrs, data=data)
        with urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", errors="replace"), None
    except HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        return e.code, body, str(e)
    except Exception as e:
        return None, None, str(e)


def _jget(url: str, timeout: float = 10.0) -> tuple[dict | None, str | None]:
    """GET + parse JSON. Returns (parsed, error)."""
    s, b, e = _get(url, timeout)
    if e and s is None:
        return None, e
    if b is None:
        return None, f"Empty response (HTTP {s})"
    try:
        return json.loads(b), None
    except Exception:
        return None, f"JSON parse error (HTTP {s})"


def _jpost(url: str, payload: Any, headers: dict[str, str] | None = None, timeout: float = 10.0) -> tuple[dict | None, str | None]:
    """POST JSON + parse response. Returns (parsed, error)."""
    s, b, e = _post(url, payload, headers, timeout)
    if e and s is None:
        return None, e
    try:
        return json.loads(b or "{}"), None
    except Exception:
        return None, f"JSON parse error (HTTP {s})"


def _rpc(url: str, method: str, params: Any = None, timeout: float = 10.0) -> tuple[Any, str | None]:
    """JSON-RPC call. Returns (result, error)."""
    payload = {"jsonrpc": "2.0", "id": "0", "method": method}
    if params:
        payload["params"] = params
    parsed, err = _jpost(url, payload, timeout=timeout)
    if err:
        return None, err
    if not parsed:
        return None, "Empty response"
    if "error" in parsed:
        return None, str(parsed["error"])
    return parsed.get("result"), None


def _eth_call(to: str, data: str, timeout: float = 10.0) -> tuple[str | None, str | None]:
    """eth_call to Anvil. Returns (hex_result, error)."""
    parsed, err = _jpost(
        ANVIL_URL,
        {"jsonrpc": "2.0", "method": "eth_call",
         "params": [{"to": to, "data": data}, "latest"], "id": 1},
        timeout=timeout,
    )
    if err:
        return None, err
    if not parsed:
        return None, "Empty response"
    if "error" in parsed:
        return None, parsed["error"].get("message", str(parsed["error"]))
    return parsed.get("result"), None


def _eth_code(addr: str):
    """eth_getCode on Anvil. Returns (code_hex, error)."""
    parsed, err = _jpost(
        ANVIL_URL,
        {"jsonrpc": "2.0", "method": "eth_getCode",
         "params": [addr, "latest"], "id": 1},
    )
    if err:
        return None, err
    return (parsed or {}).get("result"), None


def _cast(args: list[str], timeout: float = 15.0) -> tuple[str | None, str | None]:
    """Run foundry `cast` CLI. Returns (stdout, error)."""
    try:
        result = subprocess.run(
            ["cast"] + args,
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            return None, result.stderr.strip() or f"exit code {result.returncode}"
        return result.stdout.strip(), None
    except FileNotFoundError:
        return None, "cast not found (install foundry)"
    except subprocess.TimeoutExpired:
        return None, f"cast timed out after {timeout}s"
    except Exception as e:
        return None, str(e)


def _get_rr() -> tuple[float | None, str | None]:
    """Get current reserve ratio from Zephyr node. Returns (float, error)."""
    result, err = _rpc(NODE1_RPC, "get_reserve_info")
    if err:
        return None, err
    rr_str = (result or {}).get("reserve_ratio", "0")
    try:
        return float(rr_str), None
    except (ValueError, TypeError):
        return None, f"Bad reserve_ratio: {rr_str}"


# ── Service Probes ────────────────────────────────────────────────────────

def _tcp_probe(host: str, port: int, timeout: float = 2.0) -> bool:
    """Raw TCP connection check."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe_services() -> dict[str, bool]:
    """Probe all services. Returns dict of service_name -> up/down."""
    probes: dict[str, bool] = {}

    # Redis: raw TCP on 6380
    probes["redis"] = _tcp_probe("127.0.0.1", 6380)

    # Postgres: TCP on 5432
    probes["postgres"] = _tcp_probe("127.0.0.1", 5432)

    # Anvil: JSON-RPC
    try:
        parsed, err = _jpost(
            ANVIL_URL,
            {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1},
            timeout=3.0,
        )
        probes["anvil"] = err is None and parsed is not None and parsed.get("result") is not None
    except Exception:
        probes["anvil"] = False

    # Oracle
    try:
        s, _, _ = _get(f"{ORACLE_URL}/status", timeout=3.0)
        probes["oracle"] = s == 200
    except Exception:
        probes["oracle"] = False

    # Orderbook
    try:
        s, _, _ = _get(f"{ORDERBOOK_URL}/status", timeout=3.0)
        probes["orderbook"] = s == 200
    except Exception:
        probes["orderbook"] = False

    # Zephyr nodes
    for name, url in [("node1", NODE1_RPC), ("node2", f"http://127.0.0.1:{NODE2_RPC_PORT}/json_rpc")]:
        try:
            result, err = _rpc(url, "get_info", timeout=3.0)
            probes[name] = err is None and result is not None
        except Exception:
            probes[name] = False

    # Wallets
    for name, url in [("gov_wallet", GOV_W), ("miner_wallet", MINER_W), ("test_wallet", TEST_W), ("bridge_wallet", BRIDGE_W)]:
        try:
            result, err = _rpc(url, "get_version", timeout=3.0)
            probes[name] = err is None and result is not None
        except Exception:
            probes[name] = False

    # Bridge API
    try:
        s, _, _ = _get(f"{BRIDGE_API_URL}/health", timeout=3.0)
        probes["bridge_api"] = s == 200
    except Exception:
        probes["bridge_api"] = False

    # Bridge Web
    try:
        s, _, _ = _get(BRIDGE_WEB_URL, timeout=3.0)
        probes["bridge_web"] = s == 200
    except Exception:
        probes["bridge_web"] = False

    # Engine — use /api/engine/status which doesn't depend on daemon pricing
    try:
        s, _, _ = _get(f"{ENGINE_URL}/api/engine/status", timeout=3.0)
        probes["engine"] = s == 200
    except Exception:
        probes["engine"] = False

    return probes


# ── Oracle Control ────────────────────────────────────────────────────────

def set_oracle_price(usd: float) -> bool:
    """Set oracle price via fake oracle API. Returns success."""
    atomic = int(usd * ATOMIC)
    s, _, e = _post(f"{ORACLE_URL}/set-price", {"spot": atomic}, timeout=5.0)
    return s == 200


def set_orderbook_spread(bps: int) -> bool:
    """Set orderbook spread in basis points. Returns success."""
    s, _, e = _post(f"{ORDERBOOK_URL}/set-spread", {"spreadBps": bps}, timeout=5.0)
    return s == 200


class CleanupContext:
    """Context manager that restores oracle price and orderbook spread on exit."""

    def __init__(self, price_usd: float = 1.50, spread_bps: int = 50):
        self.price_usd = price_usd
        self.spread_bps = spread_bps

    def __enter__(self):
        return self

    def __exit__(self, *_):
        set_oracle_price(self.price_usd)
        set_orderbook_spread(self.spread_bps)


# ── Colored Terminal Output ───────────────────────────────────────────────

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
CYAN = "\033[0;36m"
NC = "\033[0m"

# Disable colors if not a TTY
if not sys.stdout.isatty():
    RED = GREEN = YELLOW = BLUE = CYAN = NC = ""


def print_result(r: ExecutionResult, verbose: bool = False) -> None:
    """Print a single test result."""
    color = {PASS: GREEN, FAIL: RED, BLOCKED: YELLOW, SKIP: YELLOW}.get(r.result, NC)
    print(f"{color}[{r.result}]{NC} {r.test_id}", end="")
    if verbose and r.detail:
        print(f": {r.detail}", end="")
    print()


def print_summary(results: list[ExecutionResult]) -> None:
    """Print colored summary of all results."""
    counts = {PASS: 0, FAIL: 0, BLOCKED: 0, SKIP: 0}
    for r in results:
        counts[r.result] = counts.get(r.result, 0) + 1

    print()
    print("===========================================")
    print("  Results")
    print("===========================================")
    print()
    print(f"  {GREEN}PASS:{NC} {counts[PASS]}")
    print(f"  {RED}FAIL:{NC} {counts[FAIL]}")
    if counts[BLOCKED]:
        print(f"  {YELLOW}BLOCKED:{NC} {counts[BLOCKED]}")
    if counts[SKIP]:
        print(f"  {YELLOW}SKIP:{NC} {counts[SKIP]}")
    print()


def write_json_report(path: str, results: list[ExecutionResult], probes: dict[str, bool]) -> None:
    """Write JSON report compatible with L5 format."""
    counts = {PASS: 0, FAIL: 0, BLOCKED: 0, SKIP: 0}
    for r in results:
        counts[r.result] = counts.get(r.result, 0) + 1

    payload = {
        "summary": {
            "pass": counts[PASS],
            "fail": counts[FAIL],
            "blocked": counts[BLOCKED],
            "skip": counts[SKIP],
        },
        "service_probes": probes,
        "results": [asdict(r) for r in results],
    }
    Path(path).write_text(json.dumps(payload, indent=2))
    print(f"Wrote JSON report: {path}")
