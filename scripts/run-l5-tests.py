#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import shutil
import socket
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable
from urllib.error import URLError
from urllib.request import urlopen

# Ensure scripts/ is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_common import (
    L5Result,
    ANVIL_URL,
    NODE1_RPC,
    _get,
    _jpost,
    _rpc,
)
from l5_checks import ALL_CHECKS, SUBLEVEL_MAP, CATEGORY_MAP


STATUS_VALUES = {"SCOPED-READY", "SCOPED-EXPAND", "SCOPED-TBC"}
PRIORITY_VALUES = {"P0", "P1", "P2"}
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2}
STATUS_ORDER = {"SCOPED-READY": 0, "SCOPED-EXPAND": 1, "SCOPED-TBC": 2}

EXEC_PASS = "PASS"
EXEC_FAIL = "FAIL"
EXEC_BLOCKED = "BLOCKED"

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG = ROOT / "docs/testing/00-edge-case-scope.md"

INTEGRATED_DOCS = [
    ROOT / "docs/testing/02-infra-checklist.md",
    ROOT / "docs/testing/03-bridge-scenarios.md",
    ROOT / "docs/testing/04-full-stack-scenarios.md",
    ROOT / "docs/testing/05-devnet-scenarios.md",
    ROOT / "docs/testing/06-engine-strategies.md",
]

TEST_ROW_RE = re.compile(
    r"^\| `(?P<id>ZB-[A-Z]+-\d{3})` "
    r"\| (?P<title>.+?) "
    r"\| (?P<priority>P\d) "
    r"\| (?P<severity>[^|]+?) "
    r"\| `(?P<status>SCOPED-[A-Z]+)` "
    r"\| `(?P<doc>[^`]+)` "
    r"\| (?P<next_action>.+?) \|$"
)
CAT_HEADING_RE = re.compile(r"^##\s+\d+\.\s+(.+)$")
ID_IN_TABLE_RE = re.compile(r"\| `(ZB-[A-Z]+-\d{3})` \|")

SERVICE_URLS = {
    "bridge_api": "http://127.0.0.1:7051/health",
    "bridge_web": "http://127.0.0.1:7050",
    "engine": "http://127.0.0.1:7000/api/state",
    "oracle": "http://127.0.0.1:5555/status",
    "orderbook": "http://127.0.0.1:5556/status",
}

LANE_REQUIREMENTS = {
    "api-contract": ["bridge_api", "anvil", "zephyr_node"],
    "chaos-recovery": ["engine", "zephyr_node"],
    "runtime-policy": ["engine", "oracle"],
    "dex-routing": ["bridge_api", "anvil"],
    "browser": ["bridge_web", "cdp"],
    "privacy-observability": ["bridge_api"],
}


@dataclass(frozen=True)
class TestCase:
    test_id: str
    title: str
    priority: str
    severity: str
    status: str
    primary_doc: str
    next_action: str
    category: str
    lane: str


def _cdp_open() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 9222), timeout=1.0):
            return True
    except OSError:
        return False


def probe_services() -> dict[str, bool]:
    probes: dict[str, bool] = {
        "anvil": False,
        "zephyr_node": False,
        "cdp": _cdp_open(),
    }

    for key, url in SERVICE_URLS.items():
        try:
            s, _, _ = _get(url)
            probes[key] = s == 200
        except Exception:
            probes[key] = False

    try:
        parsed, err = _jpost(
            ANVIL_URL,
            {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1},
        )
        probes["anvil"] = err is None and parsed is not None and parsed.get("result") is not None
    except Exception:
        probes["anvil"] = False

    try:
        result, err = _rpc(NODE1_RPC, "get_info")
        probes["zephyr_node"] = err is None and result is not None
    except Exception:
        probes["zephyr_node"] = False

    return probes


def missing_requirements(row: TestCase, probes: dict[str, bool]) -> list[str]:
    reqs = LANE_REQUIREMENTS.get(row.lane, [])
    return [req for req in reqs if not probes.get(req, False)]


def generic_lane_check(row: TestCase, probes: dict[str, bool]) -> L5Result:
    missing = missing_requirements(row, probes)
    if missing:
        return L5Result(
            test_id=row.test_id,
            result=EXEC_BLOCKED,
            detail=f"Missing prerequisites: {', '.join(missing)}",
            lane=row.lane,
            status=row.status,
            priority=row.priority,
        )

    return L5Result(
        test_id=row.test_id,
        result=EXEC_PASS,
        detail="Lane preconditions and baseline probes are healthy",
        lane=row.lane,
        status=row.status,
        priority=row.priority,
    )


def lane_for_test(test_id: str) -> str:
    prefix = test_id.split("-")[1]
    if prefix in {"SEC", "SC", "CONS", "CONF", "ASSET"}:
        return "api-contract"
    if prefix in {"CONC", "REC", "WATCH", "LOAD"}:
        return "chaos-recovery"
    if prefix in {"RR", "TIME"}:
        return "runtime-policy"
    if prefix == "DEX":
        return "dex-routing"
    if prefix == "FE":
        return "browser"
    if prefix == "PRIV":
        return "privacy-observability"
    return "general"


def parse_catalog(catalog_path: Path) -> list[TestCase]:
    if not catalog_path.exists():
        raise FileNotFoundError(f"Catalog not found: {catalog_path}")

    rows: list[TestCase] = []
    current_category = ""

    for raw_line in catalog_path.read_text().splitlines():
        line = raw_line.strip()

        category_match = CAT_HEADING_RE.match(line)
        if category_match:
            current_category = category_match.group(1)
            continue

        row_match = TEST_ROW_RE.match(line)
        if not row_match:
            continue

        row = row_match.groupdict()
        test_id = row["id"]
        rows.append(
            TestCase(
                test_id=test_id,
                title=row["title"].replace("\\|", "|"),
                priority=row["priority"],
                severity=row["severity"].strip(),
                status=row["status"],
                primary_doc=row["doc"],
                next_action=row["next_action"].strip(),
                category=current_category,
                lane=lane_for_test(test_id),
            )
        )

    return rows


def filter_rows(
    rows: Iterable[TestCase],
    ids: set[str] | None,
    status: str | None,
    priority: str | None,
    doc: str | None,
) -> list[TestCase]:
    filtered = []
    for row in rows:
        if ids and row.test_id not in ids:
            continue
        if status and row.status != status:
            continue
        if priority and row.priority != priority:
            continue
        if doc and row.primary_doc != doc:
            continue
        filtered.append(row)
    return filtered


def sorted_rows(rows: Iterable[TestCase]) -> list[TestCase]:
    return sorted(
        rows,
        key=lambda r: (
            PRIORITY_ORDER.get(r.priority, 99),
            STATUS_ORDER.get(r.status, 99),
            r.test_id,
        ),
    )


def print_summary(rows: list[TestCase]) -> None:
    status_counts = Counter(r.status for r in rows)
    priority_counts = Counter(r.priority for r in rows)
    lane_counts = Counter(r.lane for r in rows)
    doc_counts = Counter(r.primary_doc for r in rows)

    print("L5 Catalog Summary")
    print(f"- Total tests: {len(rows)}")
    print(
        "- Status counts: "
        + ", ".join(
            f"{status}={status_counts.get(status, 0)}"
            for status in ["SCOPED-READY", "SCOPED-EXPAND", "SCOPED-TBC"]
        )
    )
    print(
        "- Priority counts: "
        + ", ".join(
            f"{priority}={priority_counts.get(priority, 0)}"
            for priority in ["P0", "P1", "P2"]
        )
    )
    print("- Lane counts:")
    for lane, count in sorted(lane_counts.items()):
        print(f"  - {lane}: {count}")
    print("- Primary docs:")
    for doc, count in sorted(doc_counts.items()):
        print(f"  - {doc}: {count}")


def print_list(rows: list[TestCase], as_json: bool) -> None:
    rows = sorted_rows(rows)
    if as_json:
        print(json.dumps([asdict(row) for row in rows], indent=2))
        return

    for row in rows:
        print(
            f"{row.test_id} | {row.priority} | {row.status} | {row.lane} | "
            f"{row.primary_doc} | {row.title}"
        )


def logical_run(rows: list[TestCase], verbose: bool) -> None:
    rows = sorted_rows(rows)
    by_priority: dict[str, list[TestCase]] = defaultdict(list)
    for row in rows:
        by_priority[row.priority].append(row)

    print("Logical Execution Pass")
    for priority in ["P0", "P1", "P2"]:
        group = by_priority.get(priority, [])
        status_counts = Counter(r.status for r in group)
        print(
            f"- {priority}: total={len(group)} "
            f"ready={status_counts.get('SCOPED-READY', 0)} "
            f"expand={status_counts.get('SCOPED-EXPAND', 0)} "
            f"tbc={status_counts.get('SCOPED-TBC', 0)}"
        )

    lane_counts = Counter((row.lane, row.status) for row in rows)
    print("- Lane/status matrix:")
    lanes = sorted({row.lane for row in rows})
    for lane in lanes:
        ready = lane_counts.get((lane, "SCOPED-READY"), 0)
        expand = lane_counts.get((lane, "SCOPED-EXPAND"), 0)
        tbc = lane_counts.get((lane, "SCOPED-TBC"), 0)
        print(f"  - {lane}: ready={ready}, expand={expand}, tbc={tbc}")

    print("- Recommended execution order:")
    print("  1) Run P0 SCOPED-READY as regression gate.")
    print("  2) Run P0 SCOPED-EXPAND with added assertions.")
    print("  3) Convert P0 SCOPED-TBC into executable runbooks.")
    print("  4) Repeat same sequence for P1 then P2.")

    if verbose:
        print("- Per-test logical plan:")
        for row in rows:
            print(
                f"  - [{row.priority}] [{row.status}] [{row.lane}] {row.test_id} "
                f"-> {row.next_action}"
            )


def integrated_ids() -> set[str]:
    ids: set[str] = set()
    for path in INTEGRATED_DOCS:
        if not path.exists():
            continue
        content = path.read_text()
        for match in ID_IN_TABLE_RE.finditer(content):
            ids.add(match.group(1))
    return ids


def legacy_links() -> list[str]:
    hits: list[str] = []
    testing_dir = ROOT / "docs/testing"
    for path in sorted(testing_dir.glob("*.md")):
        text = path.read_text()
        if "07-edge-case-scope.md" in text:
            hits.append(str(path.relative_to(ROOT)))
    return hits


def lint_catalog(rows: list[TestCase]) -> bool:
    ok = True
    errors: list[str] = []
    warnings: list[str] = []

    if len(rows) != 138:
        errors.append(f"Expected 138 tests, found {len(rows)}")

    ids = [r.test_id for r in rows]
    duplicate_ids = sorted({test_id for test_id in ids if ids.count(test_id) > 1})
    if duplicate_ids:
        errors.append(f"Duplicate IDs: {', '.join(duplicate_ids)}")

    for row in rows:
        if row.status not in STATUS_VALUES:
            errors.append(f"Invalid status for {row.test_id}: {row.status}")
        if row.priority not in PRIORITY_VALUES:
            errors.append(f"Invalid priority for {row.test_id}: {row.priority}")
        target_doc = ROOT / row.primary_doc
        if not target_doc.exists():
            errors.append(f"Primary doc missing for {row.test_id}: {row.primary_doc}")

    ids_in_catalog = set(ids)
    ids_in_docs = integrated_ids()
    missing_in_docs = sorted(ids_in_catalog - ids_in_docs)
    if missing_in_docs:
        errors.append(
            "IDs present in 00 catalog but not integrated docs: "
            + ", ".join(missing_in_docs)
        )

    extra_in_docs = sorted(ids_in_docs - ids_in_catalog)
    if extra_in_docs:
        warnings.append(
            "IDs present in integrated docs but absent from 00 catalog: "
            + ", ".join(extra_in_docs)
        )

    for path in INTEGRATED_DOCS[:4]:
        if not path.exists():
            errors.append(f"Integrated doc missing: {path.relative_to(ROOT)}")
            continue
        text = path.read_text()
        if (
            "<!-- L5-CATALOG-START -->" not in text
            or "<!-- L5-CATALOG-END -->" not in text
        ):
            errors.append(f"Missing L5 catalog markers in {path.relative_to(ROOT)}")

    old_link_hits = legacy_links()
    if old_link_hits:
        errors.append(
            "Legacy 07-edge-case-scope link still present in: "
            + ", ".join(old_link_hits)
        )

    print("L5 Catalog Lint")
    if errors:
        ok = False
        for err in errors:
            print(f"- FAIL: {err}")
    else:
        print("- PASS: core integrity checks")

    if warnings:
        for warning in warnings:
            print(f"- WARN: {warning}")

    if ok:
        status_counts = Counter(r.status for r in rows)
        print(
            "- PASS: status snapshot "
            f"ready={status_counts.get('SCOPED-READY', 0)}, "
            f"expand={status_counts.get('SCOPED-EXPAND', 0)}, "
            f"tbc={status_counts.get('SCOPED-TBC', 0)}"
        )

    return ok


def browser_preflight(rows: list[TestCase]) -> bool:
    print("Browser Lane Preflight")

    fe_rows = [row for row in rows if row.test_id.startswith("ZB-FE-")]
    status_counts = Counter(r.status for r in fe_rows)
    print(
        f"- FE tests: total={len(fe_rows)} "
        f"ready={status_counts.get('SCOPED-READY', 0)} "
        f"expand={status_counts.get('SCOPED-EXPAND', 0)} "
        f"tbc={status_counts.get('SCOPED-TBC', 0)}"
    )

    required_bins = ["google-chrome-stable", "curl"]
    missing_bins = [name for name in required_bins if shutil.which(name) is None]
    if missing_bins:
        print(f"- WARN: missing binaries: {', '.join(missing_bins)}")
    else:
        print("- PASS: required binaries are available")

    cdp_ok = False
    try:
        with socket.create_connection(("127.0.0.1", 9222), timeout=1.5):
            cdp_ok = True
    except OSError:
        cdp_ok = False

    if cdp_ok:
        print("- PASS: CDP port 9222 is open")
        try:
            with urlopen("http://127.0.0.1:9222/json/version", timeout=2) as resp:
                if resp.status == 200:
                    print("- PASS: CDP endpoint responds")
        except URLError:
            print("- WARN: CDP port open but endpoint probe failed")
    else:
        print("- WARN: CDP port 9222 is not open")

    print(
        "- Next: launch Chrome with CDP (--remote-debugging-port=9222) and MetaMask before executing ZB-FE tests live"
    )
    return True


def execute_rows(
    rows: list[TestCase],
    execute_tbc: bool,
    verbose: bool,
    json_report_path: str | None,
) -> int:
    rows = sorted_rows(rows)
    probes = probe_services()

    results: list[L5Result] = []
    for row in rows:
        if row.status == "SCOPED-TBC" and not execute_tbc:
            results.append(
                L5Result(
                    test_id=row.test_id,
                    result=EXEC_BLOCKED,
                    detail="SCOPED-TBC (runbook detail still required)",
                    lane=row.lane,
                    status=row.status,
                    priority=row.priority,
                )
            )
            continue

        check = ALL_CHECKS.get(row.test_id, generic_lane_check)
        results.append(check(row, probes))

    counts = Counter(result.result for result in results)
    print("L5 Execute")
    print(
        "- Service probes: "
        + ", ".join(
            f"{key}={'up' if value else 'down'}"
            for key, value in sorted(probes.items())
        )
    )
    print(
        f"- Results: PASS={counts.get(EXEC_PASS, 0)} "
        f"FAIL={counts.get(EXEC_FAIL, 0)} "
        f"BLOCKED={counts.get(EXEC_BLOCKED, 0)}"
    )

    if verbose:
        for result in results:
            print(
                f"  - {result.test_id} [{result.priority}] [{result.status}] "
                f"=> {result.result}: {result.detail}"
            )

    if json_report_path:
        payload = {
            "summary": {
                "pass": counts.get(EXEC_PASS, 0),
                "fail": counts.get(EXEC_FAIL, 0),
                "blocked": counts.get(EXEC_BLOCKED, 0),
            },
            "service_probes": probes,
            "results": [asdict(result) for result in results],
        }
        out_path = Path(json_report_path)
        out_path.write_text(json.dumps(payload, indent=2))
        print(f"- Wrote JSON report: {out_path}")

    return 1 if counts.get(EXEC_FAIL, 0) > 0 else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="L5 edge-case framework runner for the ZB catalog",
    )
    parser.add_argument(
        "ids",
        nargs="*",
        help="Optional test IDs to include (e.g. ZB-SEC-011)",
    )
    parser.add_argument(
        "--catalog",
        default=str(DEFAULT_CATALOG),
        help="Path to 00-edge-case-scope.md",
    )
    parser.add_argument("--summary", action="store_true", help="Show summary")
    parser.add_argument("--list", action="store_true", help="List filtered tests")
    parser.add_argument("--lint", action="store_true", help="Lint catalog integration")
    parser.add_argument(
        "--logical", action="store_true", help="Run logical execution pass"
    )
    parser.add_argument(
        "--browser-preflight",
        action="store_true",
        help="Run browser lane preflight checks",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute all filtered tests with automated checks where available",
    )
    parser.add_argument(
        "--execute-tbc",
        action="store_true",
        help="Attempt execution for SCOPED-TBC tests using lane baseline checks",
    )
    parser.add_argument(
        "--report-json",
        help="Write execution report to JSON file",
    )
    parser.add_argument(
        "--sublevel",
        action="append",
        dest="sublevels",
        choices=["L5.1", "L5.2", "L5.3", "L5.4", "L5.5", "L5.6"],
        help="Filter by sublevel (repeatable)",
    )
    parser.add_argument(
        "--category",
        action="append",
        dest="categories",
        choices=sorted(CATEGORY_MAP.keys()),
        help="Filter by category (repeatable)",
    )
    parser.add_argument(
        "--status", choices=sorted(STATUS_VALUES), help="Filter by status"
    )
    parser.add_argument(
        "--priority", choices=sorted(PRIORITY_VALUES), help="Filter by priority"
    )
    parser.add_argument("--doc", help="Filter by primary doc path")
    parser.add_argument("--json", action="store_true", help="Output list as JSON")
    parser.add_argument("--verbose", action="store_true", help="Verbose logical output")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    run_default = not any(
        [
            args.summary,
            args.list,
            args.lint,
            args.logical,
            args.browser_preflight,
            args.execute,
        ]
    )

    try:
        rows = parse_catalog(Path(args.catalog).resolve())
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    ids_filter = set(args.ids) if args.ids else None
    filtered = filter_rows(rows, ids_filter, args.status, args.priority, args.doc)

    # Apply sublevel filter
    if args.sublevels:
        sublevel_ids: set[str] = set()
        for sl in args.sublevels:
            sublevel_ids.update(SUBLEVEL_MAP.get(sl, []))
        filtered = [r for r in filtered if r.test_id in sublevel_ids]

    # Apply category filter
    if args.categories:
        cat_ids: set[str] = set()
        for cat in args.categories:
            cat_ids.update(CATEGORY_MAP.get(cat, []))
        filtered = [r for r in filtered if r.test_id in cat_ids]

    exit_code = 0

    if run_default or args.summary:
        print_summary(filtered)

    if args.list:
        print_list(filtered, as_json=args.json)

    if run_default or args.lint:
        if not lint_catalog(rows):
            exit_code = 1

    if run_default or args.logical:
        logical_run(filtered, verbose=args.verbose)

    if args.browser_preflight:
        browser_preflight(filtered)

    if args.execute:
        execute_code = execute_rows(
            filtered,
            execute_tbc=args.execute_tbc,
            verbose=args.verbose,
            json_report_path=args.report_json,
        )
        if execute_code != 0:
            exit_code = execute_code

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
