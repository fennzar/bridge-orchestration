"""SEC-DEBUG-AUTH-OPEN / SEC-ENGINE-CTRL-UNAUTH — privileged routes guarded by a flag, not auth.

INV-18: privileged routes must require authentication. Two surfaces fail this today:

  * bridge-api `/debug/*` — gated ONLY by the `NEXT_PUBLIC_ENABLE_DEV_CONTROLS` / `ENABLE_DEV_RESET`
    env flag, no auth token (routes/debug/index.ts). Reachable endpoints include
    `GET /debug/bridge-accounts/backup` (exports custodial account material) and, worse,
    `GET /debug/reset/database` — a DESTRUCTIVE wipe reachable by an idempotent GET.
  * engine `/api/engine/{runner,queue}` — execution-control surfaces with no auth (route.ts).

Probed non-destructively: we GET the read/backup surfaces and assert they are reachable without
any auth header (200), NOT that we trigger the destructive reset. Tagged @known_gap(INV-18). If the
dev flag is off (so /debug 4xx's), the debug case skips rather than green-washing.
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


@pytest.mark.known_gap(
    inv="INV-18",
    reason="bridge-api /debug/* (incl. custodial-account backup and a DESTRUCTIVE GET "
    "/debug/reset/database) is guarded only by a feature flag, no auth token.",
)
def test_sec_debug_backup_reachable_unauth():
    """`GET /debug/bridge-accounts/backup` exports custodial account material with no auth — only a
    dev flag. Reachable (200) = the gap. 4xx ⇒ dev controls off here, can't exercise → skip."""
    st = _status(f"{BRIDGE}/debug/bridge-accounts/backup")
    if st in (403, 404, 503):
        pytest.skip(f"/debug disabled here (status {st}) — dev controls off; can't exercise")
    assert st != 200, (
        "custodial-account backup is reachable with NO auth header (only a feature flag) — "
        "privileged route must require authentication (INV-18)"
    )


@pytest.mark.known_gap(
    inv="INV-18",
    reason="engine /api/engine/runner exposes execution-control settings with no authentication.",
)
def test_sec_engine_runner_unauth():
    """`GET /api/engine/runner` returns the live execution-control settings (autoExecute,
    manualApproval) with no auth — the write side (POST) is equally open."""
    st = _status(f"{ENGINE}/api/engine/runner")
    assert st != 200, "engine runner control reachable with no auth (INV-18)"


@pytest.mark.known_gap(
    inv="INV-18",
    reason="engine /api/engine/queue (approve/reject/cancel operations) has no authentication.",
)
def test_sec_engine_queue_unauth():
    """`GET /api/engine/queue` lists the operation queue (and POST approves/rejects ops) with no
    auth — anyone who can reach the port can drive execution."""
    st = _status(f"{ENGINE}/api/engine/queue")
    assert st != 200, "engine operation queue reachable with no auth (INV-18)"
