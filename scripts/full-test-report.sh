#!/bin/bash
set -e

# Zephyr Bridge Unified Test Runner
# Runs all tiers (L1-L4) and edge-cases (L5), then generates a markdown report.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORTS_DIR="$ROOT/reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_MD="$REPORTS_DIR/full-test-report_$TIMESTAMP.md"
LATEST_REPORT_MD="$REPORTS_DIR/full-test-report.md"

mkdir -p "$REPORTS_DIR"

echo "==========================================="
echo "  Zephyr Bridge Unified Test Suite"
echo "==========================================="
echo "Started at: $(date)"

# 1. Run L1-L4 Tiers
echo -e "\n[1/2] Running L1-L4 Tiers..."
python3 "$ROOT/scripts/run-tests.py" --report-json "$REPORTS_DIR/tiers.json" || true

# 2. Run L5 Edge-Cases
echo -e "\n[2/2] Running L5 Edge-Cases..."
python3 "$ROOT/scripts/run-l5-tests.py" --execute --execute-tbc --report-json "$REPORTS_DIR/l5.json" || true

# 3. Generate Unified Markdown Report
echo -e "\nGenerating Unified Report..."

cat > "$REPORT_MD" <<EOF
# Zephyr Bridge Unified Test Report
**Date:** $(date)
**Environment:** devnet

## Summary

EOF

# Add summaries from JSONs using python (since it's already there)
python3 - <<EOF >> "$REPORT_MD"
import json
from pathlib import Path

reports_dir = Path("$REPORTS_DIR")
tiers_file = reports_dir / "tiers.json"
l5_file = reports_dir / "l5.json"

def get_summary(path):
    if not path.exists():
        return "Not found", 0, 0, 0, 0
    data = json.loads(path.read_text())
    s = data.get("summary", {})
    return "OK", s.get("pass", 0), s.get("fail", 0), s.get("blocked", 0), s.get("skip", 0)

t_status, t_pass, t_fail, t_blocked, t_skip = get_summary(tiers_file)
l_status, l_pass, l_fail, l_blocked, l_skip = get_summary(l5_file)

print(f"| Suite | Status | Pass | Fail | Blocked | Skip |")
print(f"|-------|--------|------|------|---------|------|")
print(f"| L1-L4 Tiers | {t_status} | {t_pass} | {t_fail} | {t_blocked} | {t_skip} |")
print(f"| L5 Edge-Cases | {l_status} | {l_pass} | {l_fail} | {l_blocked} | {l_skip} |")
print(f"\n**Total Pass:** {t_pass + l_pass}")
print(f"**Total Fail:** {t_fail + l_fail}")
EOF

cat >> "$REPORT_MD" <<EOF

## Service Probes
EOF

python3 - <<EOF >> "$REPORT_MD"
import json
from pathlib import Path

reports_dir = Path("$REPORTS_DIR")
tiers_file = reports_dir / "tiers.json"

if tiers_file.exists():
    data = json.loads(tiers_file.read_text())
    probes = data.get("service_probes", {})
    print("| Service | Status |")
    print("|---------|--------|")
    for s, up in sorted(probes.items()):
        print(f"| {s} | {'✅ UP' if up else '❌ DOWN'} |")
else:
    print("Service probe data unavailable.")
EOF

cat >> "$REPORT_MD" <<EOF

## Failed/Blocked Tests
EOF

python3 - <<EOF >> "$REPORT_MD"
import json
from pathlib import Path

reports_dir = Path("$REPORTS_DIR")

def print_issues(path, label):
    if not path.exists(): return
    data = json.loads(path.read_text())
    issues = [r for r in data.get("results", []) if r.get("result") in ("FAIL", "BLOCKED")]
    if not issues:
        print(f"### {label}: None 🎉")
        return
    print(f"### {label}")
    print("| ID | Result | Detail |")
    print("|----|--------|--------|")
    for r in issues:
        print(f"| {r.get('test_id')} | {r.get('result')} | {r.get('detail')} |")

print_issues(reports_dir / "tiers.json", "L1-L4 Tiers")
print_issues(reports_dir / "l5.json", "L5 Edge-Cases")
EOF

# Link latest
cp "$REPORT_MD" "$LATEST_REPORT_MD"

echo -e "\nReport saved to: $REPORT_MD"
echo "Link: $LATEST_REPORT_MD"
echo "==========================================="
