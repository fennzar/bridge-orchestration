"""MKT-ARB-DETECT / MKT-APPROVAL-RRMODE — the engine reads a market move correctly.

ARB-DETECT: shove a DEX pool off its native/oracle reference and confirm the engine's arbitrage
analysis (`/api/arbitrage/analysis`) sees the gap with the RIGHT SIGN — selling wZSD into the
wZSD/USDT pool drops the DEX price → the engine must report `evm_discount` (gapBps falls); buying
wZSD raises it → `evm_premium`. If the engine mis-signs the gap it would arb the wrong way.

APPROVAL-RRMODE: the engine's auto-execute gate (`shouldAutoExecuteForRRMode`,
arbitrage.approval.ts) must tighten as the reserve ratio falls — in defensive mode (RR 200-400%)
ZRS opportunities are NOT auto-executable. Observed via `/api/arbitrage/plans` auto-exec filter.

Both expected GREEN — they prove the engine reacts to market dynamics correctly. Pool pushes run
under `anvil_snapshot` so they revert; they need the funded ENGINE_PK (skip if absent).
"""
from __future__ import annotations

import pytest

from harness import control, engine, pool

pytestmark = [pytest.mark.needs_stack, pytest.mark.inv("INV-14")]

PUSH_TOKENS = 10_000  # large enough to move price well past the trigger band


def _asset_gap(asset: str) -> tuple[float | None, str | None]:
    """(gapBps, direction) for an asset from /api/arbitrage/analysis."""
    resp, err = engine.analysis()
    assert not err, f"/api/arbitrage/analysis errored: {err}"
    for a in (resp or {}).get("assets", []):
        if a.get("asset") == asset:
            return a.get("gapBps"), a.get("direction")
    return None, None


@pytest.mark.parametrize(
    "label,sell_wzsd,expected_dir,sign",
    [
        ("discount", True, "evm_discount", -1),   # sell wZSD → DEX price down
        ("premium", False, "evm_premium", +1),    # sell USDT → DEX price up
    ],
    ids=["discount", "premium"],
)
def test_mkt_arb_detect_zsd(anvil_snapshot, label, sell_wzsd, expected_dir, sign):
    """A wZSD/USDT push makes the engine report the correctly-signed ZSD gap."""
    pk, addr = pool.pusher()
    if not pk or not addr:
        pytest.skip("ENGINE_PK/ENGINE_ADDRESS unavailable — can't fund a pool push")

    state, err = pool.load_pool("wZSD-USDT")
    if err or not state:
        pytest.skip(f"wZSD-USDT pool not in config: {err}")

    # Fundability: size the push to what the pusher (live engine wallet) actually holds.
    in_symbol = "wZSD" if sell_wzsd else "USDT"
    need, ferr = pool.affordable_push(in_symbol, addr, PUSH_TOKENS)
    if need is None:
        pytest.skip(f"{ferr} — can't fund the {label} push")

    before_gap, _ = _asset_gap("ZSD")
    _, perr = pool.move_price("wZSD-USDT", sell_currency0=sell_wzsd, amount_atomic=need,
                              pk=pk, receiver=addr)
    assert not perr, f"pool push failed: {perr}"

    after_gap, after_dir = _asset_gap("ZSD")
    assert before_gap is not None and after_gap is not None, "analysis returned no gapBps for ZSD"
    moved = after_gap - before_gap
    assert moved * sign > 0, (
        f"[{label}] gapBps moved {moved:+.1f} — wrong sign for a {label} push "
        f"(before {before_gap:.1f}, after {after_gap:.1f})"
    )
    # If the push cleared the trigger band, the labelled direction must show.
    assert after_dir in (expected_dir, "aligned"), (
        f"[{label}] engine direction {after_dir!r} != {expected_dir!r}"
    )


@pytest.mark.needs_reset
def test_mkt_approval_blocks_zrs_in_defensive(clean_market):
    """In defensive RR (<400%), no ZRS plan may be auto-executable (shouldAutoExecuteForRRMode
    blocks ZRS there). This is the engine correctly tightening with the market."""
    settled = control.settle_price(control.PRICE_DEFENSIVE)
    if settled is None:
        pytest.skip("RR never settled")
    if settled >= control.RR_NORMAL:
        pytest.skip(f"RR {settled:.2f} did not fall into defensive band")

    resp, err = engine.plans()
    assert not err, f"/api/arbitrage/plans errored: {err}"
    auto = engine.auto_executable_plans(resp or {})
    zrs_auto = [p for p in auto if str(p.get("asset", "")).upper() == "ZRS"]
    assert not zrs_auto, (
        f"engine marked {len(zrs_auto)} ZRS plan(s) auto-executable at defensive RR {settled:.2f} "
        "— shouldAutoExecuteForRRMode should block ZRS here"
    )


@pytest.mark.needs_reset
def test_mkt_approval_allows_in_normal(clean_market):
    """Sanity counter-test: in normal RR the auto-exec gate does NOT categorically block — if the
    market is aligned there simply are no plans, but the gate itself must not be the blocker."""
    settled = control.settle_price(control.PRICE_HIGH_RR)
    if settled is None or settled < control.RR_NORMAL:
        pytest.skip(f"RR {settled} not in normal band")
    ev, err = engine.evaluate()
    assert not err and ev, f"evaluate errored: {err}"
    assert engine.rr_mode(ev) == "normal", f"expected normal mode at RR {settled:.2f}"
