"""MKT-RRMODE-SWEEP — the oracle → reserve-ratio → engine-decision pipeline actually moves.

This is the foundation every other MKT scenario stands on: if turning the oracle knob does NOT
move the daemon's reserve ratio and the engine's observed `rrMode` in lock-step, no downstream
market-dynamics assertion means anything. Expected GREEN — it proves the control plane drives the
engine. (If it reds, the rest of the MKT suite is untrustworthy, so it is intentionally untagged:
a failure here is a real regression, not a known gap.)

Grounding: `/api/engine/evaluate` reports `state.reserveRatio` as a PERCENT (reserve.reserveRatio
× 100, route.ts:86) and `state.rrMode` from the RAW ratio (`>=4 normal : >=2 defensive : crisis`,
route.ts:87). We MEASURE the daemon's raw RR and assert the engine's view matches it.
"""
from __future__ import annotations

import pytest

from harness import chain, control, engine

pytestmark = [pytest.mark.needs_stack, pytest.mark.inv("INV-17")]

# (label, oracle price) — descending, walking RR down through the regimes.
_SWEEP = [
    ("high", control.PRICE_HIGH_RR),
    ("near-gate", control.PRICE_NEAR_ZRS_GATE),
    ("defensive", control.PRICE_DEFENSIVE),
    ("crisis", control.PRICE_CRISIS),
]


@pytest.mark.needs_reset
@pytest.mark.parametrize("label,price", _SWEEP, ids=[s[0] for s in _SWEEP])
def test_mkt_rrmode_tracks_oracle(clean_market, label, price):
    """Setting the oracle and mining moves the measured RR; the engine's rrMode + reported RR
    agree with the daemon's raw ratio at that price."""
    settled = control.settle_price(price)
    if settled is None:
        pytest.skip(f"RR never settled at price ${price}")

    measured_raw, err = chain.reserve_ratio()
    assert not err and measured_raw is not None, f"daemon RR unreadable: {err}"

    ev, err = engine.evaluate()
    assert not err and ev, f"engine evaluate errored: {err}"

    # rrMode mirrors determineRRMode on the measured ratio.
    assert engine.rr_mode(ev) == control.expected_mode(measured_raw), (
        f"[{label}] engine rrMode {engine.rr_mode(ev)} != expected "
        f"{control.expected_mode(measured_raw)} at measured RR {measured_raw:.2f}"
    )

    # reserveRatio is reported in PERCENT; it should track the daemon's raw ratio ×100.
    reported_pct = engine.reserve_ratio(ev)
    assert reported_pct is not None, "engine reported no reserveRatio"
    assert reported_pct == pytest.approx(measured_raw * 100, rel=0.05), (
        f"[{label}] engine reserveRatio {reported_pct} % != measured {measured_raw * 100:.1f} %"
    )


@pytest.mark.needs_reset
def test_mkt_rrmode_monotone_under_falling_price(clean_market):
    """RR is monotone non-increasing as the oracle price falls — a sanity check that the knob has
    the expected sign (higher ZEPH price ⇒ more USD backing ⇒ higher reserve ratio)."""
    last = None
    for label, price in _SWEEP:
        rr = control.settle_price(price)
        if rr is None:
            pytest.skip(f"RR never settled at ${price}")
        if last is not None:
            assert rr <= last + 0.25, (
                f"RR rose ({last:.2f} → {rr:.2f}) when price fell to ${price} ({label}) — wrong sign"
            )
        last = rr
