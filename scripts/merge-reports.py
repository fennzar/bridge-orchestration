#!/usr/bin/env python3
import json
import sqlite3
import sys
import datetime
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        print("Usage: merge-reports.py <reports_dir>")
        sys.exit(1)

    reports_dir = Path(sys.argv[1])
    if not reports_dir.exists() or not reports_dir.is_dir():
        print(f"Error: {reports_dir} not found")
        sys.exit(1)

    all_reports = []
    total_pass = 0
    total_fail = 0
    total_blocked = 0
    global_probes = {}
    failed_tests = []

    for p in sorted(reports_dir.glob("*.json")):
        try:
            with open(p, "r") as f:
                data = json.load(f)
                
            report_name = p.stem
            all_reports.append((report_name, data))
            
            summary = data.get("summary", {})
            total_pass += summary.get("pass", 0)
            total_fail += summary.get("fail", 0)
            total_blocked += summary.get("blocked", 0)
            
            probes = data.get("service_probes", {})
            for k, v in probes.items():
                global_probes[k] = v
                
            for res in data.get("results", []):
                if res.get("result", "") == "FAIL":
                    failed_tests.append(res)
        
        except Exception as e:
            print(f"Error processing {p}: {e}", file=sys.stderr)

    out_md = reports_dir / "full-report.md"
    
    with open(out_md, "w") as f:
        f.write("# Bridge Orchestration Test Report\n\n")
        f.write(f"**Generated:** {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n")
        
        f.write("## Overall Summary\n\n")
        f.write(f"- **Total Passes:** {total_pass} 🟢\n")
        f.write(f"- **Total Failures:** {total_fail} 🔴\n")
        f.write(f"- **Total Blocked:** {total_blocked} 🟡\n\n")

        f.write("## Tier Breakdown\n\n")
        f.write("| Tier | Pass | Fail | Blocked |\n")
        f.write("|------|------|------|---------|\n")
        for name, data in all_reports:
            summary = data.get("summary", {})
            p_cnt = summary.get("pass", 0)
            f_cnt = summary.get("fail", 0)
            b_cnt = summary.get("blocked", 0)
            f.write(f"| `{name}` | {p_cnt} | {f_cnt} | {b_cnt} |\n")
        f.write("\n")

        f.write("## Service Probes\n\n")
        f.write("| Service | Status |\n")
        f.write("|---------|--------|\n")
        for k, v in sorted(global_probes.items()):
            status_icon = "🟢 UP" if v else "🔴 DOWN"
            f.write(f"| `{k}` | {status_icon} |\n")
        f.write("\n")
        
        if failed_tests:
            f.write("## Failed Tests Details\n\n")
            for ft in failed_tests:
                test_id = ft.get("test_id", "Unknown")
                detail = ft.get("detail", "No details")
                row_raw = ft.get("row")
                f.write(f"### {test_id}\n")
                f.write(f"- **Detail:** {detail}\n")
                if "error" in ft:
                    f.write(f"- **Error:** `{ft['error']}`\n")
                f.write("\n")

    print(f"Merged {len(all_reports)} JSON reports into {out_md}")

if __name__ == '__main__':
    main()
