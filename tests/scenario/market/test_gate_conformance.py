"""MKT-GATE-CONFORM — does the engine's gate model match the PROTOCOL's gate table?

The engine decides, per market state, whether a native conversion is allowed
(`reserve.policy.<asset>.<mintable|redeemable>`, surfaced as `/api/runtime` `enabled`). If that
model disagrees with what the daemon will actually accept, the engine either (a) emits a plan
whose conversion leg the daemon REJECTS → a doomed tx that can strand funds mid-arb, or (b)
needlessly refuses safe conversions. Either is an INV-17 break.

Method (self-grounding — assumes NOTHING about the price→RR map):
  1. settle the oracle to land a target regime, then MEASURE (rr_spot, rr_ma, circulating, reserves)
     from the daemon's own `get_reserve_info`.
  2. ask the PROTOCOL oracle (market/protocol_gates.py, transcribed from zephyr-reference.md) what
     it allows at those measured values.
  3. ask the ENGINE (`/api/runtime` `enabled`) what it thinks.
  4. assert they agree.
If the intended regime wasn't reached (seed-dependent), the test skips loudly rather than lying.

CODE-VERIFIED divergence (the headline red): engine `zrs.mintable` (reserve.ts:155-158) is
`rr≥4 ∧ ma≥4 ∧ rr≤8 ∧ ma≤8` — it adds a 400% LOWER floor the protocol's MINT_RESERVE does NOT
have (protocol: `rr<800 ∧ ma<800`, plus a bootstrap exception). Below 400% the protocol ALLOWS
ZRS mint; the engine blocks it. That cell is tagged @known_gap(INV-17).
"""
from __future__ import annotations

import pytest

from harness import chain, control, engine
from market import protocol_gates as G

pytestmark = [pytest.mark.needs_stack, pytest.mark.inv("INV-17")]


# ── measurement helpers ───────────────────────────────────────────────────────
def _measure() -> dict:
    """Snapshot the daemon's gate inputs (raw RR units: 4.0 == 400%)."""
    rr, _ = chain.reserve_ratio()
    ma, _ = chain.reserve_ratio_ma()
    circ = chain.circulating()
    return {"rr": rr, "ma": ma, "zsd_circ": circ.get("ZSD"), "zrs_circ": circ.get("ZRS")}


def _engine_allows(op_from: str, op_to: str) -> bool | None:
    resp, err = engine.runtime(op="auto", frm=op_from, to=op_to)
    assert not err, f"/api/runtime {op_from}->{op_to} errored: {err}"
    assert engine.runtime_operation(resp) is not None, f"engine resolved no op for {op_from}->{op_to}: {resp}"
    return engine.runtime_enabled(resp)


def _require_regime(m: dict, *, lo: float | None = None, hi: float | None = None) -> None:
    """Skip (don't lie) if the chain didn't actually land the regime this case needs."""
    rr = m["rr"]
    if rr is None or m["ma"] is None:
        pytest.skip(f"could not measure RR/MA from daemon: {m}")
    if lo is not None and rr < lo:
        pytest.skip(f"RR {rr:.2f} below intended floor {lo} — seed/price didn't land the regime")
    if hi is not None and rr > hi:
        pytest.skip(f"RR {rr:.2f} above intended ceiling {hi} — seed/price didn't land the regime")


# ── ZEPH → ZSD (MINT_STABLE) — engine model MATCHES protocol (expected GREEN) ──
def test_mkt_gate_conform_zsd_mint_normal(clean_market):
    """At high RR (normal), both protocol and engine allow ZEPH→ZSD."""
    control.settle_price(control.PRICE_HIGH_RR)
    m = _measure()
    _require_regime(m, lo=G.RR_MIN)
    proto = G.mint_stable_allowed(m["rr"], m["ma"])
    assert proto is True
    assert _engine_allows("ZEPH.n", "ZSD.n") == proto


def test_mkt_gate_conform_zsd_mint_defensive(clean_market):
    """Below 400% (defensive), the protocol blocks MINT_STABLE and so does the engine."""
    control.settle_price(control.PRICE_DEFENSIVE)
    m = _measure()
    _require_regime(m, hi=G.RR_MIN - 0.05)  # need to be genuinely under 400%
    proto = G.mint_stable_allowed(m["rr"], m["ma"])
    assert proto is False
    assert _engine_allows("ZEPH.n", "ZSD.n") == proto


# ── ZEPH → ZRS (MINT_RESERVE) — normal regime MATCHES (expected GREEN) ─────────
def test_mkt_gate_conform_zrs_mint_normal(clean_market):
    """In [400%, 800%) both allow ZEPH→ZRS."""
    control.settle_price(control.PRICE_HIGH_RR)
    m = _measure()
    _require_regime(m, lo=G.RR_MIN, hi=G.RR_MAX - 0.01)
    proto = G.mint_reserve_allowed(m["rr"], m["ma"], m["zsd_circ"] or 0.0)
    assert proto is True
    assert _engine_allows("ZEPH.n", "ZRS.n") == proto


# ── ZEPH → ZRS below the 400% floor — DIVERGENCE CLOSED (promoted to GREEN, INV-17) ──
def test_mkt_gate_conform_zrs_mint_below_floor(clean_market):
    """Between 200% and 400%: protocol allows ZEPH→ZRS (rr<800, no floor) and the engine now agrees.

    MINT_RESERVE has no 400% lower floor — only the 800% cap plus the bootstrap exception. The engine
    previously added a spurious `rr≥4` floor; reserve.ts (`mintReserveOk`) drops it, so below 400%
    the engine returns True, matching the protocol. Robust to MA lag: as long as MA stays under 800%,
    both stay True. (Promoted from @known_gap once reserve.ts was fixed — INV-17.)
    """
    control.settle_price(control.PRICE_DEFENSIVE)
    m = _measure()
    _require_regime(m, lo=G.YIELD_MIN, hi=G.RR_MIN - 0.05)
    if (m["ma"] or 0) >= G.RR_MAX:
        pytest.skip(f"MA {m['ma']} ≥ 800% — protocol would also block; can't isolate the floor gap")
    proto = G.mint_reserve_allowed(m["rr"], m["ma"], m["zsd_circ"] or 0.0)
    assert proto is True, "protocol should allow ZRS mint below 400% (no floor)"
    assert _engine_allows("ZEPH.n", "ZRS.n") == proto  # engine now returns True → green


# ── ZRS → ZEPH (REDEEM_RESERVE) — engine model MATCHES protocol (expected GREEN) ─
def test_mkt_gate_conform_zrs_redeem_normal(clean_market):
    control.settle_price(control.PRICE_HIGH_RR)
    m = _measure()
    _require_regime(m, lo=G.RR_MIN)
    proto = G.redeem_reserve_allowed(m["rr"], m["ma"])
    assert proto is True
    assert _engine_allows("ZRS.n", "ZEPH.n") == proto


def test_mkt_gate_conform_zrs_redeem_defensive(clean_market):
    """Below 400% the protocol blocks REDEEM_RESERVE and so does the engine."""
    control.settle_price(control.PRICE_DEFENSIVE)
    m = _measure()
    _require_regime(m, hi=G.RR_MIN - 0.05)
    proto = G.redeem_reserve_allowed(m["rr"], m["ma"])
    assert proto is False
    assert _engine_allows("ZRS.n", "ZEPH.n") == proto


# ── ZSD → ZEPH (REDEEM_STABLE) — engine says always-true; protocol gates on reserves>0 ─
def test_mkt_gate_conform_zsd_redeem(clean_market):
    """With reserves present (devnet baseline), protocol allows REDEEM_STABLE and engine agrees.

    The engine models this as unconditionally `true` (reserve.ts:153) while the protocol requires
    `reserve assets > 0`. That divergence only bites when reserves are fully drained — NOT reachable
    by an oracle price move, so it is covered by the pure LE-CONFORM unit test, not here. This live
    case stays green at the baseline.
    """
    control.settle_price(control.PRICE_HIGH_RR)
    m = _measure()
    _require_regime(m, lo=G.YIELD_MIN)  # any non-crisis baseline
    reserve_assets = (m["zrs_circ"] or 0.0)  # ZRS circulating proxies "reserve assets exist"
    proto = G.redeem_stable_allowed(reserve_assets)
    assert proto is True, "baseline devnet should have reserves > 0"
    assert _engine_allows("ZSD.n", "ZEPH.n") == proto
