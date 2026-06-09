"""Plumbing tests for the KNOWN-GAP red/green model — run WITHOUT a stack.

These pin the bucketing logic (harness/report.py) and confirm the markers are wired. They are
all GREEN: the actual exit-code override is verified separately by the suite's own behavior
(a regression fails the build; a known gap does not).
"""
from __future__ import annotations

from harness import report as R


def test_passing_untagged_is_green():
    assert R.classify(passed=True, failed=False, skipped=False,
                      known_gap=False, accepted_risk=False) == R.GREEN


def test_failing_untagged_is_regression_and_fatal():
    b = R.classify(passed=False, failed=True, skipped=False,
                   known_gap=False, accepted_risk=False)
    assert b == R.REGRESSION
    assert R.is_fatal(b)


def test_failing_known_gap_is_red_but_not_fatal():
    b = R.classify(passed=False, failed=True, skipped=False,
                   known_gap=True, accepted_risk=False)
    assert b == R.KNOWN_GAP
    assert not R.is_fatal(b)


def test_known_gap_that_passes_is_unexpected_pass_and_fatal():
    # A gap test that goes green means the fix landed → fail the build so we promote the row.
    b = R.classify(passed=True, failed=False, skipped=False,
                   known_gap=True, accepted_risk=False)
    assert b == R.UNEXPECTED_PASS
    assert R.is_fatal(b)


def test_accepted_risk_is_amber_regardless_of_outcome():
    for passed, failed in ((True, False), (False, True)):
        b = R.classify(passed=passed, failed=failed, skipped=False,
                       known_gap=False, accepted_risk=True)
        assert b == R.ACCEPTED
        assert not R.is_fatal(b)


def test_skipped_is_skipped():
    assert R.classify(passed=False, failed=False, skipped=True,
                      known_gap=False, accepted_risk=False) == R.SKIPPED


def test_markers_are_registered(pytestconfig):
    # @known_gap / @accepted_risk etc. must be known to --strict-markers.
    names = {ln.split(":")[0].split("(")[0]
             for ln in pytestconfig.getini("markers")}
    for m in ("known_gap", "accepted_risk", "needs_stack", "needs_reset", "inv", "asset"):
        assert m in names, f"marker {m} not registered"
