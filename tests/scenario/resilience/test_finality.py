"""RES-REORG-UNWRAP — the bridge relays an unwrap payout before the burn is reorg-safe (INV-11).

The EVM watcher's ingest path (`ingestEvmBurn`, packages/bridge/src/unwraps/ingest.ts) relays the
native Zephyr payout the instant it sees a `Burned` event — it never consults the confirmation-depth
primitives (`isBurnConfirmed`/`safeHeadBlock`, confirmations.ts), which exist but are unwired. On a
chain that can reorg (Sepolia/mainnet) a burn can be relayed and then vanish in a reorg, leaving the
bridge having paid native ZEPH against a burn that no longer exists — an unrecoverable loss.

Live-verified on devnet: the payout reaches sendStatus='sent' while the burn is only ~1 confirmation
deep. Anvil can't reorg and the gate is intentionally off on devnet (confirmTarget<=0), so this can't
be shown as an actual fund loss here — the faithful red is the BEHAVIOUR: the payout is relayed
before the burn is buried a reorg-safe depth. KNOWN-GAP(INV-11): the test asserts the safe behaviour
(no relay until ≥ REORG_SAFE_DEPTH confirmations) and fails today because the bridge relays at ~1.
The day the confirmation gate is wired into the watcher, this flips to UNEXPECTED_PASS → promote.
"""
from __future__ import annotations

import pytest

from harness import bridge, chain, pool

pytestmark = [pytest.mark.needs_stack, pytest.mark.needs_reset, pytest.mark.inv("INV-11")]

UNWRAP_WZEPH = 1 * chain.ATOMIC
# A modest reorg-safety target. Devnet relays at ~1 conf; even a stray engine-mined block or two
# stays well under this, so the known-gap reds deterministically (and won't flap to unexpected-pass).
REORG_SAFE_DEPTH = 3


@pytest.mark.known_gap(
    inv="INV-11",
    reason="the EVM watcher relays the unwrap payout at ~1 confirmation — ingestEvmBurn never "
    "consults isBurnConfirmed/safeHeadBlock (confirmations.ts is unwired). A reorg of the burn "
    "after relay loses native ZEPH against a burn that no longer exists.",
)
def test_res_unwrap_relayed_before_reorg_safe_depth():
    """A burn must not be relayed until it is buried REORG_SAFE_DEPTH confirmations deep.

    We mint wZEPH, burn it, and — WITHOUT mining further EVM blocks — wait for the relay, then
    measure how deep the burn was when paid. Today it's ~1 (unsafe) → red.
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

    # Do NOT mine extra EVM blocks — leave the burn shallow and see if the bridge relays anyway.
    relayed = bridge.wait_for_unwrap(addr, since_ids=before_ids,
                                     until=lambda u: u.get("sendStatus") == "sent", timeout=60)
    if not relayed:
        pytest.skip("watcher did not relay within timeout — watcher down or relay flake")

    head = chain.block_number() or burn_block
    confs_at_relay = max(1, head - (burn_block or head) + 1)
    assert confs_at_relay >= REORG_SAFE_DEPTH, (
        f"payout relayed at {confs_at_relay} confirmation(s) (< reorg-safe {REORG_SAFE_DEPTH}) — "
        "a reorg of the burn after relay would lose native ZEPH (INV-11; confirmation gate unwired)"
    )
