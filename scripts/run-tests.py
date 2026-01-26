#!/usr/bin/env python3
"""Unified L1-L4 test runner for Zephyr Bridge Orchestration.

Usage:
  ./scripts/run-tests.py                         # All L1-L4
  ./scripts/run-tests.py --level L1              # Specific level
  ./scripts/run-tests.py --level L1 --level L2   # Multiple levels
  ./scripts/run-tests.py INFRA-01 SMOKE-01       # Specific test IDs
  ./scripts/run-tests.py --list                  # List tests
  ./scripts/run-tests.py --list --level L3       # List L3 tests
  ./scripts/run-tests.py --verbose               # Show per-test detail
  ./scripts/run-tests.py --report-json out.json  # JSON report
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure scripts/ is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from l1_l4_checks import (
    ALL_TESTS,
    L1_IDS,
    L2_IDS,
    L3_IDS,
    L4_IDS,
    TEST_BY_ID,
)
from test_common import (
    BLUE,
    CYAN,
    FAIL,
    NC,
    CleanupContext,
    print_result,
    print_summary,
    probe_services,
    write_json_report,
)


LEVEL_MAP = {
    "L1": L1_IDS,
    "L2": L2_IDS,
    "L3": L3_IDS,
    "L4": L4_IDS,
}


def list_tests(ids: list[str]) -> None:
    """Print available tests."""
    current_level = ""
    level_labels = {
        "L1": "L1: Infrastructure",
        "L2": "L2: Smoke",
        "L3": "L3: Component Features",
        "L4": "L4: Full Stack E2E",
    }
    print("Available Tests:")
    for tid in ids:
        td = TEST_BY_ID.get(tid)
        if not td:
            continue
        if td.level != current_level:
            current_level = td.level
            print(f"\n{level_labels.get(current_level, current_level)}")
        print(f"  {td.test_id:15s} {td.title}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Unified L1-L4 test runner for Zephyr Bridge Orchestration",
    )
    parser.add_argument(
        "ids", nargs="*",
        help="Specific test IDs to run (e.g. INFRA-01 SMOKE-01)",
    )
    parser.add_argument(
        "--level", action="append", dest="levels",
        choices=["L1", "L2", "L3", "L4"],
        help="Run all tests at a specific level (repeatable)",
    )
    parser.add_argument("--list", action="store_true", help="List available tests")
    parser.add_argument("--verbose", action="store_true", help="Show per-test detail")
    parser.add_argument("--report-json", help="Write JSON report to file")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # Determine which tests to run
    test_ids: list[str] = []

    if args.ids:
        test_ids = args.ids
    elif args.levels:
        for level in args.levels:
            test_ids.extend(LEVEL_MAP.get(level, []))
    else:
        # Default: all L1-L4
        test_ids = [t.test_id for t in ALL_TESTS]

    if args.list:
        list_tests(test_ids)
        return 0

    # Resolve tests
    tests_to_run = []
    for tid in test_ids:
        td = TEST_BY_ID.get(tid)
        if td:
            tests_to_run.append(td)
        else:
            print(f"WARNING: Unknown test ID: {tid}")

    if not tests_to_run:
        print("No tests to run.")
        return 0

    # Banner
    print("===========================================")
    print("  Bridge Orchestration Test Runner")
    print("===========================================")
    print()

    # Probe services once
    print(f"{CYAN}[INFO]{NC} Probing services...")
    probes = probe_services()
    up = [k for k, v in sorted(probes.items()) if v]
    down = [k for k, v in sorted(probes.items()) if not v]
    if up:
        print(f"{BLUE}[INFO]{NC} Up: {', '.join(up)}")
    if down:
        print(f"{BLUE}[INFO]{NC} Down: {', '.join(down)}")
    print()

    print(f"Running {len(tests_to_run)} test(s)...")
    print()

    # Check if L3/L4 tests are included (need cleanup context)
    has_l3_l4 = any(t.level in ("L3", "L4") for t in tests_to_run)

    # Run tests
    results = []
    ctx = CleanupContext() if has_l3_l4 else None

    try:
        if ctx:
            ctx.__enter__()

        for td in tests_to_run:
            r = td.check(probes)
            results.append(r)
            print_result(r, verbose=args.verbose)

    finally:
        if ctx:
            ctx.__exit__(None, None, None)

    # Summary
    print_summary(results)

    # JSON report
    if args.report_json:
        write_json_report(args.report_json, results, probes)

    # Exit code
    fail_count = sum(1 for r in results if r.result == FAIL)
    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
