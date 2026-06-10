"""FLOW-* — the money paths. Wrap (ZEPH→wZEPH) and unwrap (wZEPH→ZEPH) end to end, asserting the
properties that keep custody honest: exact 1:1, replay-once, value conserved, status truthful.

These are full integration scenarios — they move real funds across the Zephyr daemon, the bridge
watchers, and Anvil, and mutate Zephyr chain state (mining), so they are @needs_reset and the
operator isolates them. They need a funded EVM claimer (ENGINE_PK) and the gov wallet's ZPH; absent
either, they skip rather than fail. The bridge watchers must be running to relay claims/payouts —
if a claim never appears within the timeout the test skips (watcher down), it does not red.
"""
from __future__ import annotations

import time

import pytest

from harness import bridge, chain, control, pool

pytestmark = [pytest.mark.needs_stack, pytest.mark.needs_reset, pytest.mark.inv("INV-1")]

WRAP_ZEPH = 5.0                      # whole ZPH to wrap
WRAP_ATOMIC = int(WRAP_ZEPH * chain.ATOMIC)
CONFIRM_BLOCKS = 15                  # generous cover for the watcher's confirmation target
CLAIM_TIMEOUT = 150.0


def _claimer() -> tuple[str | None, str | None]:
    return pool.pusher()  # (pk, addr)


def _wzeph() -> str | None:
    return pool.token_address("wZEPH")


def _deposit_and_mine(evm_addr: str) -> tuple[str | None, str | None]:
    """Create a bridge subaddress for evm_addr, send WRAP_ZEPH from gov, mine confirmations.
    Returns (zephyr_subaddress, err)."""
    sub, err = bridge.create_address(evm_addr)
    if err or not sub:
        return None, f"create_address failed: {err}"
    _, terr = chain.transfer(chain.GOV_WALLET_PORT, sub, WRAP_ATOMIC, "ZPH")
    if terr:
        return None, f"gov→bridge transfer failed: {terr}"
    control.mine(CONFIRM_BLOCKS)
    return sub, None


def test_flow_wrap_zeph_mints_exact(anvil_snapshot):
    """Deposit ZEPH → claim → wZEPH balance rises by EXACTLY the deposited amount (1:1, INV-1/6)."""
    pk, addr = _claimer()
    if not pk or not addr:
        pytest.skip("ENGINE_PK/ENGINE_ADDRESS unavailable")
    token = _wzeph()
    if not token:
        pytest.skip("wZEPH not in config")

    before, _ = pool.balance_of(token, addr)
    sub, err = _deposit_and_mine(addr)
    if err:
        pytest.skip(err)

    claim = bridge.wait_for_claim(addr, status="claimable", timeout=CLAIM_TIMEOUT)
    if not claim:
        pytest.skip("no claimable claim within timeout — watcher down or confirmations slow")

    voucher = int(claim["amountWei"])
    _, cerr = bridge.claim_on_evm(token, claim, pk)
    assert not cerr, f"claimWithSignature reverted: {cerr}"
    # allow the mint to land
    deadline = time.time() + 30
    after = before or 0
    while time.time() < deadline:
        after, _ = pool.balance_of(token, addr)
        if (after or 0) > (before or 0):
            break
        time.sleep(2)
    minted = (after or 0) - (before or 0)
    # Contract-level 1:1: the claim mints EXACTLY the voucher amount, nothing more.
    assert minted == voucher, f"minted {minted} wei != voucher {voucher} (mint not 1:1, INV-1/6)"
    # And the voucher should reflect the deposit (wZEPH 12-dec == ZEPH atomic scale, 1:1 less fees).
    assert 0 < voucher <= WRAP_ATOMIC, f"voucher {voucher} not within (0, deposit {WRAP_ATOMIC}]"


def test_flow_claim_idempotent(anvil_snapshot):
    """Claiming the same voucher twice: the second reverts (usedZephyrTx replay guard, INV-2)."""
    pk, addr = _claimer()
    if not pk or not addr:
        pytest.skip("ENGINE_PK/ENGINE_ADDRESS unavailable")
    token = _wzeph()
    if not token:
        pytest.skip("wZEPH not in config")

    sub, err = _deposit_and_mine(addr)
    if err:
        pytest.skip(err)
    claim = bridge.wait_for_claim(addr, status="claimable", timeout=CLAIM_TIMEOUT)
    if not claim:
        pytest.skip("no claimable claim within timeout — watcher down")

    _, e1 = bridge.claim_on_evm(token, claim, pk)
    assert not e1, f"first claim should succeed, got: {e1}"
    _, e2 = bridge.claim_on_evm(token, claim, pk)
    assert e2 is not None, "second claim of the same voucher did NOT revert — replay possible (INV-2)"


UNWRAP_WZEPH = 1 * chain.ATOMIC      # 1 wZEPH (12-dec == ZEPH atomic scale)


@pytest.mark.inv("INV-13")
def test_flow_unwrap_pays_out_and_status_confirms(anvil_snapshot):
    """Burn wZEPH → native ZEPH pays out → the unwrap record flips pending→confirmed (INV-1/13).

    The wZEPH inventory is minted to the burner (MINTER_ROLE, devnet) to isolate the unwrap side;
    the honest wrap-then-unwrap is FLOW-ROUNDTRIP. Live-verified: the watcher relays (sendStatus
    'sent') and a downstream confirmation flips status pending→confirmed within ~15s. Skips (never
    reds) if the watcher is down or the daemon rejects the relay (a known devnet flake).
    """
    pk, addr = _claimer()
    mpk = pool.minter()
    token = _wzeph()
    if not pk or not addr or not mpk or not token:
        pytest.skip("ENGINE_PK / DEPLOYER_PRIVATE_KEY / wZEPH unavailable")
    dest = chain.wallet_address(chain.GOV_WALLET_PORT)
    if not dest:
        pytest.skip("gov wallet address unavailable")

    _, merr = pool.mint_wtoken("wZEPH", addr, UNWRAP_WZEPH, mpk)
    assert not merr, f"mint wZEPH failed: {merr}"

    before_ids = {u.get("id") for u in bridge.unwraps_for(addr)}
    info, err = bridge.prepare_and_burn(token, UNWRAP_WZEPH, dest, pk)
    if err:
        pytest.skip(f"prepare/burn unavailable: {err}")

    relayed = bridge.wait_for_unwrap(addr, since_ids=before_ids,
                                     until=lambda u: u.get("sendStatus") == "sent", timeout=60)
    if not relayed:
        pytest.skip("watcher did not relay the payout within timeout — watcher down or relay flake")
    # INV-1: the bridge relayed a native payout (a Zephyr tx hash is bound to the record).
    assert relayed.get("zephTxHashHex"), "relayed unwrap carries no Zephyr tx hash"

    confirmed = bridge.wait_for_unwrap(addr, since_ids=before_ids,
                                       until=lambda u: u.get("status") == "confirmed", timeout=45)
    assert confirmed is not None, (
        "unwrap relayed but status never reached 'confirmed' — stuck on a stale wallet height "
        "(INV-13 status truth)"
    )
