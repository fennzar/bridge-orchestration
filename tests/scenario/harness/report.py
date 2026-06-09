"""Pure red/green classification — the heart of the KNOWN-GAP model.

Dependency-free (no pytest, no stack) so the bucketing logic is unit-testable in
isolation. The conftest plumbing feeds pytest outcomes through `classify()`; the
cross-layer aggregator (`scripts/invariant-report.py`) consumes the JSON it emits.

Buckets:
  GREEN           test asserts correct behavior and passes — invariant held here
  KNOWN_GAP       test asserts correct behavior, fails today, tagged @known_gap → the worklist
  REGRESSION      test fails and is NOT tagged → a real break, FATAL to the build
  UNEXPECTED_PASS a @known_gap test started passing → fix landed, promote the row, FATAL (drop marker)
  ACCEPTED        @accepted_risk — a documented, owner-accepted deviation → AMBER, never fatal
  SKIPPED         not run (stack down / isolation)
"""
from __future__ import annotations

GREEN = "GREEN"
KNOWN_GAP = "KNOWN_GAP"
REGRESSION = "REGRESSION"
UNEXPECTED_PASS = "UNEXPECTED_PASS"
ACCEPTED = "ACCEPTED"
SKIPPED = "SKIPPED"

# Buckets that must fail the build (CI gate = "no regressions, no silent fixes").
FATAL = frozenset({REGRESSION, UNEXPECTED_PASS})


def classify(*, passed: bool, failed: bool, skipped: bool,
             known_gap: bool, accepted_risk: bool) -> str:
    """Map a single test outcome + its markers to a bucket. Pure."""
    if skipped:
        return SKIPPED
    if accepted_risk:
        # Documented accepted deviation — amber regardless of pass/fail, never fatal.
        return ACCEPTED
    if passed:
        # A gap we expected to be red just went green → the fix landed; promote it.
        return UNEXPECTED_PASS if known_gap else GREEN
    if failed:
        return KNOWN_GAP if known_gap else REGRESSION
    return SKIPPED


def is_fatal(bucket: str) -> bool:
    return bucket in FATAL
