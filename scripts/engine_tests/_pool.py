"""Layer 2: Pool push/restore, RR mode, sync waits, result extractors.

Imports from _api only. No dependency on _patterns or _funding.
"""
from __future__ import annotations

import subprocess
import time
from contextlib import contextmanager
from typing import Any, Generator

from _api import (
    ENGINE_ADDRESS, ENGINE_PK,
    POOL_DIRECTION_INVERTED, POOL_SWAP_OVERRIDES, SWAP_AMOUNT,
    ROOT,
    set_oracle_price, set_orderbook_spread,
    engine_evaluate,
    balance_of, load_pool_config, approve_token, swap_pool,
    CTX,
    RR_MODE_TARGETS, RR_MODE_PRICES_FALLBACK,
    WAIT_SYNC, WAIT_EXEC,
)

__all__ = [
    "push_pool_price", "restore_pool", "pool_push",
    "ZEPHYR_CLI", "mine_blocks", "price_for_target_rr",
    "set_rr_mode", "DEVNET_BASELINE_PRICE", "rr_mode",
    "EngineCleanupContext",
    "wait_sync", "wait_exec", "is_engine_running",
    "find_opportunity", "find_warnings", "get_gap_bps", "get_status_field",
]


# ===========================================================================
# Pool manipulation
# ===========================================================================

def push_pool_price(pool_name: str, direction: str, amount: int = 0,
                    pk: str = "", sender: str = "") -> tuple[dict | None, str | None]:
    """Push a pool's price in the given direction.

    Args:
        pool_name: e.g. "wZEPH-wZSD", "wZSD-USDT", "wZRS-wZEPH", "wZYS-wZSD"
        direction: "premium" or "discount" (relative to EVM)
        amount: atomic swap amount (0 = auto-select from POOL_SWAP_OVERRIDES or SWAP_AMOUNT)
        pk: private key for swap (default: ENGINE_PK)
        sender: address to swap from/to (default: ENGINE_ADDRESS)

    Returns:
        (restore_info, error) where restore_info is needed for restore_pool().
    """
    use_pk = pk or ENGINE_PK
    use_addr = sender or ENGINE_ADDRESS

    if amount <= 0:
        amount = POOL_SWAP_OVERRIDES.get((pool_name, direction), SWAP_AMOUNT)

    pool_state, err = load_pool_config(pool_name)
    if err or pool_state is None:
        return None, err or "Pool not found"
    sr = CTX.get("SwapRouter")
    if not sr:
        return None, "SwapRouter not in config"

    # Normal pools: premium -> zeroForOne=True (sell c0 quote -> c1 asset expensive)
    # Inverted pools (asset=c0): premium -> zeroForOne=False (sell c1 -> c0 asset expensive)
    if pool_name in POOL_DIRECTION_INVERTED:
        zero_for_one = direction != "premium"
    else:
        zero_for_one = direction == "premium"
    c0, c1 = pool_state["currency0"], pool_state["currency1"]
    sell_token = c0 if zero_for_one else c1
    buy_token = c1 if zero_for_one else c0

    # Approve both tokens for the swap router
    for token in (sell_token, buy_token):
        _, err = approve_token(token, sr, use_pk)
        if err:
            return None, f"Approve {token}: {err}"

    before, _ = balance_of(buy_token, use_addr)
    _, err = swap_pool(amount, zero_for_one, pool_state, use_pk, use_addr)
    if err:
        return None, f"Swap: {err}"
    after, _ = balance_of(buy_token, use_addr)

    restore_amount = 0
    if before is not None and after is not None:
        restore_amount = after - before

    return {
        "pool_name": pool_name,
        "pool_state": pool_state,
        "direction": direction,
        "restore_amount": restore_amount,
        "zero_for_one": zero_for_one,
        "pk": use_pk,
        "sender": use_addr,
    }, None


def restore_pool(info: dict | None) -> None:
    """Reverse a previous push_pool_price. Best-effort, never throws."""
    if not info or info.get("restore_amount", 0) <= 0:
        return
    try:
        swap_pool(
            info["restore_amount"],
            not info["zero_for_one"],
            info["pool_state"],
            info.get("pk", ENGINE_PK),
            info.get("sender", ENGINE_ADDRESS),
        )
    except Exception:
        pass  # Best-effort cleanup


@contextmanager
def pool_push(pool_name: str, direction: str, amount: int = 0) -> Generator[tuple[dict | None, str | None], None, None]:
    """Context manager: push pool price, yield restore_info, restore on exit.

    Amount defaults to 0, which uses POOL_SWAP_OVERRIDES or SWAP_AMOUNT fallback.

    Usage:
        with pool_push("wZEPH-wZSD", "premium") as info:
            if info is None:
                return result(BLOCKED, "pool push failed")
            wait_sync()
            # ... assertions ...
    """
    info, err = push_pool_price(pool_name, direction, amount)
    if err:
        yield None, err
        return
    try:
        yield info, None
    finally:
        restore_pool(info)


# ===========================================================================
# Mining and RR mode
# ===========================================================================

ZEPHYR_CLI = str(ROOT / "tools" / "zephyr-cli" / "cli")


def mine_blocks(seconds: int = 8) -> None:
    """Start mining for N seconds then stop.

    Required after oracle price changes -- the daemon only fetches
    the oracle when processing new blocks. Uses zephyr-cli for
    reliable wallet handling (auto-opens wallets, handles resets).
    """
    try:
        subprocess.run(
            [ZEPHYR_CLI, "mine", "start"],
            capture_output=True, text=True, timeout=10,
        )
        time.sleep(seconds)
        subprocess.run(
            [ZEPHYR_CLI, "mine", "stop"],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        pass  # Best-effort


def price_for_target_rr(target_rr: float) -> float | None:
    """Compute oracle price to achieve target RR based on current state.

    Uses linear approximation: RR is proportional to ZEPH price
    (reserves denominated in ZEPH, liabilities in USD).

    Args:
        target_rr: target reserve ratio in DECIMAL form (e.g. 3.0 for defensive)
                   Engine API reports percentage (475.89) -- we convert internally.

    Returns None if engine is unreachable.
    """
    eval_data, err = engine_evaluate()
    if err:
        return None
    state = (eval_data or {}).get("state", {})
    current_rr_pct = state.get("reserveRatio")  # percentage, e.g. 475.89
    current_price = state.get("zephPrice")
    if not current_rr_pct or not current_price or current_rr_pct <= 0:
        return None
    # Convert engine percentage -> decimal to match target_rr units
    current_rr = current_rr_pct / 100  # 475.89 -> 4.7589
    return max(0.001, current_price * target_rr / current_rr)


def set_rr_mode(mode: str) -> bool:
    """Set oracle price to target a specific RR mode, then mine blocks.

    For "normal" mode, uses baseline price directly (avoids drift from
    dynamic computation). For other modes, dynamically calibrates from
    current devnet state. Falls back to static prices if engine is unreachable.
    """
    target_rr = RR_MODE_TARGETS.get(mode)
    if target_rr is None:
        return False

    # Normal mode = just restore baseline (avoid cumulative drift)
    if mode == "normal":
        ok = set_oracle_price(DEVNET_BASELINE_PRICE)
        if ok:
            mine_blocks(5)
        return ok

    price = price_for_target_rr(target_rr)
    if price is None:
        price = RR_MODE_PRICES_FALLBACK.get(mode)
        if price is None:
            return False

    ok = set_oracle_price(price)
    if ok:
        mine_blocks(5)
    return ok


DEVNET_BASELINE_PRICE = 2.00  # Default oracle price for devnet


@contextmanager
def rr_mode(mode: str) -> Generator[bool, None, None]:
    """Context manager: set RR mode, restore oracle to baseline on exit.

    Saves baseline oracle price and restores it after the test,
    rather than dynamically computing a new restore price (which
    can drift from the devnet baseline).

    Usage:
        with rr_mode("defensive"):
            wait_sync()
            # ... assertions ...
    """
    ok = set_rr_mode(mode)
    try:
        yield ok
    finally:
        # Restore to known-good baseline, not dynamically computed
        set_oracle_price(DEVNET_BASELINE_PRICE)
        mine_blocks(8)


class EngineCleanupContext:
    """Like CleanupContext but mines blocks after restoring oracle price."""

    def __init__(self, price_usd: float = 2.00, spread_bps: int = 50):
        self.price_usd = price_usd
        self.spread_bps = spread_bps

    def __enter__(self) -> EngineCleanupContext:
        return self

    def __exit__(self, *_: Any) -> None:
        set_oracle_price(self.price_usd)
        set_orderbook_spread(self.spread_bps)
        mine_blocks(5)


def wait_sync(seconds: int = WAIT_SYNC) -> None:
    """Wait for watchers to sync state changes."""
    time.sleep(seconds)


def wait_exec(seconds: int = WAIT_EXEC) -> None:
    """Wait for engine loop to detect and execute."""
    time.sleep(seconds)


def is_engine_running() -> bool:
    """Check if engine-run overmind process is alive."""
    sock = str(ROOT / ".overmind-dev.sock")
    try:
        r = subprocess.run(
            ["overmind", "status", "-s", sock],
            capture_output=True, text=True, timeout=5,
        )
        for line in r.stdout.splitlines():
            if "engine-run" in line and "running" in line.lower():
                return True
        return False
    except Exception:
        return False


# ===========================================================================
# Result extractors
# ===========================================================================

def find_opportunity(eval_result: dict | None, asset: str, direction: str | None = None) -> tuple[list[dict], dict]:
    """Extract opportunities for an asset from evaluate response.

    Returns (matches_list, metrics_dict).
    """
    arb = (eval_result or {}).get("results", {}).get("arb", {})
    opps = arb.get("opportunities", [])
    matches = [
        o for o in opps
        if o.get("asset") == asset
        and (direction is None or o.get("direction") == direction)
    ]
    return matches, arb.get("metrics", {})


def find_warnings(eval_result: dict | None, strategy: str = "arb") -> list:
    """Extract warnings from evaluate response."""
    data = (eval_result or {}).get("results", {}).get(strategy, {})
    return data.get("warnings", [])


def get_gap_bps(eval_result: dict | None, asset: str) -> Any:
    """Extract gap bps for an asset from evaluate metrics."""
    arb = (eval_result or {}).get("results", {}).get("arb", {})
    metrics = arb.get("metrics", {})
    return metrics.get(f"{asset}_gapBps")


def get_status_field(status: dict | None, *path: str) -> Any:
    """Navigate nested status response. Returns value or None."""
    node: Any = status
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node
