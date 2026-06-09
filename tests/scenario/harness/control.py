"""Market-state control plane — the knobs that drive a scenario.

Oracle price is the master knob: it moves spot, which moves the reserve ratio, which
flips the engine between normal/defensive/crisis. Pool pushes (harness/pool.py) move the
DEX side. Mining advances the Zephyr chain so oracle/reserve changes propagate.

Wraps the kept helpers in test_common + lib/seed_helpers; adds RR-targeting convenience.
"""
from __future__ import annotations

import time

import test_common as _tc

from harness import chain

# RR-mode boundaries the engine uses (src/domain/strategies/types.ts) — and the protocol
# gate boundaries (zephyr-reference.md: MINT_STABLE/REDEEM_RESERVE@400%, MINT_RESERVE@800%,
# yield-halt@200%). Scenarios assert the engine's view against the protocol's.
RR_NORMAL = 4.0       # >= 400%
RR_DEFENSIVE = 2.0    # >= 200%
RR_MAX = 8.0          # >= 800% — protocol blocks MINT_RESERVE above this

# Oracle prices that land the checkpoint chain (RR ~7.0 @ $1.50) in each regime. Approximate —
# scenarios should assert the *measured* RR after settling, not trust these blindly.
PRICE_HIGH_RR = 1.50      # ~700% normal
PRICE_NEAR_ZRS_GATE = 0.95  # ~450% just above the 400% gate
PRICE_DEFENSIVE = 0.75    # ~350% defensive
PRICE_CRISIS = 0.35       # ~150% crisis


def set_price(usd: float) -> bool:
    """Set the fake oracle spot price (DEVNET). Does not itself mine."""
    return _tc.set_oracle_price(usd)


def set_spread(bps: int) -> bool:
    return _tc.set_orderbook_spread(bps)


def oracle_spot_usd() -> float | None:
    parsed, err = _tc._jget(f"{_tc.ORACLE_URL}/status", timeout=5.0)
    if err or not parsed:
        return None
    try:
        return int(parsed.get("spot")) / _tc.ATOMIC
    except (TypeError, ValueError):
        return None


def mine(blocks: int = 5) -> None:
    """Advance the Zephyr chain (start/stop daemon mining). Irreversible — tests that call
    this must be marked @needs_reset."""
    from seed_helpers import mine_blocks
    mine_blocks(blocks)


def settle_price(usd: float, mine_blocks_count: int = 4, timeout: float = 60.0) -> float | None:
    """Set the oracle price, mine until the daemon's reserve_ratio reflects it, and return the
    settled RR. @needs_reset (mines). Returns None if it never settled."""
    set_price(usd)
    mine(mine_blocks_count)
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        rr, err = chain.reserve_ratio()
        if not err and rr is not None:
            last = rr
            return rr
        time.sleep(1)
    return last


def expected_mode(rr: float) -> str:
    """The engine's rrMode for a given reserve ratio (mirrors determineRRMode)."""
    if rr >= RR_NORMAL:
        return "normal"
    if rr >= RR_DEFENSIVE:
        return "defensive"
    return "crisis"
