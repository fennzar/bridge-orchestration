"""The Zephyr conversion gate table — the protocol's OWN rules, as a pure oracle.

This is the authoritative reference the engine's `reserve.policy` model is checked against.
Every rule here is transcribed from the CODE-VERIFIED protocol doc and cited inline; if the
daemon's behaviour and this table ever disagree, the table is wrong and must be re-grounded —
NOT the daemon. (Source: docs/protocol/zephyr-reference.md §"Conversion gates", lines 89-104,
itself cited to the Zephyr consensus code.)

Units: reserve ratio as a raw float where 4.0 == 400% (matches daemon `get_reserve_info`
`reserve_ratio`/`reserve_ratio_ma` and the engine's `reserveRatio`). Constants:
  RESERVE_RATIO_MIN = 400%  (gates MINT_STABLE, REDEEM_RESERVE)
  RESERVE_RATIO_MAX = 800%  (caps MINT_RESERVE)
  YIELD_RSV_MIN     = 200%  (yield reward halts at/below this)

A scenario settles the chain to a market state, MEASURES (rr, ma, circulating, reserves) from
the daemon, asks this table "does the protocol allow X?", asks the engine (`/api/runtime`
`enabled`) "do you think X is allowed?", and asserts they agree. Divergence = a gate the engine
mis-models — tagged to INV-17.
"""
from __future__ import annotations

RR_MIN = 4.0   # 400% — RESERVE_RATIO_MIN
RR_MAX = 8.0   # 800% — RESERVE_RATIO_MAX
YIELD_MIN = 2.0  # 200% — YIELD_RSV_MIN
BOOTSTRAP_ZSD_CIRC = 100.0  # MINT_RESERVE bootstrap exception threshold (whole ZSD)


def mint_stable_allowed(rr: float, ma: float) -> bool:
    """ZEPH → ZSD (MINT_STABLE): RR_spot ≥ 400% AND RR_MA ≥ 400%."""
    return rr >= RR_MIN and ma >= RR_MIN


def redeem_stable_allowed(reserve_assets: float) -> bool:
    """ZSD → ZEPH (REDEEM_STABLE): allowed whenever reserve assets > 0 — NO reserve-ratio floor."""
    return reserve_assets > 0


def mint_reserve_allowed(rr: float, ma: float, zsd_circulating: float) -> bool:
    """ZEPH → ZRS (MINT_RESERVE): RR_spot < 800% AND RR_MA < 800% — NO lower floor;
    bootstrap exception: always allowed while circulating ZSD < 100."""
    if zsd_circulating < BOOTSTRAP_ZSD_CIRC:
        return True
    return rr < RR_MAX and ma < RR_MAX


def redeem_reserve_allowed(rr: float, ma: float) -> bool:
    """ZRS → ZEPH (REDEEM_RESERVE): RR_spot ≥ 400% AND RR_MA ≥ 400%."""
    return rr >= RR_MIN and ma >= RR_MIN


def yield_active(rr: float, ma: float) -> bool:
    """ZSD → ZYS yield reward accrues only while RR_spot > 200% AND RR_MA > 200%
    (halts when spot OR MA ≤ 200%)."""
    return rr > YIELD_MIN and ma > YIELD_MIN


def protocol_mode(rr: float) -> str:
    """The protocol regime by spot RR alone, for orientation in scenarios:
    normal (≥400%) · defensive (≥200%) · crisis (<200%)."""
    if rr >= RR_MIN:
        return "normal"
    if rr >= YIELD_MIN:
        return "defensive"
    return "crisis"
