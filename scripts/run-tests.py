#!/usr/bin/env python3
"""Tiered test runner for Zephyr Bridge Orchestration.

Usage:
  ./scripts/run-tests.py                              # All tiers
  ./scripts/run-tests.py --tier precheck              # Health probes only
  ./scripts/run-tests.py --tier integration            # Bridge flow tests only
  ./scripts/run-tests.py --tier seed                   # Seed verification only
  ./scripts/run-tests.py INFRA-01 WRAP-01              # Specific test IDs
  ./scripts/run-tests.py --list                        # List tests
  ./scripts/run-tests.py --verbose                     # Show per-test detail
  ./scripts/run-tests.py --report-json out.json        # JSON report
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure scripts/ is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from checks import (
    ALL_TESTS,
    TIER_MAP,
    TEST_BY_ID,
)
from test_common import (
    BLUE,
    CYAN,
    FAIL,
    NC,
    SKIP,
    CleanupContext,
    print_result,
    print_summary,
    probe_services,
    write_json_report,
)


TIER_LABELS = {
    "precheck": "Precheck: Health Probes",
    "integration": "Integration: Bridge Flows",
    "seed": "Seed: Stack Verification",
}


def list_tests(ids: list[str]) -> None:
    """Print available tests grouped by tier."""
    current_tier = ""
    print("Available Tests:")
    for tid in ids:
        td = TEST_BY_ID.get(tid)
        if not td:
            continue
        if td.tier != current_tier:
            current_tier = td.tier
            print(f"\n{TIER_LABELS.get(current_tier, current_tier)}")
        print(f"  {td.test_id:15s} {td.title}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tiered test runner for Zephyr Bridge Orchestration",
    )
    parser.add_argument(
        "ids", nargs="*",
        help="Specific test IDs to run (e.g. INFRA-01 WRAP-01)",
    )
    parser.add_argument(
        "--tier", action="append", dest="tiers",
        choices=["precheck", "integration", "seed"],
        help="Run all tests in a tier (repeatable)",
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
    elif args.tiers:
        for tier in args.tiers:
            test_ids.extend(TIER_MAP.get(tier, []))
    else:
        # Default: all tiers
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

    # Check if integration tier is included (needs cleanup context for oracle/orderbook)
    has_integration = any(t.tier == "integration" for t in tests_to_run)

    # Run tests with dependency resolution
    results = []
    passed_ids: set[str] = set()
    ctx = CleanupContext() if has_integration else None

    try:
        if ctx:
            ctx.__enter__()

        for td in tests_to_run:
            # Check dependencies
            if td.depends_on:
                unmet = [dep for dep in td.depends_on if dep not in passed_ids]
                if unmet:
                    from test_common import ExecutionResult
                    r = ExecutionResult(
                        test_id=td.test_id,
                        result=SKIP,
                        detail=f"Skipped: depends on {', '.join(unmet)}",
                        level=td.level,
                        lane=td.lane,
                        priority="P0",
                    )
                    results.append(r)
                    print_result(r, verbose=args.verbose)
                    continue

            r = td.check(probes)
            results.append(r)
            if r.result == "PASS":
                passed_ids.add(td.test_id)
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
