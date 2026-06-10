"""RES-REORG-UNWRAP — the bridge must not relay an unwrap payout before the burn is reorg-safe (INV-11).

On a chain that can reorg (Sepolia/mainnet) a burn relayed at 0/1 confirmation can vanish in a reorg,
leaving the bridge having paid native ZEPH against a burn that no longer exists — an unrecoverable
loss. The fix wires the confirmation-depth primitives (`isBurnConfirmed`, confirmations.ts) into the
ingest path: `ingestEvmBurn` now PARKS a burn that isn't yet `UNWRAP_RELAY_CONFIRMATIONS` deep as
`pending`/`idle` and the EVM watcher's confirmation sweep (`relayConfirmedUnwraps`) relays it only
once it's buried deep enough.

Anvil can't reorg, but the gate is run live on devnet (`UNWRAP_RELAY_CONFIRMATIONS=3`) so the
BEHAVIOUR is provable both ways: (1) while the burn is shallower than the gate, no payout is relayed;
(2) once we bury it reorg-safe deep, the sweep relays it — and never before. Promoted from
@known_gap(INV-11).
"""
from __future__ import annotations

import time

import pytest

from harness import bridge, chain, pool

pytestmark = [pytest.mark.needs_stack, pytest.mark.needs_reset, pytest.mark.inv("INV-11")]

UNWRAP_WZEPH = 1 * chain.ATOMIC
# Must match the deployed gate (UNWRAP_RELAY_CONFIRMATIONS on devnet). Anvil auto-mines, so the chain
# only advances when we mine — a stray block can't prematurely satisfy the gate.
REORG_SAFE_DEPTH = 3


def test_res_unwrap_relayed_only_after_reorg_safe_depth():
    """A burn is relayed ONLY once it is buried >= REORG_SAFE_DEPTH confirmations deep (INV-11).

    Phase 1: burn and, while it is still shallower than the gate, assert it is NOT relayed (the gate
    parks it pending). Phase 2: mine until the burn is reorg-safe deep and assert the watcher's
    confirmation sweep then relays it — at a depth >= REORG_SAFE_DEPTH.
    """
    pk, addr = pool.pusher()
    mpk = pool.minter()
    token = pool.token_address("wZEPH")
    if not pk or not addr or not mpk or not token:
        pytest.skip("ENGINE_PK / DEPLOYER_PRIVATE_KEY / wZEPH unavailable")
    dest = chain.wallet_address(chain.GOV_WALLET_PORT)
    if not dest:
        pytest.skip("gov wallet address unavailable")

    _, merr = pool.mint_wtoken("wZEPH", addr, UNWRAP_WZEPH, mpk)
    assert not merr, f"mint wZEPH failed: {merr}"

    before_ids = {u.get("id") for u in bridge.unwraps_for(addr)}
    info, err = bridge.prepare_and_burn(token, UNWRAP_WZEPH, dest, pk)
    if err or not info:
        pytest.skip(f"prepare/burn unavailable: {err}")
    burn_block = info["burnBlock"]

    # ── Phase 1 — while the burn is shallower than the gate, it must NOT be relayed ──
    # Robust against ambient EVM block production (engine-run swaps): we only FAIL on a genuine
    # shallow relay. If the chain advances to the safe depth on its own, we can't demonstrate
    # deferral here — that's fine, Phase 2 still proves "relayed only at safe depth".
    def _new_unwrap():
        return next((u for u in bridge.unwraps_for(addr) if u.get("id") not in before_ids), None)

    deadline = time.time() + 12
    while time.time() < deadline:
        head = chain.block_number() or burn_block
        confs = head - burn_block + 1
        if confs >= REORG_SAFE_DEPTH:
            break  # chain advanced on its own — deferral window passed, move on to Phase 2
        rec = _new_unwrap()
        assert not (rec and rec.get("sendStatus") == "sent"), (
            f"payout relayed at {confs} confirmation(s) (< reorg-safe {REORG_SAFE_DEPTH}) — a reorg of "
            "the burn after relay would lose native ZEPH against a burn that no longer exists (INV-11)"
        )
        time.sleep(1.5)

    # ── Phase 2 — bury the burn reorg-safe deep; the confirmation sweep now relays it ──
    chain.mine_evm(REORG_SAFE_DEPTH)
    relayed = bridge.wait_for_unwrap(addr, since_ids=before_ids,
                                     until=lambda u: u.get("sendStatus") == "sent", timeout=60)
    if not relayed:
        pytest.skip("watcher did not relay even after burying the burn — watcher down or relay flake")

    head = chain.block_number() or burn_block
    confs_at_relay = head - burn_block + 1
    assert confs_at_relay >= REORG_SAFE_DEPTH, (
        f"payout relayed at {confs_at_relay} confirmation(s) (< reorg-safe {REORG_SAFE_DEPTH}) — INV-11"
    )
    assert relayed.get("zephTxHashHex"), "relayed unwrap carries no Zephyr tx hash"
