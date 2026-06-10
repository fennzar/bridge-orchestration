"""MKT-PEG-DEFENSE — the peg keeper reacts when wZSD leaves its $1 peg.

The PegKeeper strategy (pegkeeper.ts) monitors the wZSD/USDT pool and, once the deviation clears
`minDeviationBps`, emits a corrective opportunity (buy wZSD when cheap) within the prevailing RR
gates. The trigger widens by RR mode (getAdjustedThresholds: normal 30bps / defensive 100bps /
crisis 300bps), so the "fires on a small depeg" proof is only meaningful at NORMAL RR.

This proves the engine defends the peg in response to a market move — the strategy counterpart to
ARB-DETECT. Expected GREEN.

Pushes run under `anvil_snapshot` (reverted after). The live engine wallet can't move the seeded
pool past the trigger on its own, so the depeg test MINTS wZSD to it (MINTER_ROLE, reverted with
the snapshot) and pushes a calibrated amount. Needs ENGINE_PK + DEPLOYER_PRIVATE_KEY (skip if
absent).
"""
from __future__ import annotations

import pytest

from harness import engine, pool

pytestmark = [pytest.mark.needs_stack, pytest.mark.inv("INV-14")]

# ≈ −43bps on the seeded wZSD/USDT depth: clears the 30bps normal trigger with margin, short of
# the concentrated-liquidity cliff (~35K+ sweeps the in-range liquidity and drains the pool).
PUSH_TOKENS = 32_000
NORMAL_TRIGGER_BPS = 30  # PegKeeper minDeviationBps at normal RR (pegkeeper.ts)


def _peg_eval() -> tuple[list[dict], float | None]:
    """(opportunities, deviationBps) from a peg evaluation."""
    ev, err = engine.evaluate(strategies="peg")
    assert not err and ev, f"evaluate(peg) errored: {err}"
    peg = (ev.get("results") or {}).get("peg") or {}
    dev = (peg.get("metrics") or {}).get("deviationBps")
    return peg.get("opportunities", []), dev


def test_mkt_peg_quiet_when_on_peg(anvil_snapshot):
    """Baseline: with wZSD near $1, the peg keeper proposes nothing (or nothing urgent)."""
    opps, _ = _peg_eval()
    # Not a hard zero — tiny residual deviation is fine; assert it isn't screaming.
    assert all(o.get("severity") != "critical" for o in opps), (
        f"peg keeper flagged a critical op while on-peg: {opps}"
    )


def test_mkt_peg_reacts_to_depeg(anvil_snapshot):
    """Push wZSD below peg → the keeper proposes a corrective (discount→buy) op.

    Only meaningful at NORMAL RR (the trigger widens off-normal). We mint wZSD to the pusher and
    push a calibrated amount; if a reseed deepens the pool so the push undershoots the 30bps
    trigger, skip with the measured number rather than false-fail.
    """
    pk, addr = pool.pusher()
    if not pk or not addr:
        pytest.skip("ENGINE_PK/ENGINE_ADDRESS unavailable — can't fund a pool push")
    mpk = pool.minter()
    if not mpk:
        pytest.skip("DEPLOYER_PRIVATE_KEY (MINTER_ROLE) unavailable — can't fund a calibrated push")
    ev, err = engine.evaluate()
    mode = engine.rr_mode(ev) if not err else None
    if mode != "normal":
        pytest.skip(f"RR mode {mode!r} (not normal) → keeper trigger widens past the calibrated "
                    "push; reset to normal RR to exercise peg defense")

    _, before_dev = _peg_eval()
    amt = PUSH_TOKENS * 10 ** (pool.token_decimals("wZSD") or 12)
    _, merr = pool.mint_wtoken("wZSD", addr, amt, mpk)
    assert not merr, f"mint failed: {merr}"
    _, perr = pool.move_price("wZSD-USDT", sell_currency0=True, amount_atomic=amt, pk=pk, receiver=addr)
    assert not perr, f"pool push failed: {perr}"

    opps, after_dev = _peg_eval()
    assert after_dev is not None, "peg metrics carried no deviationBps after the push"
    # 1) Engine must SEE the depeg — the deviation moved down.
    assert after_dev < (before_dev or 0), (
        f"engine did not register the depeg: deviationBps {before_dev} → {after_dev}"
    )
    # 2) If the push undershot the trigger (pool deeper than calibrated), skip the action assertion.
    if abs(after_dev) < NORMAL_TRIGGER_BPS:
        pytest.skip(f"push achieved {after_dev}bps (< {NORMAL_TRIGGER_BPS} trigger) — pool deeper "
                    "than calibrated; can't exercise the corrective action")
    # 3) Past the trigger: the keeper must propose a corrective op and read it as a DISCOUNT (buy
    #    wZSD to restore), never a premium (which would pile into the drop).
    assert opps, f"keeper proposed no corrective op at {after_dev}bps depeg (≥ {NORMAL_TRIGGER_BPS})"
    dirs = [str(o.get("direction", "")).lower() for o in opps]
    assert any("discount" in d for d in dirs), (
        f"keeper mis-read a below-peg move (expected a zsd_discount correction): {dirs}"
    )
    assert not any("premium" in d for d in dirs), (
        f"keeper flagged a premium on a below-peg move: {dirs}"
    )
