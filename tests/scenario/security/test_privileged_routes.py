"""SEC-DEBUG-AUTH-OPEN / SEC-ENGINE-CTRL-UNAUTH — privileged routes must require authentication.

INV-18: privileged routes must require authentication. Two surfaces:

  * bridge-api `/debug/*` (custodial) — CLOSED. The custodial/destructive routes
    (`GET /debug/bridge-accounts/backup`, `POST /debug/reset/database`, account restore) now require
    the `ADMIN_TOKEN` bearer in addition to the dev-controls flag, and the destructive GET variant of
    the reset was REMOVED (a wipe must never be an idempotent, crawler-/CSRF-triggerable GET). Probed
    non-destructively below: the backup GET with no auth must 401.
  * engine `/api/engine/{runner,queue}` (execution control) — OPEN, design fork. These are
    same-origin, browser-driven (engine-web's own /engine panel, no external caller). Closing them
    forces either exposing a shared secret in the client bundle (theater vs the "anyone on the port"
    threat) or cookie/session operator auth (real, but needs browser QA). Left @known_gap pending
    that decision rather than green-washed with a forgeable same-origin check. See FINDINGS.md.

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


@pytest.mark.known_gap(
    inv="INV-18",
    reason="DESIGN FORK: engine /api/engine/runner (execution-control settings) is same-origin "
    "browser-driven with no external caller. Real auth needs an operator-auth decision (cookie/"
    "session vs bundle-exposed shared secret vs network isolation); not closing it with a forgeable "
    "same-origin check, which would be a false green. Awaiting the mechanism decision.",
)
def test_sec_engine_runner_unauth():
    """`GET /api/engine/runner` returns the live execution-control settings (autoExecute,
    manualApproval) with no auth — the write side (POST) is equally open."""
    st = _status(f"{ENGINE}/api/engine/runner")
    assert st != 200, "engine runner control reachable with no auth (INV-18)"


@pytest.mark.known_gap(
    inv="INV-18",
    reason="DESIGN FORK: engine /api/engine/queue (approve/reject/cancel ops) is same-origin "
    "browser-driven with no external caller — same operator-auth decision as the runner route. "
    "Awaiting the mechanism decision (see FINDINGS.md / key-ops-and-contract-posture.md).",
)
def test_sec_engine_queue_unauth():
    """`GET /api/engine/queue` lists the operation queue (and POST approves/rejects ops) with no
    auth — anyone who can reach the port can drive execution."""
    st = _status(f"{ENGINE}/api/engine/queue")
    assert st != 200, "engine operation queue reachable with no auth (INV-18)"
