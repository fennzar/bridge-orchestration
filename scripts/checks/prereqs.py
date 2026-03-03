"""Precheck tier (T1): environment readiness checks.

Pure file/binary checks — no infrastructure needed, instant.
Validates that everything is in place before dev-init or dev-setup.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from ._types import TestDef, _r
from test_common import ExecutionResult, FAIL, PASS

ROOT = Path(__file__).resolve().parent.parent.parent


def check_prereq_env(probes: dict[str, bool]) -> ExecutionResult:
    """PREREQ-01: .env exists with no <KEYGEN:> placeholders."""
    tid, lvl, lane = "PREREQ-01", "prereq", "precheck"

    env_file = ROOT / ".env"
    if not env_file.exists():
        return _r(tid, lvl, lane, FAIL, ".env not found — run: make setup")

    content = env_file.read_text()
    if "<KEYGEN:" in content:
        return _r(tid, lvl, lane, FAIL, ".env contains unresolved <KEYGEN:> placeholders — run: make keygen")

    return _r(tid, lvl, lane, PASS, ".env exists, no placeholders")


def check_prereq_repos(probes: dict[str, bool]) -> ExecutionResult:
    """PREREQ-02: Required repos cloned (ZEPHYR, BRIDGE, ENGINE)."""
    tid, lvl, lane = "PREREQ-02", "prereq", "precheck"
    parts = []
    failed = False

    repos = {
        "ZEPHYR_REPO_PATH": os.environ.get("ZEPHYR_REPO_PATH", ""),
        "BRIDGE_REPO_PATH": os.environ.get("BRIDGE_REPO_PATH", ""),
        "ENGINE_REPO_PATH": os.environ.get("ENGINE_REPO_PATH", ""),
    }

    for name, path in repos.items():
        if not path:
            parts.append(f"{name}: not set")
            failed = True
        elif not os.path.isdir(path):
            parts.append(f"{name}: directory not found")
            failed = True
        else:
            parts.append(f"{name}: OK")

    return _r(tid, lvl, lane, FAIL if failed else PASS, "; ".join(parts))


def check_prereq_docker(probes: dict[str, bool]) -> ExecutionResult:
    """PREREQ-03: Docker daemon running."""
    tid, lvl, lane = "PREREQ-03", "prereq", "precheck"

    import subprocess
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0:
            return _r(tid, lvl, lane, PASS, "Docker daemon running")
        return _r(tid, lvl, lane, FAIL, "Docker daemon not responding")
    except FileNotFoundError:
        return _r(tid, lvl, lane, FAIL, "docker binary not found")
    except subprocess.TimeoutExpired:
        return _r(tid, lvl, lane, FAIL, "Docker info timed out")


def check_prereq_binaries(probes: dict[str, bool]) -> ExecutionResult:
    """PREREQ-04: Required binaries available."""
    tid, lvl, lane = "PREREQ-04", "prereq", "precheck"

    required = ["cast", "forge", "node", "pnpm", "python3", "overmind"]
    missing = []
    found = []

    for binary in required:
        if shutil.which(binary):
            found.append(binary)
        else:
            missing.append(binary)

    if missing:
        return _r(tid, lvl, lane, FAIL, f"Missing binaries: {', '.join(missing)}")
    return _r(tid, lvl, lane, PASS, f"All {len(found)} binaries found: {', '.join(found)}")


def check_prereq_snapshot(probes: dict[str, bool]) -> ExecutionResult:
    """PREREQ-05: Dev-init snapshot exists (warns if not)."""
    tid, lvl, lane = "PREREQ-05", "prereq", "precheck"

    snapshot = ROOT / "snapshots" / "chain" / "node1-lmdb.tar.gz"
    if snapshot.exists():
        size_mb = snapshot.stat().st_size / (1024 * 1024)
        return _r(tid, lvl, lane, PASS, f"Dev-init snapshot exists ({size_mb:.1f} MB)")

    return _r(tid, lvl, lane, PASS, "Dev-init snapshot not found — run: make dev-init (not blocking)")


# ── Test Registry ────────────────────────────────────────────────────

TESTS: list[TestDef] = [
    TestDef("PREREQ-01", "Environment File", "prereq", "precheck", "precheck", check_prereq_env),
    TestDef("PREREQ-02", "Required Repos", "prereq", "precheck", "precheck", check_prereq_repos),
    TestDef("PREREQ-03", "Docker Daemon", "prereq", "precheck", "precheck", check_prereq_docker),
    TestDef("PREREQ-04", "Required Binaries", "prereq", "precheck", "precheck", check_prereq_binaries),
    TestDef("PREREQ-05", "Dev-Init Snapshot", "prereq", "precheck", "precheck", check_prereq_snapshot),
]
