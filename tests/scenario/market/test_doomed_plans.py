"""MKT-NO-DOOMED-PLAN — the engine must not auto-execute a conversion the daemon will reject.

This is the money-critical half of gate-conformance, observed at the PLAN level. A multi-step arb
that opens fine but closes via a native conversion the protocol blocks at the current reserve ratio
is a *doomed plan*: the early legs move real funds (EVM swap, wrap) and then the closing native
mint/redeem reverts, stranding inventory on the wrong side. INV-17.

We don't trust a per-leg `op` field (the serialized plan is opaque, report.ts); we extract every
native `from→to` hop the plan would perform (harness `engine.native_conversions`) and check each
against the PROTOCOL gate table at the MEASURED reserve ratio. If any auto-executable plan contains
a protocol-blocked native hop, it is doomed.

Expected GREEN: the engine's `mint_stable` / `redeem_reserve` gates DO match the protocol, so it
should never emit such a plan. Left UNTAGGED on purpose — a red here is a real, launch-blocking
finding (the engine proposing a doomed tx), not a pre-known gap.
"""
from __future__ import annotations

import pytest

from harness import chain, control, engine
from market import protocol_gates as G

pytestmark = [pytest.mark.needs_stack, pytest.mark.needs_reset, pytest.mark.inv("INV-17")]


def _measure() -> dict:
    rr, _ = chain.reserve_ratio()
    ma, _ = chain.reserve_ratio_ma()
    circ = chain.circulating()
    return {"rr": rr, "ma": ma, "zsd_circ": circ.get("ZSD") or 0.0, "zrs_circ": circ.get("ZRS") or 0.0}


def _protocol_allows(pair: tuple[str, str], m: dict) -> bool | None:
    """Protocol verdict for a native hop at measured market state. None = not a gated conversion
    we model (then it's not our concern here)."""
    rr, ma = m["rr"], m["ma"]
    if rr is None or ma is None:
        return None
    return {
        ("ZEPH.n", "ZSD.n"): G.mint_stable_allowed(rr, ma),
        ("ZEPH.n", "ZRS.n"): G.mint_reserve_allowed(rr, ma, m["zsd_circ"]),
        ("ZRS.n", "ZEPH.n"): G.redeem_reserve_allowed(rr, ma),
        ("ZSD.n", "ZEPH.n"): G.redeem_stable_allowed(m["zrs_circ"]),
        ("ZSD.n", "ZYS.n"): G.yield_active(rr, ma),
    }.get(pair)


def _doomed_hops(m: dict):
    """Yield (plan_label, hop) for every auto-executable plan hop the protocol would reject now."""
    resp, err = engine.plans()
    assert not err, f"/api/arbitrage/plans errored: {err}"
    for plan in engine.auto_executable_plans(resp or {}):
        label = f"{plan.get('asset','?')}/{plan.get('direction','?')}"
        for hop in engine.native_conversions(plan):
            if _protocol_allows(hop, m) is False:
                yield label, hop


def test_mkt_no_doomed_plan_defensive(clean_market):
    """At a defensive RR (<400%), no auto-executable plan may close via MINT_STABLE/REDEEM_RESERVE
    (both blocked below 400%). The engine should withhold or re-route such plans."""
    control.settle_price(control.PRICE_DEFENSIVE)
    m = _measure()
    if m["rr"] is None:
        pytest.skip("daemon RR unreadable")
    if m["rr"] >= G.RR_MIN:
        pytest.skip(f"RR {m['rr']:.2f} did not fall below 400% — can't exercise the doomed path")

    doomed = list(_doomed_hops(m))
    assert not doomed, (
        f"engine would auto-execute protocol-blocked native hop(s) at RR {m['rr']:.2f}: "
        + "; ".join(f"{lbl}:{frm}->{to}" for lbl, (frm, to) in doomed)
    )


def test_mkt_no_doomed_plan_high_rr_ceiling(clean_market):
    """At a very high RR (>800%), MINT_RESERVE is protocol-blocked (ZSD circulating ≥ 100). No
    auto-executable plan may close via ZEPH→ZRS mint up there."""
    control.settle_price(control.PRICE_HIGH_RR)
    m = _measure()
    if m["rr"] is None:
        pytest.skip("daemon RR unreadable")
    if m["rr"] <= G.RR_MAX or m["zsd_circ"] < G.BOOTSTRAP_ZSD_CIRC:
        pytest.skip(
            f"RR {m['rr']:.2f} not above 800% (or bootstrap active, ZSD circ {m['zsd_circ']:.0f}) "
            "— can't exercise the MINT_RESERVE ceiling"
        )
    doomed = list(_doomed_hops(m))
    assert not doomed, (
        f"engine would auto-execute protocol-blocked ZRS mint above the 800% ceiling: "
        + "; ".join(f"{lbl}:{frm}->{to}" for lbl, (frm, to) in doomed)
    )
