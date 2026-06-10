"""RES-DOUBLE-PAYOUT — a confirmed EVM burn must pay out native ZEPH exactly once, even across a
watcher crash / event re-delivery / operator resend (INV-4).

The payout is a pre-signed Zephyr tx: fixed inputs → a stable commit hash → it can mine at most once.
That makes the daemon the source of truth: a relay error or a lost status-write is NOT proof the
payout didn't land. Two crash states can otherwise double-pay, and each is exercised here against the
live stack:

  1. resend (fresh-input vector) — the broadcast landed on-chain but the post-broadcast confirmation
     write threw, so the record reads `failed`. `POST /admin/unwraps/:id/resend` builds a NEW payout
     with FRESH inputs (zephyrTransferSimple) → it would pay the destination twice. The fix
     (findLandedPayout reconcile guard) must detect the landed payout, heal to `sent`, and refuse.

  2. re-delivery (entry reconcile) — the watcher re-delivers the same Burned event after a crash that
     lost the sent-state write; the record looks un-relayed. Re-ingest (via /retry → ingestEvmBurn)
     must reconcile by commit hash at entry and heal WITHOUT relaying — and even if it did relay, the
     pre-signed tx is idempotent, so the record must converge to the ORIGINAL payout, never a new one.

  3. resend fail-closed (unverifiable commit) — the dangerous middle case: a `failed` record that
     CARRIES a pre-signed commit the daemon does NOT surface (the payout broadcast but isn't visible
     yet, or the wallet hasn't rescanned). The wallet RPC can't prove a relayed pre-signed tx is
     permanently dead — `get_transfer_by_txid` answers "not found" for both "never existed" and "in
     mempool, not yet rescanned". So resend must REFUSE the fresh-input send for ANY record with a
     commit on file (heal-or-refuse, never fresh-send); only a record that never had a payout may
     fresh-send. Building a second payout on that unverified absence is the double-pay this pins.

We can't crash a real watcher mid-flight deterministically, so we drive a genuine unwrap to a landed
payout, then INJECT the exact post-crash DB state (harness/db.py) and assert the guard holds. The
INV-4 anchor under test is: the record's zephTxId converges to the original payout — a *different*
txid would mean a second, fresh-input payout left the hot wallet. Promoted from @known_gap(INV-4).
"""
from __future__ import annotations

import time

import pytest

from harness import bridge, chain, control, db, pool

pytestmark = [pytest.mark.needs_stack, pytest.mark.needs_reset, pytest.mark.inv("INV-4")]

UNWRAP_WZEPH = 1 * chain.ATOMIC
# Devnet relay gate (UNWRAP_RELAY_CONFIRMATIONS=3) — bury the burn this deep so the watcher relays.
REORG_SAFE_DEPTH = 3
# A valid-format Zephyr commit hash for a tx the bridge wallet has never seen → daemon answers
# `get_transfer_by_txid` with code -8 "Transaction not found". Models a pre-signed payout that is
# on record but not (yet) surfaced by the wallet — the unverifiable state resend must fail closed on.
FAKE_UNKNOWN_COMMIT = "0x" + "deadbeef" * 8


def _drive_to_landed_payout() -> tuple[str, str, str]:
    """Mint wZEPH → prepare+burn → wait for the watcher to relay → confirm the daemon holds the
    payout by its commit hash. Returns (evm_addr, unwrap_id, original_zeph_txid). Skips (not fails)
    when prerequisites or the relay are unavailable — the gap under test is double-pay, not relay."""
    pk, addr = pool.pusher()
    mpk = pool.minter()
    token = pool.token_address("wZEPH")
    if not pk or not addr or not mpk or not token:
        pytest.skip("ENGINE_PK / DEPLOYER_PRIVATE_KEY / wZEPH unavailable")
    if not bridge.admin_token():
        pytest.skip("ADMIN_TOKEN unavailable — cannot exercise the privileged resend/retry guards")
    dest = chain.wallet_address(chain.GOV_WALLET_PORT)
    if not dest:
        pytest.skip("gov wallet address unavailable")

    _, merr = pool.mint_wtoken("wZEPH", addr, UNWRAP_WZEPH, mpk)
    assert not merr, f"mint wZEPH failed: {merr}"

    before = {u.get("id") for u in bridge.unwraps_for(addr)}
    info, err = bridge.prepare_and_burn(token, UNWRAP_WZEPH, dest, pk)
    if err or not info:
        pytest.skip(f"prepare/burn unavailable: {err}")

    # Bury the burn reorg-safe deep so the EVM watcher's confirmation sweep relays the payout.
    chain.mine_evm(REORG_SAFE_DEPTH)
    rec = bridge.wait_for_unwrap(
        addr, since_ids=before,
        until=lambda u: u.get("sendStatus") == "sent" and u.get("zephTxId"),
        timeout=90,
    )
    if not rec:
        pytest.skip("watcher did not relay the payout (watcher down or relay flake) — cannot stage INV-4")
    uid = rec["id"]
    txa = rec["zephTxId"]

    # Confirm the bridge wallet actually surfaces the payout by its commit hash — the exact lookup
    # both guards make (findLandedPayout/getTransferByTxid). The payout is a daemon-relayed pre-signed
    # tx, so the wallet only sees it after it is MINED and the wallet has RESCANNED that block: mine
    # Zephyr, force a wallet refresh, then probe. /admin/unwraps/reconcile returns the resolved
    # transfer. This is the realistic "operator resends a long-failed unwrap" state — by then mined.
    deadline = time.time() + 180
    while time.time() < deadline:
        control.mine(4)
        bridge.refresh_bridge_wallet()
        st, body, gerr = bridge.admin_get(f"/unwraps/reconcile?burnId={uid}")
        if st == 200 and body and body.get("transfer"):
            return addr, uid, txa
        time.sleep(3)
    pytest.skip("daemon never surfaced the payout by txid — cannot stage the landed-but-failed state")


def _await_converged_txid(uid: str, timeout: float = 30.0) -> str | None:
    """Poll the persisted record until its zephTxId settles (healing can lag one watcher tick)."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = db.unwrap_get(uid, ["zephTxId"]).get("zephTxId")
        if last:
            return last
        time.sleep(2)
    return last


def test_res_resend_refuses_fresh_payout_for_landed_burn():
    """A `failed` unwrap whose pre-signed payout already landed must NOT get a second, fresh-input
    payout on resend — the guard heals it to the original and refuses (INV-4)."""
    addr, uid, txa = _drive_to_landed_payout()

    # Inject the crash state: the relay broadcast LANDED on-chain, but the confirmation write threw,
    # so the record is `failed`. Clear zephTxId so resend's "already sent" short-circuit is bypassed
    # and we actually reach the INV-4 reconcile guard; keep preparedZephTxHashHex pointed at the
    # on-chain payout (the guard reconciles against it).
    _, derr = db.psql(
        f'''UPDATE "Unwrap"
            SET status = 'FAILED',
                "sendStatus" = 'error',
                "preparedZephTxHashHex" = COALESCE("preparedZephTxHashHex", '0x' || "zephTxId"),
                "zephTxId" = NULL,
                "zephTxHashHex" = NULL
            WHERE id = '{db._esc(uid)}';'''
    )
    assert not derr, f"failed to stage the landed-but-failed state: {derr}"

    st, body, err = bridge.admin_post(f"/unwraps/{uid}/resend")
    assert err is None, f"resend request never reached the API: {err}"
    # The guard MUST refuse the fresh-input resend (409) and heal to the original payout. A 200 'ok'
    # here means zephyrTransferSimple built and broadcast a SECOND payout — the double-pay (INV-4).
    assert st == 409, (
        f"resend returned {st}, expected 409 — a fresh-input payout for an already-landed burn drains "
        f"the hot wallet twice (INV-4). body={body}"
    )
    healed = (body or {}).get("record") or {}
    assert healed.get("zephTxId") == txa, (
        f"resend healed to zephTxId={healed.get('zephTxId')} but the on-chain payout was {txa} — a "
        f"different txid means a SECOND (fresh-input) payout was issued (INV-4 double-pay)"
    )
    assert healed.get("sendStatus") == "sent", f"healed record not marked sent: {healed.get('sendStatus')}"

    # And it persisted: the record is back to the ORIGINAL payout, not a fresh one.
    persisted = _await_converged_txid(uid)
    assert persisted == txa, f"persisted zephTxId={persisted} drifted from the original {txa} (INV-4)"


def test_res_resend_failclosed_for_unverifiable_commit():
    """The crux of the INV-4 HIGH: a `failed` unwrap that CARRIES a pre-signed payout commit the daemon
    does NOT surface must NOT get a fresh-input resend. The wallet RPC cannot prove a relayed pre-signed
    tx is permanently dead, so a fresh-input send here could pay twice if the original later mines. The
    structural guard (decideResend) must REFUSE for any record with a commit on file — heal-or-refuse,
    never fresh-send."""
    _addr, uid, _txa = _drive_to_landed_payout()

    # Inject the dangerous state: failed, no zephTxId, but a pre-signed commit ON RECORD that the
    # daemon reports "not found" (-8). This is the exact window where the OLD code fell through to
    # zephyrTransferSimple (a fresh-input second payout) on an unverified absence.
    _, derr = db.psql(
        f'''UPDATE "Unwrap"
            SET status = 'FAILED',
                "sendStatus" = 'error',
                "preparedZephTxHashHex" = '{FAKE_UNKNOWN_COMMIT}',
                "zephTxId" = NULL,
                "zephTxHashHex" = NULL
            WHERE id = '{db._esc(uid)}';'''
    )
    assert not derr, f"failed to stage the unverifiable-commit state: {derr}"

    st, body, err = bridge.admin_post(f"/unwraps/{uid}/resend")
    assert err is None, f"resend request never reached the API: {err}"
    # MUST refuse: 409 (daemon reachable, reported not-found) or 503 (daemon lookup failed). A 200 'ok'
    # means a SECOND, fresh-input payout was built on an unverified absence — the INV-4 double-pay.
    assert st in (409, 503), (
        f"resend returned {st}, expected 409/503 — building a fresh-input payout for a burn that still "
        f"carries an unverifiable pre-signed commit can drain the hot wallet twice (INV-4). body={body}"
    )
    assert not (body or {}).get("ok"), f"resend reported ok on a refuse path: {body}"

    # And nothing was sent: the record must NOT have acquired a fresh zephTxId.
    persisted = db.unwrap_get(uid, ["zephTxId", "sendStatus"])
    assert not persisted.get("zephTxId"), (
        f"resend wrote zephTxId={persisted.get('zephTxId')} — a fresh-input payout was issued for a "
        f"record with an unverifiable pre-signed commit (INV-4 double-pay)"
    )


def test_res_resend_recovers_commit_from_linked_draft():
    """Recovery: "no commit on the unwrap row" is NOT "no pre-signed payout exists". If the row
    loses its hash fields but a linked prepared/outgoing DRAFT still holds the commit, resend must
    recover it (or detect the lineage) and refuse the fresh-input send — never treat the row as a bare
    burn and pay a second time (INV-4)."""
    _addr, uid, txa = _drive_to_landed_payout()

    # Null EVERY hash field on the Unwrap ROW but leave the linked prepared/outgoing drafts intact
    # (they still carry zephTxId = the real on-chain commit). Without draft-aware recovery, the route
    # would see no commit and fresh-send a second payout.
    _, derr = db.psql(
        f'''UPDATE "Unwrap"
            SET status = 'FAILED',
                "sendStatus" = 'error',
                "preparedZephTxHashHex" = NULL,
                "preparedZephTxId" = NULL,
                "zephTxId" = NULL,
                "zephTxHashHex" = NULL
            WHERE id = '{db._esc(uid)}';'''
    )
    assert not derr, f"failed to stage the lost-row-hash state: {derr}"

    st, body, err = bridge.admin_post(f"/unwraps/{uid}/resend")
    assert err is None, f"resend request never reached the API: {err}"
    # MUST NOT fresh-send. The commit is recovered from the draft → its payout is on-chain → heal 409
    # (record converges to the original txid); or, if unrecoverable, refuse. A 200 'ok' with a NEW txid
    # is the double-pay this pins.
    assert st in (409, 503), (
        f"resend returned {st}, expected 409/503 — a row that lost its hash but has a linked payout "
        f"draft must not fresh-send a second payout (INV-4). body={body}"
    )
    healed = (body or {}).get("record") or {}
    if healed.get("zephTxId"):
        assert healed.get("zephTxId") == txa, (
            f"resend healed to zephTxId={healed.get('zephTxId')} != original {txa} — a SECOND payout "
            f"was issued for a burn whose commit lived only in the linked draft (INV-4 double-pay)"
        )

    # And the persisted record never acquired a fresh, different payout.
    persisted = db.unwrap_get(uid, ["zephTxId"]).get("zephTxId")
    assert persisted in (None, txa, "\\N"), (
        f"persisted zephTxId={persisted} is a new payout != original {txa} (INV-4 double-pay)"
    )


def test_res_resend_recovers_commit_from_burn_payload():
    """Recovery: the structured burn payload persisted on the unwrap row ALSO embeds the prepared
    tx hash. If the row loses every hash field, its prepareId/outgoingId, AND the linked drafts are
    deleted, the payload is the last surviving commit source — resend must recover from it and refuse
    the fresh-input send, never treat the row as a bare burn (INV-4)."""
    _addr, uid, txa = _drive_to_landed_payout()

    # Strip EVERY commit source except the burn payload: null the row hash fields + prepareId/outgoingId
    # (first, to drop any FK ref), then delete the linked prepared/outgoing drafts. The structured
    # burnPayload still decodes to the prepared tx hash (== the on-chain payout).
    _, derr = db.psql(
        f'''UPDATE "Unwrap"
            SET status = 'FAILED', "sendStatus" = 'error',
                "preparedZephTxHashHex" = NULL, "preparedZephTxId" = NULL,
                "zephTxId" = NULL, "zephTxHashHex" = NULL,
                "prepareId" = NULL, "outgoingId" = NULL
            WHERE id = '{db._esc(uid)}';'''
    )
    assert not derr, f"failed to null row commit sources: {derr}"
    _, e1 = db.psql(f'''DELETE FROM "ZephyrOutgoing" WHERE "unwrapId" = '{db._esc(uid)}';''')
    _, e2 = db.psql(f'''DELETE FROM "ZephyrPrepared" WHERE "unwrapId" = '{db._esc(uid)}';''')
    assert not e1 and not e2, f"failed to delete linked drafts: {e1} {e2}"

    # Sanity: the row still carries a structured burnPayload (now the only surviving commit source).
    bp = db.unwrap_get(uid, ["burnPayload"]).get("burnPayload")
    if not bp or bp == "\\N":
        pytest.skip("row carries no burnPayload to recover from — flow did not persist it")

    st, body, err = bridge.admin_post(f"/unwraps/{uid}/resend")
    assert err is None, f"resend request never reached the API: {err}"
    assert st in (409, 503), (
        f"resend returned {st}, expected 409/503 — the prepared tx hash still lives in the structured "
        f"burn payload, so resend must recover it and not fresh-send a second payout (INV-4). body={body}"
    )
    healed = (body or {}).get("record") or {}
    if healed.get("zephTxId"):
        assert healed.get("zephTxId") == txa, (
            f"resend healed to zephTxId={healed.get('zephTxId')} != original {txa} — a second payout "
            f"was issued for a burn whose commit lived only in the payload (INV-4 double-pay)"
        )
    persisted = db.unwrap_get(uid, ["zephTxId"]).get("zephTxId")
    assert persisted in (None, txa, "\\N"), (
        f"persisted zephTxId={persisted} is a new payout != original {txa} (INV-4 double-pay)"
    )


def test_res_reingest_idempotent_via_entry_reconcile():
    """Re-delivery of an already-paid burn (record looks un-relayed but the pre-signed payout landed)
    must reconcile at ingest entry and converge to the ORIGINAL payout — never relay a second one
    (INV-4)."""
    addr, uid, txa = _drive_to_landed_payout()

    # Simulate a crash that lost the sent-state write: the record reads un-relayed (pending/idle, no
    # zephTxId) but its pre-signed payout already landed. preparedZephTxHashHex still anchors it.
    _, derr = db.psql(
        f'''UPDATE "Unwrap"
            SET status = 'PENDING',
                "sendStatus" = 'idle',
                "preparedZephTxHashHex" = COALESCE("preparedZephTxHashHex", '0x' || "zephTxId"),
                "zephTxId" = NULL,
                "zephTxHashHex" = NULL
            WHERE id = '{db._esc(uid)}';'''
    )
    assert not derr, f"failed to stage the re-delivery state: {derr}"

    # /retry re-runs ingestEvmBurn (the watcher's re-delivery path). The entry reconcile should heal
    # by commit hash without relaying. The confirmation sweep may also heal it first (→ 409 'already
    # sent'); both outcomes are correct. What must NEVER happen is a fresh second payout.
    st, body, err = bridge.admin_post(f"/unwraps/{uid}/retry")
    assert err is None, f"retry request never reached the API: {err}"
    assert st in (200, 409), f"retry returned {st}, expected 200 (re-ingest heals) or 409 (swept first). body={body}"
    if st == 200:
        assert (body or {}).get("zephTxId") == txa, (
            f"re-ingest produced zephTxId={(body or {}).get('zephTxId')} != original {txa} — the entry "
            f"reconcile failed and a SECOND payout was relayed (INV-4 double-pay)"
        )

    # Authoritative invariant: the record converges to the ORIGINAL on-chain payout. A different txid
    # would be a second, distinct payout having left the hot wallet.
    persisted = _await_converged_txid(uid)
    assert persisted == txa, (
        f"record converged to zephTxId={persisted} != original {txa} — a second payout was issued for "
        f"one burn (INV-4 double-pay)"
    )
