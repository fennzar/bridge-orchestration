#!/usr/bin/env python3
"""Engine Test Suite Runner.

Usage:
    python scripts/engine_tests/runner.py                   # all tests
    python scripts/engine_tests/runner.py --category ARB    # category filter
    python scripts/engine_tests/runner.py --module arb_gates # module filter
    python scripts/engine_tests/runner.py PRE-01 ARB-E05    # specific IDs
    python scripts/engine_tests/runner.py --list             # list all tests
    python scripts/engine_tests/runner.py --verbose          # detailed output
    python scripts/engine_tests/runner.py --report-json /tmp/report.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Ensure scripts/ is on sys.path for test_common imports
scripts_dir = str(Path(__file__).resolve().parent.parent)
if scripts_dir not in sys.path:
    sys.path.insert(0, scripts_dir)

from test_common import (
    PASS, FAIL, BLOCKED, SKIP,
    GREEN, RED, YELLOW, CYAN, NC,
    probe_services,
)

from engine_tests import collect_all_tests


def run_test(test_id: str, info: dict, probes: dict, verbose: bool) -> dict:
    """Run a single test. Returns result dict."""
    fn = info["fn"]

    # Check if it's a stub (body is just `pass`)
    import inspect
    source = inspect.getsource(fn)
    is_stub = source.strip().endswith("pass")

    if is_stub:
        result = {"test_id": test_id, "result": SKIP, "detail": "Not yet implemented"}
    else:
        try:
            result = fn(probes)
            if result is None:
                result = {"test_id": test_id, "result": SKIP, "detail": "No result returned"}
            elif isinstance(result, str):
                result = {"test_id": test_id, "result": result, "detail": ""}
        except Exception as e:
            result = {"test_id": test_id, "result": FAIL, "detail": f"Exception: {e}"}

    if not isinstance(result, dict):
        result = {"test_id": test_id, "result": SKIP, "detail": str(result)}

    result.setdefault("test_id", test_id)
    result.setdefault("module", info.get("module", ""))
    result.setdefault("category", info.get("category", ""))

    # Print
    color = {PASS: GREEN, FAIL: RED, BLOCKED: YELLOW, SKIP: YELLOW}.get(
        result["result"], NC)
    tag = f"[{result['result']}]"
    print(f"  {color}{tag:10s}{NC} {test_id}", end="")
    if verbose and result.get("detail"):
        print(f"  {result['detail']}", end="")
    print()

    return result


def main():
    parser = argparse.ArgumentParser(description="Engine Test Suite")
    parser.add_argument("ids", nargs="*", help="Specific test IDs to run")
    parser.add_argument("--category", "-c", help="Filter by category prefix (ARB, PEG, etc.)")
    parser.add_argument("--module", "-m", help="Filter by module name")
    parser.add_argument("--list", "-l", action="store_true", help="List tests without running")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--report-json", help="Write JSON report to path")
    args = parser.parse_args()

    all_tests = collect_all_tests()

    # Filter
    if args.ids:
        tests = {k: v for k, v in all_tests.items() if k in args.ids}
    elif args.category:
        cat = args.category.upper()
        tests = {k: v for k, v in all_tests.items() if k.startswith(cat)}
    elif args.module:
        tests = {k: v for k, v in all_tests.items() if v["module"] == args.module}
    else:
        tests = all_tests

    if args.list:
        for tid, info in sorted(tests.items()):
            doc = (info["fn"].__doc__ or "").strip().split("\n")[0]
            print(f"  {tid:20s}  {info['module']:20s}  {doc}")
        print(f"\n  {len(tests)} tests total")
        return

    print(f"\n{'='*60}")
    print(f"  Engine Test Suite — {len(tests)} tests")
    print(f"{'='*60}\n")

    # Probe services
    probes = probe_services()
    up = [k for k, v in probes.items() if v]
    down = [k for k, v in probes.items() if not v]
    print(f"  Services UP:   {', '.join(up) or 'none'}")
    if down:
        print(f"  Services DOWN: {', '.join(down)}")
    print()

    # Run tests
    results = []
    t0 = time.time()
    current_module = None

    for tid, info in sorted(tests.items()):
        if info["module"] != current_module:
            current_module = info["module"]
            print(f"\n  --- {current_module} ---")
        results.append(run_test(tid, info, probes, args.verbose))

    elapsed = time.time() - t0

    # Summary
    counts = {PASS: 0, FAIL: 0, BLOCKED: 0, SKIP: 0}
    for r in results:
        counts[r["result"]] = counts.get(r["result"], 0) + 1

    print(f"\n{'='*60}")
    print(f"  {GREEN}PASS:{NC}    {counts[PASS]}")
    print(f"  {RED}FAIL:{NC}    {counts[FAIL]}")
    if counts[BLOCKED]:
        print(f"  {YELLOW}BLOCKED:{NC} {counts[BLOCKED]}")
    if counts[SKIP]:
        print(f"  {YELLOW}SKIP:{NC}    {counts[SKIP]}")
    print(f"  Time:    {elapsed:.1f}s")
    print(f"{'='*60}\n")

    # JSON report
    if args.report_json:
        payload = {
            "summary": counts,
            "service_probes": probes,
            "elapsed_seconds": round(elapsed, 1),
            "results": results,
        }
        Path(args.report_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.report_json).write_text(json.dumps(payload, indent=2))
        print(f"  Wrote: {args.report_json}")

    sys.exit(1 if counts[FAIL] > 0 else 0)


if __name__ == "__main__":
    main()
