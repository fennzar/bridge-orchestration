"""Uniswap V4 pool reads + pushes — harvested from the retired l5_checks/engine_arb.py.

A pool push (a large directional swap) is how a scenario knocks the DEX price off its
oracle/native reference so the engine sees an arbitrage gap. Always run pool-push scenarios
under the `anvil_snapshot` fixture so the push is reverted after the test.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import test_common as _tc

from harness import chain

ROOT = Path(__file__).resolve().parents[3]   # .../bridge-orchestration
ANVIL_URL = _tc.ANVIL_URL
CTX = _tc.CTX
ZERO_HOOKS = "0x0000000000000000000000000000000000000000"
MAX_UINT256 = str(2**256 - 1)
SEL_GET_SLOT0 = "0xc815641c"
SEL_BALANCE_OF = "0x70a08231"


def load_pool(pool_name: str) -> tuple[dict | None, str | None]:
    """Pool state (currency0/1, fee, tickSpacing, poolId) from config/addresses*.json."""
    for fname in ("config/addresses.json", "config/addresses.local.json"):
        p = ROOT / fname
        if p.exists():
            data = json.loads(p.read_text())
            state = data.get("pools", {}).get(pool_name, {}).get("state", {})
            if state.get("poolId"):
                return state, None
    return None, f"pool {pool_name} not found in config"


def sqrt_price_x96(pool_id: str) -> tuple[int | None, str | None]:
    state_view = CTX.get("StateView")
    if not state_view:
        return None, "StateView not in config"
    data = pool_id.replace("0x", "").zfill(64)
    r, err = _tc._eth_call(state_view, SEL_GET_SLOT0 + data)
    if err:
        return None, err
    if not r or len(r) < 66:
        return None, "empty slot0"
    try:
        return int(r[2:66], 16), None
    except (ValueError, TypeError):
        return None, "bad slot0"


def balance_of(token: str, account: str) -> tuple[int | None, str | None]:
    acct = account.lower().replace("0x", "").zfill(64)
    r, e = _tc._eth_call(token, SEL_BALANCE_OF + acct)
    if e or r is None:
        return None, e or "no response"
    try:
        return int(r, 16), None
    except (ValueError, TypeError):
        return None, f"bad balanceOf: {r}"


def approve(token: str, spender: str, pk: str) -> tuple[str | None, str | None]:
    return chain.cast([
        "send", token, "approve(address,uint256)", spender, MAX_UINT256,
        "--private-key", pk, "--rpc-url", ANVIL_URL,
    ])


def push(amount_in: int, zero_for_one: bool, pool_state: dict, pk: str,
         receiver: str) -> tuple[str | None, str | None]:
    """SwapRouter.swapExactTokensForTokens — a directional swap that moves the pool price.
    `zero_for_one=True` sells currency0 (price down); False sells currency1 (price up)."""
    swap_router = CTX.get("SwapRouter")
    if not swap_router:
        return None, "SwapRouter not in config"
    c0, c1 = pool_state["currency0"], pool_state["currency1"]
    fee, ts = pool_state["fee"], pool_state["tickSpacing"]
    pool_key = f"({c0},{c1},{fee},{ts},{ZERO_HOOKS})"
    deadline = str(int(time.time()) + 600)
    return chain.cast([
        "send", swap_router,
        "swapExactTokensForTokens(uint256,uint256,bool,"
        "(address,address,uint24,int24,address),bytes,address,uint256)",
        str(amount_in), "0", "true" if zero_for_one else "false",
        pool_key, "0x", receiver, deadline,
        "--private-key", pk, "--rpc-url", ANVIL_URL,
    ])
