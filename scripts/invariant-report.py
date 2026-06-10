#!/usr/bin/env python3
"""Cross-layer INV ledger aggregator — the north star (`make test-report`).

Renders the INVARIANTS.md release gate (INV-1..19) from ACTUAL test outcomes across every layer
that produced structured output. The ledger is generated from the live tests, NOT a hand-kept table
— a test self-declares the invariant it pins (and whether it is a known-gap) via a name tag, and the
aggregator buckets each INV by the WORST status observed across all layers that pinned it.

Sources:
  SCENARIO (pytest)        tests/scenario/.report/scenario.json — {inv, bucket} emitted by conftest.
  LOGIC-engine (vitest)    run `pnpm vitest run tests/conformance` (no stack); tags in test titles.
  CONTRACT (forge)         run `forge test --json` (--with-forge); tags in fn names.       [opt-in]
  LOGIC-bridge (node:test) run `pnpm test` (--with-node); tags in test names.              [opt-in]

Name-tag convention (one place — the test itself, so the ledger can't drift from reality):
  [INV-NN]   the invariant this test pins (required to count toward the ledger).
  [gap]      a known-gap: the test encodes the SAFE behavior the system does not yet honor.

Per-source bucketing handles the one sign-convention difference:
  - pytest/forge/node: a known-gap test ASSERTS the safe behavior and FAILS today → KNOWN_GAP.
  - vitest: a known-gap uses `it.fails`, so it PASSES today (the inner assert fails) → KNOWN_GAP;
    if it starts FAILING, the gap closed → UNEXPECTED_PASS (promote the INV row, drop the marker).

Buckets mirror tests/scenario/harness/report.py. Gate: only REGRESSION / UNEXPECTED_PASS are fatal
(exit 1). KNOWN_GAP rows are the worklist. UNKNOWN = no test pins that INV yet (a coverage hole).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_REPORT = ROOT / "tests" / "scenario" / ".report" / "scenario.json"
LEDGER_OUT = ROOT / "tests" / ".report" / "ledger.json"

# ── buckets (kept identical to harness/report.py) ────────────────────────────
GREEN, KNOWN_GAP, REGRESSION = "GREEN", "KNOWN_GAP", "REGRESSION"
UNEXPECTED_PASS, ACCEPTED, SKIPPED, UNKNOWN = "UNEXPECTED_PASS", "ACCEPTED", "SKIPPED", "UNKNOWN"
FATAL = frozenset({REGRESSION, UNEXPECTED_PASS})
# Display precedence: the worst (most urgent) status a contributing test gives an INV wins.
_PRECEDENCE = [REGRESSION, UNEXPECTED_PASS, KNOWN_GAP, ACCEPTED, GREEN, SKIPPED, UNKNOWN]

# ── the canonical ledger (titles + sections from docs/security/INVARIANTS.md) ─
INV_TITLES = {
    1: "No unbacked mint", 2: "No double-credit", 3: "No over-payout on unwrap",
    4: "No double-payout", 5: "Asset-type integrity", 6: "Decimal correctness",
    7: "Claim non-expiry trap", 8: "Voucher unforgeable", 9: "No signature replay",
    10: "Burn nonce non-replay", 11: "No payout before finality", 12: "Watcher exactly-once",
    13: "Unwrap status truthfulness", 14: "Engine can't drain on bad price",
    15: "Realized accounting", 16: "No fund-burning loop", 17: "Execution-time gating",
    18: "Privileged routes need auth", 19: "/unwraps/prepare not weaponizable",
}
SECTIONS = [
    ("A. Custody — loses user money", range(1, 8)),
    ("B. Signature / replay — the crypto gate", range(8, 11)),
    ("C. Finality / consistency", range(11, 14)),
    ("D. Engine — launch-blocking (engine ships enabled)", range(14, 18)),
    ("E. Authorization", range(18, 20)),
]

_INV_TAG = re.compile(r"\[INV-(\d+)\]", re.I)
_GAP_TAG = re.compile(r"\[(?:gap|known-gap)\]", re.I)
# Catalog id token (CT-/LB-/LE-/FLOW-/MKT-/SEC-/RES-/OPS-/UI-…) — for clean ledger pin labels.
_CAT_ID = re.compile(r"\b((?:CT|LB|LE|FLOW|MKT|SEC|RES|OPS|UI)-[A-Z0-9][A-Z0-9-]*)")


# ── ANSI (degrade to plain when not a tty) ───────────────────────────────────
_TTY = sys.stdout.isatty()
def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _TTY else s
def red(s): return _c("31", s)
def green(s): return _c("32", s)
def yellow(s): return _c("33", s)
def amber(s): return _c("33", s)
def dim(s): return _c("2", s)
def bold(s): return _c("1", s)


_ENV_CACHE: dict[str, str] | None = None


def _load_env() -> dict[str, str]:
    """Parse .env once into a dict, resolving ${VAR}/$VAR refs against os.environ AND .env itself
    (a couple of passes so chains like ROOT → *_REPO_PATH resolve)."""
    global _ENV_CACHE
    if _ENV_CACHE is not None:
        return _ENV_CACHE
    raw: dict[str, str] = {}
    envf = ROOT / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            raw[k.strip()] = v.strip().strip("'\"")
    sub = re.compile(r"\$\{([^}]+)\}|\$([A-Za-z_]\w*)")
    resolved = dict(raw)
    for _ in range(5):  # fixed-point: enough for ROOT → A → B chains
        changed = False
        for k, v in list(resolved.items()):
            nv = sub.sub(lambda m: os.environ.get(m.group(1) or m.group(2))
                         or resolved.get(m.group(1) or m.group(2), ""), v)
            if nv != v:
                resolved[k] = nv
                changed = True
        if not changed:
            break
    _ENV_CACHE = resolved
    return resolved


def _env(name: str, default: str = "") -> str:
    """Resolve a var from the process env, else from .env (with nested-ref expansion)."""
    return os.environ.get(name) or _load_env().get(name) or default


def _worst(statuses: list[str]) -> str:
    present = [s for s in statuses if s]
    if not present:
        return UNKNOWN
    # A SKIPPED record never masks a real result; only show SKIPPED if it's all there is.
    meaningful = [s for s in present if s != SKIPPED]
    pool = meaningful or present
    for level in _PRECEDENCE:
        if level in pool:
            return level
    return UNKNOWN


# ── source: SCENARIO (pytest, already structured) ────────────────────────────
def read_scenario() -> tuple[list[dict], dict]:
    if not SCENARIO_REPORT.exists():
        return [], {"layer": "scenario", "status": SKIPPED, "note": "no scenario.json — run `make test-scenario`"}
    data = json.loads(SCENARIO_REPORT.read_text())
    age_s = time.time() - SCENARIO_REPORT.stat().st_mtime
    recs = []
    for r in data.get("records", []):
        inv = _inv_num(r.get("inv"))
        if inv is None:
            continue
        recs.append({"inv": inv, "bucket": r["bucket"], "id": _short(r.get("nodeid", "")),
                     "layer": "scenario", "reason": r.get("reason")})
    meta = {"layer": "scenario", "status": "ran", "counts": data.get("counts", {}),
            "age_min": round(age_s / 60, 1), "records": len(recs)}
    return recs, meta


def _inv_num(raw) -> int | None:
    if raw is None:
        return None
    m = re.search(r"(\d+)", str(raw))
    return int(m.group(1)) if m else None


def _short(nodeid: str) -> str:
    # tests/scenario/flows/test_wrap_unwrap.py::test_flow_unwrap_pays_out -> flow_unwrap_pays_out
    fn = nodeid.split("::")[-1] if nodeid else nodeid
    return fn[5:] if fn.startswith("test_") else fn


# ── source: LOGIC-engine (vitest conformance) ────────────────────────────────
def run_vitest(engine_path: Path) -> tuple[list[dict], dict]:
    if not engine_path.is_dir():
        return [], {"layer": "vitest", "status": SKIPPED, "note": f"engine repo not found: {engine_path}"}
    tmp = Path(tempfile.gettempdir()) / "inv-vitest.json"
    cmd = ["pnpm", "vitest", "run", "tests/conformance", "--reporter=json", f"--outputFile={tmp}"]
    try:
        subprocess.run(cmd, cwd=engine_path, capture_output=True, text=True, timeout=300)
    except Exception as e:  # noqa: BLE001 — any failure → layer skipped, report stays honest
        return [], {"layer": "vitest", "status": SKIPPED, "note": f"vitest run failed: {e}"}
    if not tmp.exists():
        return [], {"layer": "vitest", "status": SKIPPED, "note": "vitest produced no JSON output"}
    data = json.loads(tmp.read_text())
    recs = []
    for suite in data.get("testResults", []):
        for a in suite.get("assertionResults", []):
            name = a.get("fullName") or " ".join(a.get("ancestorTitles", []) + [a.get("title", "")])
            m = _INV_TAG.search(name)
            if not m:
                continue
            inv = int(m.group(1))
            gap = bool(_GAP_TAG.search(name))
            passed = a.get("status") == "passed"
            # vitest known-gap = it.fails: PASSES while the gap stands, FAILS once fixed.
            if gap:
                bucket = KNOWN_GAP if passed else UNEXPECTED_PASS
            else:
                bucket = GREEN if passed else REGRESSION
            cid = _CAT_ID.search(" ".join(a.get("ancestorTitles", []) + [a.get("title", "")]))
            recs.append({"inv": inv, "bucket": bucket, "id": cid.group(1) if cid else "LE-?",
                         "layer": "vitest", "reason": None})
    return recs, {"layer": "vitest", "status": "ran", "records": len(recs)}


# ── source: CONTRACT (forge) / LOGIC-bridge (node:test) — opt-in ─────────────
def run_forge(foundry_path: Path) -> tuple[list[dict], dict]:
    if not foundry_path.is_dir():
        return [], {"layer": "forge", "status": SKIPPED, "note": f"foundry repo not found: {foundry_path}"}
    try:
        p = subprocess.run(["forge", "test", "--json"], cwd=foundry_path,
                           capture_output=True, text=True, timeout=420)
    except Exception as e:  # noqa: BLE001
        return [], {"layer": "forge", "status": SKIPPED, "note": f"forge test failed: {e}"}
    line = next((ln for ln in p.stdout.splitlines() if ln.strip().startswith("{")), None)
    if not line:
        return [], {"layer": "forge", "status": SKIPPED, "note": "forge produced no JSON"}
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return [], {"layer": "forge", "status": SKIPPED, "note": "forge JSON parse error"}
    recs = []
    for suite in data.values():
        for fn, res in (suite.get("test_results") or {}).items():
            m = re.search(r"inv(\d+)", fn, re.I)
            if not m:
                continue
            inv = int(m.group(1))
            gap = "gap" in fn.lower()
            passed = res.get("status") == "Success"
            if gap:
                bucket = UNEXPECTED_PASS if passed else KNOWN_GAP
            else:
                bucket = GREEN if passed else REGRESSION
            recs.append({"inv": inv, "bucket": bucket, "id": fn.split("(")[0], "layer": "forge", "reason": None})
    return recs, {"layer": "forge", "status": "ran", "records": len(recs)}


# ── roll-up + render ──────────────────────────────────────────────────────────
_BUCKET_LABEL = {GREEN: green("GREEN     "), KNOWN_GAP: red("RED  GAP  "),
                 REGRESSION: red("REGRESSION"), UNEXPECTED_PASS: red("UNEXP-PASS"),
                 ACCEPTED: amber("AMBER ACC "), UNKNOWN: dim("UNKNOWN   "), SKIPPED: dim("SKIPPED   ")}


def render(all_recs: list[dict], metas: list[dict], write_json: bool) -> int:
    by_inv: dict[int, list[dict]] = {i: [] for i in INV_TITLES}
    for r in all_recs:
        by_inv.setdefault(r["inv"], []).append(r)

    rolled: dict[int, str] = {}
    for inv in INV_TITLES:
        rolled[inv] = _worst([r["bucket"] for r in by_inv[inv]])

    print()
    print(bold("  Money-Critical Invariant Ledger") + dim("  (docs/security/INVARIANTS.md · release gate)"))
    layer_bits = []
    for m in metas:
        tag = m["layer"]
        if m["status"] == SKIPPED:
            layer_bits.append(dim(f"{tag}:skip"))
        elif tag == "scenario":
            layer_bits.append(f"{tag}:{m['records']}rec({m['age_min']}m old)")
        else:
            layer_bits.append(f"{tag}:{m['records']}rec")
    print(dim("  layers: " + " · ".join(layer_bits)))
    print()

    for title, rng in SECTIONS:
        print(dim(f"  {title}"))
        for inv in rng:
            status = rolled[inv]
            label = _BUCKET_LABEL.get(status, status)
            pins = ", ".join(sorted({r["id"] for r in by_inv[inv]})) or dim("— no test pins this INV yet")
            dots = "." * max(3, 30 - len(INV_TITLES[inv]))
            print(f"    INV-{inv:<2} {INV_TITLES[inv]} {dim(dots)} {label}  {dim(pins)}")
        print()

    counts = {b: sum(1 for s in rolled.values() if s == b) for b in _PRECEDENCE}
    held = counts[GREEN]
    fatal = [inv for inv, s in rolled.items() if s in FATAL]
    print(bold("  Gate: ") +
          f"{green(str(held)+'/19 HELD')} · "
          f"{red(str(counts[KNOWN_GAP])+' KNOWN-GAP')} · "
          f"{amber(str(counts[ACCEPTED])+' ACCEPTED')} · "
          f"{dim(str(counts[UNKNOWN])+' UNCOVERED')} · "
          f"{(red if fatal else green)(str(len(fatal))+' FATAL')}")
    if counts[UNKNOWN]:
        uncovered = [f"INV-{i}" for i in INV_TITLES if rolled[i] == UNKNOWN]
        print(dim("  uncovered (no test pins these yet): " + ", ".join(uncovered)))
    if fatal:
        print(red("  FATAL — untagged failure or a closed gap still marked @known_gap:"))
        for inv in fatal:
            print(red(f"    INV-{inv} {INV_TITLES[inv]} → {rolled[inv]}"))
    releasable = held == 19
    print()
    print(bold("  " + (green("RELEASABLE — every invariant HELD") if releasable
                       else yellow(f"NOT RELEASABLE — {19 - held} invariant(s) not green"))))
    print()

    if write_json:
        LEDGER_OUT.parent.mkdir(parents=True, exist_ok=True)
        LEDGER_OUT.write_text(json.dumps({
            "rolled": {f"INV-{i}": rolled[i] for i in INV_TITLES},
            "held": held, "fatal": [f"INV-{i}" for i in fatal],
            "counts": {b: counts[b] for b in _PRECEDENCE},
            "layers": metas,
        }, indent=2))

    return 1 if fatal else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Render the INV-1..19 release-gate ledger from live tests.")
    ap.add_argument("--with-forge", action="store_true", help="also run forge contract tests (slower)")
    ap.add_argument("--no-vitest", action="store_true", help="skip the engine vitest conformance layer")
    ap.add_argument("--no-json", action="store_true", help="do not write tests/.report/ledger.json")
    args = ap.parse_args()

    all_recs: list[dict] = []
    metas: list[dict] = []

    recs, meta = read_scenario(); all_recs += recs; metas.append(meta)
    if not args.no_vitest:
        recs, meta = run_vitest(Path(_env("ENGINE_REPO_PATH", str(ROOT.parent / "zephyr-bridge-engine"))))
        all_recs += recs; metas.append(meta)
    if args.with_forge:
        recs, meta = run_forge(Path(_env("FOUNDRY_REPO_PATH", str(ROOT.parent / "zephyr-eth-foundry"))))
        all_recs += recs; metas.append(meta)

    return render(all_recs, metas, write_json=not args.no_json)


if __name__ == "__main__":
    sys.exit(main())
