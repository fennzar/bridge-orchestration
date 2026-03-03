"""Layer 1: Constants, API wrappers, EVM reads, low-level pool swaps.

Imports from test_common only. No dependency on _pool, _patterns, or _funding.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

# Re-export core infrastructure from test_common
from test_common import (  # noqa: F401
    PASS, FAIL, BLOCKED, SKIP,
    ENGINE, ANVIL, API, ORACLE, OBOOK,
    NODE1_RPC, ANVIL_URL, ORACLE_URL, ORDERBOOK_URL,
    MINER_W,
    TK, CTX, ATOMIC,
    _get, _post, _jget, _jpost, _rpc, _eth_call, _cast, _get_rr,
    set_oracle_price, set_orderbook_spread, CleanupContext,
    probe_services,
    TestResult,
)

__all__ = [
    # test_common re-exports
    "PASS", "FAIL", "BLOCKED", "SKIP",
    "ENGINE", "ANVIL", "API", "ORACLE", "OBOOK",
    "NODE1_RPC", "ANVIL_URL", "ORACLE_URL", "ORDERBOOK_URL",
    "MINER_W",
    "TK", "CTX", "ATOMIC",
    "_get", "_post", "_jget", "_jpost", "_rpc", "_eth_call", "_cast", "_get_rr",
    "set_oracle_price", "set_orderbook_spread", "CleanupContext",
    "probe_services",
    "TestResult",
    # Own exports
    "ROOT",
    "ENGINE_ADDRESS", "ENGINE_PK",
    "TEST_WALLET_ADDRESS", "TEST_WALLET_PK",
    "SWAP_AMOUNT", "WAIT_SYNC", "WAIT_EXEC",
    "POOL_DIRECTION_INVERTED", "POOL_SWAP_OVERRIDES",
    "SEL_BALANCE_OF", "SEL_DECIMALS", "SEL_GET_SLOT0",
    "ZERO_HOOKS", "MAX_UINT256",
    "ASSET_POOL", "ASSET_THRESHOLD",
    "RR_MODE_TARGETS", "RR_MODE_PRICES_FALLBACK",
    "engine_evaluate", "engine_status", "engine_history",
    "engine_balances", "daemon_reserve_info", "engine_plans",
    "engine_runner_get", "engine_runner_set",
    "engine_queue", "engine_queue_action",
    "balance_of", "decimals_of", "get_pool_sqrt_price",
    "load_pool_config", "approve_token", "swap_pool",
    "EXEC_SWAP_AMOUNTS", "WAIT_EXEC_LONG", "WAIT_EXEC_POLL",
]

ROOT = Path(__file__).resolve().parent.parent.parent

# Ensure scripts/lib is importable (for seed_helpers)
_lib_dir = str(ROOT / "scripts" / "lib")
if _lib_dir not in sys.path:
    sys.path.insert(0, _lib_dir)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENGINE_ADDRESS = os.environ.get("ENGINE_ADDRESS", "")
ENGINE_PK = os.environ.get("ENGINE_PK", "")

# Test wallet — dedicated account for pool pushes in EXEC tests.
# NOT deployer, NOT bridge signer, NOT engine.  Pre-funded with ETH by Anvil.
TEST_WALLET_ADDRESS = os.environ.get("TEST_USER_1_ADDRESS", "")
TEST_WALLET_PK = os.environ.get("TEST_USER_1_PK", "")

# Pool swap defaults
SWAP_AMOUNT = 8_000_000_000_000_000  # 8000 tokens * 1e12 (for 12-decimal pools)
WAIT_SYNC = 8       # seconds for watchers to pick up on-chain changes
WAIT_EXEC = 15      # seconds for engine loop to detect + execute

# Pools where the ASSET is currency0 (not currency1).
# In these pools, selling currency0 makes the asset CHEAPER (discount),
# so the premium/discount → zeroForOne mapping must be inverted.
# Normal pools: premium → zeroForOne=True (sell c0 quote → c1 asset expensive)
# Inverted pools: premium → zeroForOne=False (sell c1 quote → c0 asset expensive)
POOL_DIRECTION_INVERTED = {"wZSD-USDT"}

# Per-pool per-direction swap amounts — keyed by (pool_name, direction)
# Calibrated for: enough price impact (>threshold bps) without draining pool
# Key insight: selling wZSD is ~5x less efficient than selling wZEPH at moving price
POOL_SWAP_OVERRIDES: dict[tuple[str, str], int] = {
    # ---- wZSD-USDT (inverted: c0=wZSD is the asset) ----
    # premium: sell USDT (c1, 6 decimals) to make wZSD expensive
    ("wZSD-USDT", "premium"):   9_500_000_000,           # 9.5K USDT (6 decimals)
    # discount: sell wZSD (c0, 12 decimals) — need more than default for 12bps threshold
    ("wZSD-USDT", "discount"):  10_000_000_000_000_000,  # 10K wZSD

    # ---- wZEPH-wZSD: premium sells wZSD (quote), need more for thick pool ----
    ("wZEPH-wZSD", "premium"):  13_000_000_000_000_000,  # 13K wZSD

    # ---- wZYS-wZSD: premium sells wZSD (quote) ----
    ("wZYS-wZSD", "premium"):   13_000_000_000_000_000,  # 13K wZSD
}

# EVM selectors
SEL_BALANCE_OF = "0x70a08231"
SEL_DECIMALS = "0x313ce567"
SEL_GET_SLOT0 = "0xc815641c"
ZERO_HOOKS = "0x0000000000000000000000000000000000000000"
MAX_UINT256 = str(2**256 - 1)

# Asset -> pool name mapping
ASSET_POOL = {
    "ZEPH": "wZEPH-wZSD",
    "ZSD":  "wZSD-USDT",
    "ZRS":  "wZRS-wZEPH",
    "ZYS":  "wZYS-wZSD",
}

# Asset -> trigger threshold in bps
ASSET_THRESHOLD = {
    "ZEPH": 100,
    "ZSD":  12,
    "ZRS":  100,
    "ZYS":  30,
}

# RR mode -> target RR values (prices computed dynamically from current state)
RR_MODE_TARGETS = {
    "normal":    5.0,    # Well above 4.0 threshold
    "defensive": 3.0,    # Between 2.0 and 4.0
    "crisis":    1.5,    # Below 2.0
    "high-rr":   9.0,    # Above 8.0
}

# Fallback prices if engine is unreachable (assumes fresh devnet ~5x RR)
RR_MODE_PRICES_FALLBACK = {
    "normal":    1.50,
    "defensive": 0.40,
    "crisis":    0.15,
    "high-rr":   3.00,
}

# Larger swap amounts for execution tests — need sufficient gap to exceed
# profitability threshold (fees ~190bps for ZEPH).
# Separate from POOL_SWAP_OVERRIDES to avoid changing calibration for detection/gate tests.
EXEC_SWAP_AMOUNTS: dict[tuple[str, str], int] = {
    ("wZEPH-wZSD", "premium"):  45_000_000_000_000_000,  # 45K wZSD for >200bps (fees ~190bps)
    ("wZEPH-wZSD", "discount"): 15_000_000_000_000_000,  # 15K wZEPH
    ("wZRS-wZEPH", "premium"):  13_000_000_000_000_000,  # 13K wZEPH
    ("wZRS-wZEPH", "discount"):  8_000_000_000_000_000,  # 8K wZRS
    ("wZYS-wZSD", "premium"):   13_000_000_000_000_000,  # 13K wZSD
    ("wZYS-wZSD", "discount"):   8_000_000_000_000_000,  # 8K wZYS
    ("wZSD-USDT", "premium"):   12_000_000_000,           # 12K USDT (6 decimals)
    ("wZSD-USDT", "discount"):  12_000_000_000_000_000,   # 12K wZSD
}
WAIT_EXEC_LONG = 90   # max seconds for multi-step execution
WAIT_EXEC_POLL = 5    # seconds between polls


# ===========================================================================
# Engine API
# ===========================================================================

def engine_evaluate(strategies: str = "arb") -> tuple[dict | None, str | None]:
    """GET /api/engine/evaluate?strategies=... Returns (parsed, error)."""
    return _jget(f"{ENGINE}/api/engine/evaluate?strategies={strategies}", timeout=15.0)


def engine_status() -> tuple[dict | None, str | None]:
    """GET /api/engine/status. Returns (parsed, error)."""
    return _jget(f"{ENGINE}/api/engine/status", timeout=10.0)


def engine_history(strategy: str | None = None, mode: str | None = None, limit: int = 50) -> tuple[dict | None, str | None]:
    """GET /api/engine/history. Returns (parsed, error)."""
    qs = f"limit={limit}"
    if strategy:
        qs += f"&strategy={strategy}"
    if mode:
        qs += f"&mode={mode}"
    return _jget(f"{ENGINE}/api/engine/history?{qs}", timeout=15.0)


def engine_balances() -> tuple[dict | None, str | None]:
    """GET /api/inventory/balances. Returns (parsed, error)."""
    return _jget(f"{ENGINE}/api/inventory/balances", timeout=10.0)


def daemon_reserve_info() -> tuple[Any, str | None]:
    """Query Zephyr daemon for get_reserve_info. Returns (result_dict, error)."""
    return _rpc(NODE1_RPC, "get_reserve_info")


def engine_plans() -> tuple[dict | None, str | None]:
    """GET /api/arbitrage/plans. Returns (parsed, error)."""
    return _jget(f"{ENGINE}/api/arbitrage/plans", timeout=15.0)


# ---------------------------------------------------------------------------
# Engine runner control (autoExecute, manualApproval, cooldown)
# ---------------------------------------------------------------------------

def engine_runner_get() -> tuple[dict | None, str | None]:
    """GET /api/engine/runner. Returns (parsed, error)."""
    return _jget(f"{ENGINE}/api/engine/runner", timeout=10.0)


def engine_runner_set(**kwargs: Any) -> tuple[dict | None, str | None]:
    """POST /api/engine/runner. Set autoExecute, manualApproval, cooldownMs.

    Returns (parsed, error).
    """
    return _jpost(f"{ENGINE}/api/engine/runner", kwargs, timeout=10.0)


def engine_queue(status: str | None = None, limit: int = 50) -> tuple[dict | None, str | None]:
    """GET /api/engine/queue. Returns (parsed, error)."""
    qs = f"limit={limit}"
    if status:
        qs += f"&status={status}"
    return _jget(f"{ENGINE}/api/engine/queue?{qs}", timeout=10.0)


def engine_queue_action(action: str, operation_id: str | None = None,
                        operation_ids: list[str] | None = None) -> tuple[dict | None, str | None]:
    """POST /api/engine/queue. Actions: approve, reject, cancel, retry.

    Returns (parsed, error).
    """
    body: dict[str, Any] = {"action": action}
    if operation_id:
        body["operationId"] = operation_id
    if operation_ids:
        body["operationIds"] = operation_ids
    return _jpost(f"{ENGINE}/api/engine/queue", body, timeout=10.0)


# ===========================================================================
# EVM reads
# ===========================================================================

def balance_of(token_addr: str, account: str) -> tuple[int | None, str | None]:
    """ERC-20 balanceOf. Returns (int, error)."""
    pad = account.lower().replace("0x", "").zfill(64)
    r, e = _eth_call(token_addr, SEL_BALANCE_OF + pad)
    if e or r is None:
        return None, e or "No response"
    try:
        return int(r, 16), None
    except (ValueError, TypeError):
        return None, f"Bad balanceOf: {r}"


def decimals_of(token_addr: str) -> tuple[int | None, str | None]:
    """ERC-20 decimals(). Returns (int, error)."""
    r, e = _eth_call(token_addr, SEL_DECIMALS)
    if e or r is None:
        return None, e or "No response"
    try:
        return int(r, 16), None
    except (ValueError, TypeError):
        return None, f"Bad decimals: {r}"


def get_pool_sqrt_price(pool_id: str) -> tuple[int | None, str | None]:
    """Read slot0 sqrtPriceX96 from StateView. Returns (int, error)."""
    sv = CTX.get("StateView")
    if not sv:
        return None, "StateView not in config"
    data = pool_id.replace("0x", "").zfill(64)
    r, err = _eth_call(sv, SEL_GET_SLOT0 + data)
    if err:
        return None, err
    if not r or len(r) < 66:
        return None, "empty slot0"
    try:
        return int(r[2:66], 16), None
    except (ValueError, TypeError):
        return None, "bad slot0"


# ===========================================================================
# Pool manipulation (low-level)
# ===========================================================================

def load_pool_config(pool_name: str) -> tuple[dict | None, str | None]:
    """Load pool state from addresses.json. Returns (state, error)."""
    for fname in ["config/addresses.json", "config/addresses.local.json"]:
        p = ROOT / fname
        if p.exists():
            data = json.loads(p.read_text())
            state = data.get("pools", {}).get(pool_name, {}).get("state", {})
            if state.get("poolId"):
                return state, None
    return None, f"Pool {pool_name} not found in config"


def approve_token(token_addr: str, spender: str, pk: str) -> tuple[str | None, str | None]:
    """ERC-20 approve(spender, MAX_UINT256). Returns (stdout, error)."""
    return _cast([
        "send", token_addr,
        "approve(address,uint256)", spender, MAX_UINT256,
        "--private-key", pk, "--rpc-url", ANVIL_URL,
    ], timeout=30.0)


def swap_pool(amount_in: int, zero_for_one: bool, pool_state: dict,
              pk: str, receiver: str) -> tuple[str | None, str | None]:
    """SwapRouter single pool swap. Returns (stdout, error)."""
    sr = CTX.get("SwapRouter")
    if not sr:
        return None, "SwapRouter not in config"
    pool_key = (
        f"({pool_state['currency0']},{pool_state['currency1']},"
        f"{pool_state['fee']},{pool_state['tickSpacing']},{ZERO_HOOKS})"
    )
    deadline = str(int(time.time()) + 600)
    zfo = "true" if zero_for_one else "false"
    return _cast([
        "send", sr,
        "swapExactTokensForTokens(uint256,uint256,bool,"
        "(address,address,uint24,int24,address),bytes,address,uint256)",
        str(amount_in), "0", zfo, pool_key, "0x", receiver, deadline,
        "--private-key", pk, "--rpc-url", ANVIL_URL,
    ], timeout=60.0)
