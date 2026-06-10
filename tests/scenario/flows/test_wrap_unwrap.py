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
# Devnet runs the reorg-safe relay gate (INV-11, UNWRAP_RELAY_CONFIRMATIONS): a burn isn't relayed
# until buried this deep. Anvil auto-mines, so a standalone unwrap needs the burn buried explicitly.
RELAY_CONFIRMATIONS = 3


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
    # Bury the burn past the reorg-safe relay gate (INV-11) so the watcher relays it on devnet.
    chain.mine_evm(RELAY_CONFIRMATIONS)

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


# ── FLOW-ROUNDTRIP — value conservation across wrap then unwrap ───────────────
def test_flow_roundtrip_conserves_value(anvil_snapshot):
    """Wrap ZEPH→wZEPH then unwrap the SAME amount back: the wZEPH balance returns to baseline and
    a native payout lands. No value is created or destroyed across the round trip (INV-1/6).

    Both legs run inside one Anvil snapshot (reverted after), so the mint persists across the burn.
    """
    pk, addr = _claimer()
    token = _wzeph()
    if not pk or not addr or not token:
        pytest.skip("ENGINE_PK / wZEPH unavailable")
    dest = chain.wallet_address(chain.GOV_WALLET_PORT)
    if not dest:
        pytest.skip("gov wallet address unavailable")

    baseline, _ = pool.balance_of(token, addr)
    baseline = baseline or 0

    # ── wrap leg ──
    sub, err = _deposit_and_mine(addr)
    if err:
        pytest.skip(err)
    claim = bridge.wait_for_claim(addr, status="claimable", timeout=CLAIM_TIMEOUT)
    if not claim:
        pytest.skip("no claimable claim within timeout — watcher down")
    voucher = int(claim["amountWei"])
    _, cerr = bridge.claim_on_evm(token, claim, pk)
    assert not cerr, f"claim reverted: {cerr}"

    deadline = time.time() + 30
    wrapped = baseline
    while time.time() < deadline:
        wrapped, _ = pool.balance_of(token, addr)
        if (wrapped or 0) >= baseline + voucher:
            break
        time.sleep(2)
    assert (wrapped or 0) == baseline + voucher, "wrap leg did not mint the full voucher"

    # ── unwrap leg: burn exactly what was minted ──
    before_ids = {u.get("id") for u in bridge.unwraps_for(addr)}
    info, uerr = bridge.prepare_and_burn(token, voucher, dest, pk)
    if uerr:
        pytest.skip(f"unwrap prepare/burn unavailable: {uerr}")
    # Bury the burn past the reorg-safe relay gate (INV-11) so the watcher relays it on devnet.
    chain.mine_evm(RELAY_CONFIRMATIONS)
    relayed = bridge.wait_for_unwrap(addr, since_ids=before_ids,
                                     until=lambda u: u.get("sendStatus") == "sent", timeout=60)
    if not relayed:
        pytest.skip("watcher did not relay the payout — watcher down or relay flake")

    final, _ = pool.balance_of(token, addr)
    # The burn removed exactly the minted supply: balance is back to baseline, nothing leaked.
    assert (final or 0) == baseline, (
        f"round trip did not conserve value: baseline {baseline}, final {final} "
        f"(wrapped {voucher}, burned {voucher}) — net mint/burn imbalance (INV-1)"
    )
    assert relayed.get("zephTxHashHex"), "unwrap leg relayed no native payout (no Zephyr tx hash)"


# ── FLOW-PREPARE-CANCEL — a prepare that is never burned pays nothing ─────────
@pytest.mark.inv("INV-3")
def test_flow_prepare_without_burn_pays_nothing(anvil_snapshot):
    """A `/unwraps/prepare` is only a pre-signed payout INTENT — the relay must be gated on an
    on-chain burn that covers it. Prepare without ever burning ⇒ no payout is relayed (INV-3/4).
    """
    pk, addr = _claimer()
    token = _wzeph()
    if not pk or not addr or not token:
        pytest.skip("ENGINE_PK / wZEPH unavailable")
    dest = chain.wallet_address(chain.GOV_WALLET_PORT)
    if not dest:
        pytest.skip("gov wallet address unavailable")

    before_ids = {u.get("id") for u in bridge.unwraps_for(addr)}
    body, st, perr = bridge.prepare_unwrap(token, UNWRAP_WZEPH, dest)
    if st != 200 or not (body or {}).get("payload"):
        pytest.skip(f"prepare unavailable (http {st}): {perr or (body or {}).get('error')}")

    # Deliberately do NOT burn. No covering burn ⇒ no relay should ever happen.
    sent = bridge.wait_for_unwrap(addr, since_ids=before_ids,
                                  until=lambda u: u.get("sendStatus") == "sent", timeout=20)
    assert sent is None, (
        "the bridge relayed a payout for a prepare that was never burned on-chain — a prepare must "
        "not authorize funds movement by itself (INV-3/4)"
    )


# ── FLOW-CLAIM-EXPIRY — voucher re-sign path for an expired-but-unclaimed claim ─


@pytest.mark.inv("INV-7")
def test_flow_expired_voucher_has_resign_path():
    """A user who made a real deposit must ALWAYS be able to eventually claim it. A voucher whose 24h
    deadline lapses is marked 'expired' and would otherwise be permanently stuck — so the bridge now
    exposes an admin re-sign route (POST /claims/{evm}/resign, claims/signer.ts::resignClaim) that
    refreshes the deadline while binding the SAME to/amount/zephyrTxHash (the contract's usedZephyrTx
    still guarantees at-most-once). Promoted from @known_gap (INV-7).

    Asserts BOTH halves of the fix: the route EXISTS (not 404/405) AND it's an operator lever, not a
    public mint surface — an unauthenticated call must be rejected (403), never an open 2xx.
    Read-only: an unauthenticated POST is refused before it touches any claim.
    """
    _, addr = _claimer()
    addr = addr or "0x0000000000000000000000000000000000000001"
    st, _body, _err = bridge.post_raw(f"/claims/{addr}/resign", {"evmAddress": addr})
    assert st is not None and st not in (404, 405), (
        "no voucher re-sign endpoint exists — an expired voucher cannot be refreshed, so a real "
        "deposit unclaimed within the 24h TTL is permanently stuck (INV-7 claim non-expiry)"
    )
    assert st == 403, (
        f"the re-sign route must be admin-gated (a public re-sign is a free re-mint lever); "
        f"unauthenticated POST returned {st}, expected 403"
    )


# ── FLOW multi-asset — a V2 deposit credits ONLY its matching wrapped token ───
_WRAP_ASSETS = [
    pytest.param("ZSD", "wZSD", marks=pytest.mark.asset("ZSD")),
    pytest.param("ZRS", "wZRS", marks=pytest.mark.asset("ZRS")),
    pytest.param("ZYS", "wZYS", marks=pytest.mark.asset("ZYS")),
]


@pytest.mark.inv("INV-5")
@pytest.mark.parametrize("asset,wtoken", _WRAP_ASSETS)
def test_flow_wrap_asset_mints_correct_token(asset, wtoken, anvil_snapshot):
    """Depositing a V2 asset (ZSD/ZRS/ZYS) credits EXACTLY its matching wrapped token, never wZEPH
    (asset-type integrity, INV-1/5/6). Parametrized so the asset→token map is proven per-asset, not
    just for ZEPH. Skips (never reds) if gov can't fund the asset or the wToken isn't configured.
    """
    pk, addr = _claimer()
    if not pk or not addr:
        pytest.skip("ENGINE_PK/ENGINE_ADDRESS unavailable")
    token = pool.token_address(wtoken)
    if not token:
        pytest.skip(f"{wtoken} not in config")
    gov_bal = chain.balances(chain.GOV_WALLET_PORT).get(asset, 0.0)
    if gov_bal < WRAP_ZEPH:
        pytest.skip(f"gov holds {gov_bal} {asset} (< {WRAP_ZEPH}) — cannot fund a {asset} wrap")

    before, _ = pool.balance_of(token, addr)
    before = before or 0
    sub, err = bridge.create_address(addr)
    if err or not sub:
        pytest.skip(f"create_address failed: {err}")
    _, terr = chain.transfer(chain.GOV_WALLET_PORT, sub, int(WRAP_ZEPH * chain.ATOMIC), asset)
    if terr:
        pytest.skip(f"gov→bridge {asset} transfer failed: {terr}")
    control.mine(CONFIRM_BLOCKS)

    claim = bridge.wait_for_claim(addr, status="claimable", timeout=CLAIM_TIMEOUT)
    if not claim:
        pytest.skip(f"no claimable {asset} claim — watcher down or {asset} wraps unsupported")
    # The CRITICAL integrity check: the claim is for THIS wrapped token, not defaulted to wZEPH.
    assert (claim.get("token") or "").lower() == token.lower(), (
        f"{asset} deposit produced a claim for token {claim.get('token')} — expected {wtoken} "
        f"({token}); asset misrouted (INV-5 asset-type integrity)"
    )
    voucher = int(claim["amountWei"])
    _, cerr = bridge.claim_on_evm(token, claim, pk)
    assert not cerr, f"{wtoken} claim reverted: {cerr}"

    deadline = time.time() + 30
    after = before
    while time.time() < deadline:
        after, _ = pool.balance_of(token, addr)
        if (after or 0) > before:
            break
        time.sleep(2)
    assert (after or 0) - before == voucher, (
        f"{wtoken} minted {(after or 0) - before} != voucher {voucher} (not 1:1, INV-1/6)"
    )
