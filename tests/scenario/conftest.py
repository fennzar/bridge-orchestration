"""pytest plumbing for the bridge scenario suite.

Wires the KNOWN-GAP red/green model (see harness/report.py) into pytest:
  - registers the markers (@known_gap, @accepted_risk, @needs_stack, @needs_reset, @inv, @asset)
  - skips @needs_stack tests when the core stack is down (so a no-stack run is clean, not red)
  - buckets every outcome and writes .report/scenario.json for the cross-layer aggregator
  - overrides the exit code: KNOWN-GAP/ACCEPTED failures do NOT fail the build; a REGRESSION
    (untagged failure) or an UNEXPECTED_PASS (a gap that started passing) does.

Reuses the existing stdlib control plane in ../../scripts (test_common, lib/seed_helpers) —
they are NOT rewritten, only wrapped by harness/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ── make the kept control plane + the harness importable ────────────────────
SCENARIO_DIR = Path(__file__).resolve().parent
ROOT = SCENARIO_DIR.parents[1]                 # .../bridge-orchestration
SCRIPTS = ROOT / "scripts"
for _p in (str(SCENARIO_DIR), str(SCRIPTS), str(SCRIPTS / "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from harness import report as R  # noqa: E402  (pure classification)

REPORT_DIR = SCENARIO_DIR / ".report"
REPORT_JSON = REPORT_DIR / "scenario.json"

# Services that must be up for a @needs_stack test to run (coarse gate).
CORE_SERVICES = ("anvil", "bridge_api", "engine", "node1", "gov_wallet", "bridge_wallet")

_RECORDS: list[dict] = []
_STACK: dict = {"probed": False, "up": {}, "core_ok": False}


# ── markers ──────────────────────────────────────────────────────────────────
def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "known_gap(inv, reason): expected-RED gap tied to an INVARIANTS.md row; "
        "non-fatal to the build, surfaced in the worklist.",
    )
    config.addinivalue_line(
        "markers",
        "accepted_risk(inv, reason): owner-accepted, documented deviation (e.g. contract "
        "single-key); rendered AMBER, never fatal.",
    )
    config.addinivalue_line(
        "markers", "needs_stack: requires a live `make dev` stack; skipped if core services are down."
    )
    config.addinivalue_line(
        "markers",
        "needs_reset: mutates Zephyr chain state irreversibly (mining/conversions); run in "
        "isolation — operator does `make dev-reset` between such tests.",
    )
    config.addinivalue_line("markers", "inv(id): the INVARIANTS.md invariant this test pins (e.g. INV-14).")
    config.addinivalue_line("markers", "asset(name): the Zephyr asset under test (ZEPH/ZSD/ZRS/ZYS).")


def pytest_addoption(parser):
    g = parser.getgroup("scenario")
    g.addoption("--inv", default=None, help="run only tests pinning this invariant (e.g. INV-14).")
    g.addoption("--asset", default=None, help="run only tests for this asset (ZEPH/ZSD/ZRS/ZYS).")


def _marker_values(item, name: str) -> list:
    vals = []
    for m in item.iter_markers(name=name):
        vals.extend(str(a) for a in m.args)
        if name == "known_gap" or name == "accepted_risk":
            if m.kwargs.get("inv"):
                vals.append(str(m.kwargs["inv"]))
    return vals


def pytest_collection_modifyitems(config, items):
    want_inv = config.getoption("--inv")
    want_asset = config.getoption("--asset")
    if not want_inv and not want_asset:
        return
    kept, deselected = [], []
    for it in items:
        ok = True
        if want_inv:
            invs = _marker_values(it, "inv") + _marker_values(it, "known_gap") + _marker_values(it, "accepted_risk")
            ok = ok and any(want_inv.upper() == v.upper() for v in invs)
        if want_asset:
            assets = _marker_values(it, "asset")
            ok = ok and any(want_asset.upper() == v.upper() for v in assets)
        (kept if ok else deselected).append(it)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = kept


# ── stack probe + skip gate ───────────────────────────────────────────────────
def _probe_stack() -> dict:
    if not _STACK["probed"]:
        try:
            import test_common
            up = test_common.probe_services()
        except Exception:
            up = {}
        _STACK["up"] = up
        _STACK["core_ok"] = bool(up) and all(up.get(s) for s in CORE_SERVICES)
        _STACK["probed"] = True
    return _STACK


def pytest_runtest_setup(item):
    if item.get_closest_marker("needs_stack"):
        st = _probe_stack()
        if not st["core_ok"]:
            down = [s for s in CORE_SERVICES if not st["up"].get(s)] or ["unknown"]
            pytest.skip(f"core stack down ({', '.join(down)}) — start it with `make dev`")


# ── fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def stack() -> dict:
    """The service-up map, probed once per session. Tests may branch on it."""
    return _probe_stack()


@pytest.fixture
def clean_market():
    """Restore oracle price ($1.50) + orderbook spread (50bps) after the test.

    Cheap isolation for market-manipulation scenarios — NOT a full `make dev-reset`
    (which stops the stack). Use @needs_reset for tests that mutate Zephyr chain state.
    """
    import test_common
    yield
    test_common.set_oracle_price(1.50)
    test_common.set_orderbook_spread(50)


@pytest.fixture
def anvil_snapshot():
    """Snapshot Anvil EVM state before the test and revert after — isolates swaps,
    balances, and any on-chain mutation so a pool-push can't poison the next test."""
    from harness import chain
    snap = chain.evm_snapshot()
    yield snap
    if snap:
        chain.evm_revert(snap)


# ── outcome bucketing ─────────────────────────────────────────────────────────
@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    kg = item.get_closest_marker("known_gap")
    ar = item.get_closest_marker("accepted_risk")
    inv = item.get_closest_marker("inv")
    rep._known_gap = dict(kg.kwargs) if kg else None
    rep._accepted_risk = dict(ar.kwargs) if ar else None
    invid = None
    if inv and inv.args:
        invid = inv.args[0]
    elif kg and kg.kwargs.get("inv"):
        invid = kg.kwargs["inv"]
    elif ar and ar.kwargs.get("inv"):
        invid = ar.kwargs["inv"]
    rep._inv = invid


def _record(rep):
    kg = getattr(rep, "_known_gap", None)
    ar = getattr(rep, "_accepted_risk", None)
    bucket = R.classify(
        passed=rep.passed, failed=rep.failed, skipped=rep.skipped,
        known_gap=kg is not None, accepted_risk=ar is not None,
    )
    _RECORDS.append({
        "nodeid": rep.nodeid,
        "bucket": bucket,
        "inv": getattr(rep, "_inv", None),
        "reason": (kg or {}).get("reason") or (ar or {}).get("reason"),
        "duration": round(getattr(rep, "duration", 0.0), 3),
    })


def pytest_runtest_logreport(report):
    if report.when == "call":
        _record(report)
    elif report.when == "setup" and report.skipped:
        _record(report)


# ── session summary + exit-code override ──────────────────────────────────────
def pytest_sessionfinish(session, exitstatus):
    REPORT_DIR.mkdir(exist_ok=True)
    counts: dict[str, int] = {}
    for r in _RECORDS:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1
    fatal = [r for r in _RECORDS if R.is_fatal(r["bucket"])]
    REPORT_JSON.write_text(json.dumps({
        "layer": "scenario",
        "counts": counts,
        "fatal": len(fatal),
        "stack": _STACK.get("up", {}),
        "records": _RECORDS,
    }, indent=2))
    # Build gate: only regressions / unexpected-passes are fatal. Known gaps stay red in
    # the report but pass the gate; unexpected passes (which pytest sees as success) fail it.
    if fatal:
        session.exitstatus = 1
    elif exitstatus == 1:
        session.exitstatus = 0


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    tr = terminalreporter
    if not _RECORDS:
        return
    counts: dict[str, int] = {}
    for r in _RECORDS:
        counts[r["bucket"]] = counts.get(r["bucket"], 0) + 1

    tr.write_sep("=", "INVARIANT WORKLIST (scenario layer)")
    tr.write_line(
        f"GREEN {counts.get(R.GREEN,0)} · "
        f"KNOWN-GAP {counts.get(R.KNOWN_GAP,0)} · "
        f"ACCEPTED {counts.get(R.ACCEPTED,0)} · "
        f"REGRESSION {counts.get(R.REGRESSION,0)} · "
        f"UNEXPECTED-PASS {counts.get(R.UNEXPECTED_PASS,0)} · "
        f"SKIPPED {counts.get(R.SKIPPED,0)}"
    )
    gaps = [r for r in _RECORDS if r["bucket"] == R.KNOWN_GAP]
    if gaps:
        tr.write_line("")
        tr.write_line("Known gaps (expected red — the worklist):", yellow=True)
        for r in gaps:
            tr.write_line(f"  [{r['inv'] or '?'}] {r['nodeid']}  — {r['reason'] or ''}")
    regs = [r for r in _RECORDS if r["bucket"] == R.REGRESSION]
    if regs:
        tr.write_line("")
        tr.write_line("REGRESSIONS (untagged failures — fix or tag):", red=True)
        for r in regs:
            tr.write_line(f"  {r['nodeid']}")
    ups = [r for r in _RECORDS if r["bucket"] == R.UNEXPECTED_PASS]
    if ups:
        tr.write_line("")
        tr.write_line("UNEXPECTED PASSES (gap closed — promote the INV row, drop @known_gap):", green=True)
        for r in ups:
            tr.write_line(f"  [{r['inv'] or '?'}] {r['nodeid']}")
