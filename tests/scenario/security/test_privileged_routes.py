"""SEC-DEBUG-AUTH-OPEN / SEC-ENGINE-CTRL-UNAUTH — privileged routes must require authentication.

INV-18: privileged routes must require authentication. Two surfaces:

  * bridge-api `/debug/*` (custodial) — CLOSED. The custodial/destructive routes
    (`GET /debug/bridge-accounts/backup`, `POST /debug/reset/database`, account restore) now require
    the `ADMIN_TOKEN` bearer in addition to the dev-controls flag, and the destructive GET variant of
    the reset was REMOVED (a wipe must never be an idempotent, crawler-/CSRF-triggerable GET). Probed
    non-destructively below: the backup GET with no auth must 401.
  * engine `/api/engine/{runner,queue}` (execution control) — ACCEPTED posture (network isolation).
    These are same-origin, browser-driven (engine-web's own /engine panel, no external caller). An
    in-bundle shared secret would be theater (forgeable); cookie/session auth is real but needs
    browser QA. Owner decision (2026-06-10): the engine runs operator-only behind an authenticated
    reverse proxy / private network — the NETWORK is the auth boundary, so engine-web is never
    publicly reachable. On this shared-origin dev/testnet stack the routes answer 200 (expected);
    prod isolates at the proxy. Documented in docs/security/engine-deployment-posture.md +
    FINDINGS.md. Marked @accepted_risk (AMBER), not green-washed with a forgeable same-origin check.

If the dev flag is off (so /debug 4xx's) the debug case skips rather than green-washing.
"""
from __future__ import annotations

import pytest

import test_common as _tc

pytestmark = [pytest.mark.needs_stack, pytest.mark.inv("INV-18")]

BRIDGE = _tc.BRIDGE_API_URL
ENGINE = _tc.ENGINE_URL


def _status(url: str) -> int | None:
    st, _, _ = _tc._get(url, timeout=8.0)
    return st


def test_sec_debug_backup_requires_auth():
    """`GET /debug/bridge-accounts/backup` exports custodial account material — it now requires the
    ADMIN_TOKEN bearer (INV-18). With dev controls on but NO auth header it must 401, not 200.
    4xx other than 401 (403/404/503) ⇒ dev controls off here, can't exercise → skip.
    Promoted: was the unauth-reachable gap; now asserts auth is enforced."""
    st = _status(f"{BRIDGE}/debug/bridge-accounts/backup")
    if st in (403, 404, 503):
        pytest.skip(f"/debug disabled here (status {st}) — dev controls off; can't exercise")
    assert st == 401, (
        f"custodial-account backup must require auth (expected 401 unauthenticated, got {st}) — "
        "privileged route is now ADMIN_TOKEN-gated (INV-18)"
    )


@pytest.mark.accepted_risk(
    inv="INV-18",
    reason="ACCEPTED (network isolation): engine /api/engine/runner (execution-control settings) is "
    "same-origin browser-driven with no external caller. Owner decision (2026-06-10) — the engine is "
    "operator-only behind an authenticated reverse proxy / private network; the network is the auth "
    "boundary, so engine-web is never publicly reachable. An in-bundle token would be forgeable "
    "theater. On the shared-origin dev/testnet stack this answers 200 (expected). See "
    "docs/security/engine-deployment-posture.md.",
)
def test_sec_engine_runner_unauth():
    """`GET /api/engine/runner` returns the live execution-control settings (autoExecute,
    manualApproval). On this shared-origin dev/testnet deployment it is reachable same-origin (200) —
    the accepted posture; prod isolates engine-web at the proxy/network layer (INV-18)."""
    st = _status(f"{ENGINE}/api/engine/runner")
    assert st == 200, (
        f"expected the same-origin engine panel to answer 200 here (got {st}); the INV-18 control is "
        "network isolation in prod, not a per-request gate — see engine-deployment-posture.md"
    )


@pytest.mark.accepted_risk(
    inv="INV-18",
    reason="ACCEPTED (network isolation): engine /api/engine/queue (approve/reject/cancel ops) is "
    "same-origin browser-driven with no external caller — same posture as the runner route. Engine "
    "runs operator-only behind an authenticated reverse proxy / private network (owner decision "
    "2026-06-10). See docs/security/engine-deployment-posture.md / key-ops-and-contract-posture.md.",
)
def test_sec_engine_queue_unauth():
    """`GET /api/engine/queue` lists the operation queue (POST approves/rejects ops). Reachable
    same-origin (200) on this dev/testnet stack — the accepted posture; prod isolates engine-web at
    the proxy/network layer rather than gating per-request (INV-18)."""
    st = _status(f"{ENGINE}/api/engine/queue")
    assert st == 200, (
        f"expected the same-origin engine panel to answer 200 here (got {st}); the INV-18 control is "
        "network isolation in prod, not a per-request gate — see engine-deployment-posture.md"
    )
