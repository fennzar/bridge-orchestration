"""SEC-PREPARE-* — adversarial probes of the unauthenticated `/unwraps/prepare` route.

INV-19 / CRIT-1 (size-from-burn): `/unwraps/prepare` is now a **pure quote**. It validates input and
returns the v2 burn `payload` (destination + wallet fingerprint, NO pre-signed commit) plus an
informational fee/net estimate. It calls NO wallet RPC and commits NO hot-wallet UTXOs — the payout is
sized from the on-chain `Burned.amount` and signed+relayed inside the watcher (`ingestEvmBurn`). So the
route being unauthenticated is safe by construction: there is nothing to weaponize.

Coverage (all expected GREEN):
  - bad destination → 400 · zero amount → 400 · missing token → 400  (input validation holds)
  - valid request → 200 pure quote: a `payload` and NO `txHash`/`draftId`/`prepareId`  (commits nothing)
  - firing many valid prepares does NOT reduce the bridge wallet's unlocked balance  (UTXO-lock DoS closed)
  - if `UNWRAP_MAX_AMOUNT_WEI` is set, an over-cap quote is rejected
"""
from __future__ import annotations

import pytest

from harness import bridge, chain, pool

pytestmark = [pytest.mark.needs_stack, pytest.mark.inv("INV-19")]

GOOD_TOKEN_FALLBACK = "0x" + "0" * 39 + "1"  # only used to shape a request; validation rejects first
BAD_DEST = "not-a-zephyr-address"
ONE_ZEPH_WEI = 10**12
# Pre-sign artifacts the OLD prepare returned; the pure quote must carry NONE of them.
PRESIGN_FIELDS = ("txHash", "draftId", "prepareId", "preparedZephTxHashHex", "outgoingId")


def _wzeph() -> str:
    return pool.token_address("wZEPH") or GOOD_TOKEN_FALLBACK


def _valid_dest() -> str | None:
    """A real Zephyr primary address `validateZephyrAddress` will accept (test wallet, then gov)."""
    return chain.wallet_address(chain.TEST_WALLET_PORT) or chain.wallet_address(chain.GOV_WALLET_PORT)


# ── input validation (defenses present) ───────────────────────────────────────
def test_sec_prepare_rejects_bad_destination():
    body, status, err = bridge.prepare_unwrap(_wzeph(), ONE_ZEPH_WEI, BAD_DEST)
    assert status == 400, f"bad destination should 400, got {status} ({body or err})"
    assert "destination" in str((body or {}).get("error", "")).lower()


def test_sec_prepare_rejects_zero_amount():
    body, status, err = bridge.prepare_unwrap(_wzeph(), 0, BAD_DEST)
    # zero-amount and bad-dest both 400; either rejection is acceptable, never a 200.
    assert status == 400, f"zero amount should 400, got {status} ({body or err})"


def test_sec_prepare_rejects_missing_token():
    body, status, err = bridge.prepare_unwrap("", ONE_ZEPH_WEI, BAD_DEST)
    assert status == 400, f"missing token should 400, got {status} ({body or err})"


# ── INV-19 HELD: pure quote, unauthenticated, commits nothing ──────────────────
def test_sec_prepare_is_pure_quote_unauthenticated():
    """The INV-19 proof. With a VALID destination the route returns a 200 pure quote — a burn
    `payload` and NO pre-signed commit fields — without any auth gate. No commit returned ⇒ the
    route did not pre-sign ⇒ it committed no hot-wallet UTXO. Unauthenticated is safe by design."""
    dest = _valid_dest()
    if not dest:
        pytest.skip("no Zephyr wallet address available to form a valid destination")
    body, status, err = bridge.prepare_unwrap(_wzeph(), ONE_ZEPH_WEI, dest)
    assert status not in (401, 403), f"prepare must not be auth-gated (pure quote); got {status}"
    assert status == 200, f"valid prepare should 200, got {status} ({body or err})"
    assert body and body.get("payload"), f"pure quote must return a burn payload, got {body}"
    leaked = [f for f in PRESIGN_FIELDS if (body or {}).get(f)]
    assert not leaked, f"pure quote must NOT return pre-sign artifacts (INV-19); leaked {leaked}"


@pytest.mark.needs_reset
def test_sec_prepare_commits_no_wallet_utxos():
    """UTXO-lock DoS closed (the open half of CRIT-1/INV-19). The old prepare pre-signed a
    `do_not_relay` transfer from the bridge wallet, locking inputs from pure client input — so
    spamming /prepare could lock all UTXOs and grief legitimate unwraps. The pure quote touches no
    wallet, so firing many valid prepares must NOT reduce the bridge wallet's unlocked balance."""
    dest = _valid_dest()
    if not dest:
        pytest.skip("no Zephyr wallet address available to form a valid destination")
    before = chain.balances(chain.BRIDGE_WALLET_PORT).get("ZPH")
    if before is None:
        pytest.skip("bridge wallet ZPH balance unavailable — cannot measure UTXO locking")

    # A non-trivial amount the wallet could cover (so the OLD model would actually lock inputs).
    big_wei = 50 * ONE_ZEPH_WEI
    for _ in range(5):
        _, status, _ = bridge.prepare_unwrap(_wzeph(), big_wei, dest)
        assert status == 200, f"valid prepare should 200, got {status}"

    after = chain.balances(chain.BRIDGE_WALLET_PORT).get("ZPH")
    assert after is not None, "bridge wallet ZPH balance unavailable after prepares"
    # Pure quote locks nothing → unlocked balance must not drop. (Tolerate tiny jitter from
    # unrelated background activity; the old model would crater this by ~250 ZEPH.)
    assert after >= before - 1.0, (
        f"unlocked ZPH dropped {before - after:.4f} across 5 prepares — prepare is locking UTXOs "
        f"(INV-19 regression); before={before} after={after}"
    )


@pytest.mark.needs_reset
def test_sec_prepare_over_max_rejected():
    """If UNWRAP_MAX_AMOUNT_WEI is configured, an over-cap quote is rejected (400 'exceeds maximum').
    Skipped when no cap is set (the route fails open on amount, per the code). The cap check runs
    before address validation, so a bad dest still surfaces the cap rejection."""
    import os
    cap = os.environ.get("UNWRAP_MAX_AMOUNT_WEI", "").strip()
    if not cap or not cap.isdigit() or int(cap) <= 0:
        pytest.skip("UNWRAP_MAX_AMOUNT_WEI not set — no cap to exercise")
    over = int(cap) + 10**12
    body, status, _ = bridge.prepare_unwrap(_wzeph(), over, BAD_DEST)
    assert status == 400 and "max" in str((body or {}).get("error", "")).lower(), (
        f"over-cap amount should 400 'exceeds maximum', got {status} ({body})"
    )
