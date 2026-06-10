"""MKT-PEG-DEFENSE — the peg keeper reacts when wZSD leaves its $1 peg.

The PegKeeper strategy (pegkeeper.ts) monitors the wZSD/USDT pool and, once the deviation clears
its `minDeviationBps` (30bps), emits a corrective opportunity (buy wZSD when cheap, sell when rich)
within the prevailing RR gates. This proves the engine defends the peg in response to a market
move — the strategy counterpart to ARB-DETECT. Expected GREEN.

Pushes run under `anvil_snapshot` (reverted after); need the funded ENGINE_PK (skip if absent).
"""
from __future__ import annotations

import pytest

from harness import engine, pool

pytestmark = [pytest.mark.needs_stack, pytest.mark.inv("INV-14")]

PUSH_TOKENS = 20_000  # well past the 30bps trigger on the wZSD/USDT pool


def _peg_opportunities() -> list[dict]:
    ev, err = engine.evaluate(strategies="peg")
    assert not err and ev, f"evaluate(peg) errored: {err}"
    return engine.opportunities(ev, strategy="peg")


def test_mkt_peg_quiet_when_on_peg(anvil_snapshot):
    """Baseline: with wZSD near $1, the peg keeper proposes nothing (or nothing urgent)."""
    opps = _peg_opportunities()
    # Not a hard zero — tiny residual deviation is fine; assert it isn't screaming.
    assert all(o.get("severity") != "critical" for o in opps), (
        f"peg keeper flagged a critical op while on-peg: {opps}"
    )


def test_mkt_peg_reacts_to_depeg(anvil_snapshot):
    """Drop wZSD below peg (sell wZSD into wZSD/USDT) → the peg keeper proposes a corrective op.

    The keeper widens its trigger by RR mode (getAdjustedThresholds: normal 30bps / defensive
    100bps / crisis 300bps). A ~$17K push reliably clears 30bps but not the 3% crisis band — so
    this "fires on a small depeg" proof is only meaningful at NORMAL RR. Off-normal the wide
    tolerance is correct behaviour, not a gap → skip rather than false-fail.
    """
    pk, addr = pool.pusher()
    if not pk or not addr:
        pytest.skip("ENGINE_PK/ENGINE_ADDRESS unavailable — can't fund a pool push")
    ev, err = engine.evaluate()
    mode = engine.rr_mode(ev) if not err else None
    if mode != "normal":
        pytest.skip(f"RR mode {mode!r} (not normal) → keeper trigger widens past a small push; "
                    "reset to normal RR to exercise peg defense")
    need, ferr = pool.affordable_push("wZSD", addr, PUSH_TOKENS)
    if need is None:
        pytest.skip(f"{ferr} — can't depeg the pool")

    before = len(_peg_opportunities())
    _, perr = pool.move_price("wZSD-USDT", sell_currency0=True, amount_atomic=need,
                              pk=pk, receiver=addr)
    assert not perr, f"pool push failed: {perr}"

    after = _peg_opportunities()
    assert len(after) > before or len(after) > 0, (
        "peg keeper proposed no corrective op after a >0.3% wZSD depeg"
    )
    # The correction should move wZSD back UP (buy wZSD / mint-side), not pile onto the drop.
    dirs = [str(o.get("direction", "")).lower() for o in after]
    assert not any("sell" in d and "zsd" in d for d in dirs), (
        f"peg keeper proposed to sell into the depeg: {dirs}"
    )
