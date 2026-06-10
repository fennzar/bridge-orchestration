"""Uniswap V4 pool reads + pushes — harvested from the retired l5_checks/engine_arb.py.

A pool push (a large directional swap) is how a scenario knocks the DEX price off its
oracle/native reference so the engine sees an arbitrage gap. Always run pool-push scenarios
under the `anvil_snapshot` fixture so the push is reverted after the test.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import test_common as _tc

from harness import chain

ROOT = Path(__file__).resolve().parents[3]   # .../bridge-orchestration
ANVIL_URL = _tc.ANVIL_URL
CTX = _tc.CTX
TK = _tc.TK
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


# ── the funded pusher (secrets stay in the gitignored .env) ───────────────────
def _parse_env(path: Path, keys: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if k in keys:
                out[k] = v.strip().strip('"').strip("'")
    except OSError:
        pass
    return out


def pusher() -> tuple[str | None, str | None]:
    """The funded EVM account `(pk, address)` a scenario uses to shove a pool off-peg.

    From the environment first (ENGINE_PK / ENGINE_ADDRESS, as the retired engine_arb harness
    used), falling back to the gitignored root `.env`. Returns (None, None) if unavailable — the
    caller should `pytest.skip` rather than fail, so a secret-less checkout degrades gracefully.
    """
    pk = os.environ.get("ENGINE_PK")
    addr = os.environ.get("ENGINE_ADDRESS")
    if not pk or not addr:
        vals = _parse_env(ROOT / ".env", ("ENGINE_PK", "ENGINE_ADDRESS"))
        pk = pk or vals.get("ENGINE_PK")
        addr = addr or vals.get("ENGINE_ADDRESS")
    return pk, addr


def token_address(symbol: str) -> str | None:
    """Resolve a token symbol (e.g. 'wZSD', 'USDT') to its EVM address from config."""
    return TK.get(symbol)


def token_decimals(symbol: str) -> int | None:
    """Token decimals from config (wZ* = 12, USDT = 6, USDC = 6). None if unknown."""
    for fname in ("config/addresses.json", "config/addresses.local.json"):
        p = ROOT / fname
        if p.exists():
            tok = json.loads(p.read_text()).get("tokens", {}).get(symbol)
            if tok and "decimals" in tok:
                return int(tok["decimals"])
    return None


def move_price(pool_name: str, sell_currency0: bool, amount_atomic: int,
               pk: str, receiver: str) -> tuple[str | None, str | None]:
    """Push `pool_name`'s price by selling one side. `sell_currency0=True` sells currency0
    (its price falls); False sells currency1 (currency0's price rises). Approves the input
    token to the SwapRouter first. Returns (txhash, err)."""
    state, err = load_pool(pool_name)
    if err or not state:
        return None, err or "no pool state"
    input_token = state["currency0"] if sell_currency0 else state["currency1"]
    _, aerr = approve(input_token, CTX.get("SwapRouter", ""), pk)
    if aerr:
        return None, f"approve failed: {aerr}"
    return push(amount_atomic, sell_currency0, state, pk, receiver)


def affordable_push(symbol: str, account: str, desired_tokens: int) -> tuple[int | None, str | None]:
    """How big a push of `symbol` (atomic) `account` can fund, capped at `desired_tokens`.

    The pusher is the LIVE engine wallet (ENGINE_ADDRESS), whose balance the engine itself spends,
    so it can sit just under a fixed target (observed: 9999.99 USDT vs a 10_000 target, 18088 wZSD
    vs 20_000). Rather than skip on a hair, push `min(desired, 95% of balance)` — but only if that's
    at least half the desired size, so the move still clears the trigger band. Returns
    (amount_atomic, None) to push, or (None, reason) for the caller to `pytest.skip`.
    """
    addr = token_address(symbol)
    dec = token_decimals(symbol) or 12
    if not addr:
        return None, f"no address for {symbol}"
    bal, err = balance_of(addr, account)
    if err or bal is None:
        return None, f"balanceOf {symbol} failed: {err}"
    desired = desired_tokens * (10 ** dec)
    amount = min(desired, (bal * 95) // 100)
    if amount < desired // 2:
        return None, (f"pusher holds {bal / 10 ** dec:.2f} {symbol} — too little to fund a "
                      f"meaningful push (need ≥ {desired_tokens / 2:.0f})")
    return amount, None


def currency_is(pool_state: dict, symbol: str) -> str | None:
    """Return 'currency0'/'currency1' for the slot holding `symbol`'s token, else None."""
    addr = (token_address(symbol) or "").lower()
    if not addr:
        return None
    for slot in ("currency0", "currency1"):
        if (pool_state.get(slot) or "").lower() == addr:
            return slot
    return None
