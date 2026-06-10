#!/usr/bin/env python3
"""Dev pre-flight — environment readiness before `make dev-init` / `make dev-setup`.

Pure file/binary/daemon checks; no infrastructure, instant. Self-contained (stdlib only, its own
minimal .env loader) so it is independent of the test framework — `make dev-*` must keep working
regardless of how tests/ is structured. Exits non-zero on a hard failure (.env, repos, docker,
binaries); the dev-init snapshot is advisory only.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> dict[str, str]:
    """Parse .env into a dict, resolving ${VAR}/$VAR refs against os.environ + .env itself."""
    raw: dict[str, str] = {}
    envf = ROOT / ".env"
    if envf.exists():
        for line in envf.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                raw[k.strip()] = v.strip().strip("'\"")
    sub = re.compile(r"\$\{([^}]+)\}|\$([A-Za-z_]\w*)")
    env = dict(raw)
    for _ in range(5):
        changed = False
        for k, v in list(env.items()):
            nv = sub.sub(lambda m: os.environ.get(m.group(1) or m.group(2))
                         or env.get(m.group(1) or m.group(2), ""), v)
            if nv != v:
                env[k], changed = nv, True
        if not changed:
            break
    return env


GREEN, RED, YELLOW, NC = ("\033[32m", "\033[31m", "\033[33m", "\033[0m") if sys.stdout.isatty() else ("",) * 4


def line(ok: bool | None, tid: str, detail: str) -> None:
    mark = f"{GREEN}✓{NC}" if ok else (f"{YELLOW}•{NC}" if ok is None else f"{RED}✗{NC}")
    print(f"  {mark} {tid:<10} {detail}")


def main() -> int:
    env = load_env()
    failed = False

    # PREREQ-01: .env exists, no unresolved keygen placeholders.
    envf = ROOT / ".env"
    if not envf.exists():
        line(False, "PREREQ-01", ".env not found — run: make setup"); failed = True
    elif "<KEYGEN:" in envf.read_text():
        line(False, "PREREQ-01", ".env has unresolved <KEYGEN:> placeholders — run: make keygen"); failed = True
    else:
        line(True, "PREREQ-01", ".env exists, no placeholders")

    # PREREQ-02: required repos cloned.
    parts, repo_bad = [], False
    for name in ("ZEPHYR_REPO_PATH", "BRIDGE_REPO_PATH", "ENGINE_REPO_PATH"):
        path = os.environ.get(name) or env.get(name, "")
        if not path:
            parts.append(f"{name}: not set"); repo_bad = True
        elif not Path(path).is_dir():
            parts.append(f"{name}: missing ({path})"); repo_bad = True
        else:
            parts.append(f"{name.split('_')[0]}: OK")
    line(not repo_bad, "PREREQ-02", "; ".join(parts)); failed = failed or repo_bad

    # PREREQ-03: docker daemon.
    try:
        ok = subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode == 0
        line(ok, "PREREQ-03", "Docker daemon running" if ok else "Docker daemon not responding")
        failed = failed or not ok
    except FileNotFoundError:
        line(False, "PREREQ-03", "docker binary not found"); failed = True
    except subprocess.TimeoutExpired:
        line(False, "PREREQ-03", "docker info timed out"); failed = True

    # PREREQ-04: required binaries.
    missing = [b for b in ("cast", "forge", "node", "pnpm", "python3", "overmind") if not shutil.which(b)]
    if missing:
        line(False, "PREREQ-04", f"missing binaries: {', '.join(missing)}"); failed = True
    else:
        line(True, "PREREQ-04", "cast, forge, node, pnpm, python3, overmind found")

    # PREREQ-05: dev-init snapshot (advisory only — first init creates it).
    snap = ROOT / "snapshots" / "chain" / "node1-lmdb.tar.gz"
    if snap.exists():
        line(True, "PREREQ-05", f"dev-init snapshot present ({snap.stat().st_size / 1048576:.1f} MB)")
    else:
        line(None, "PREREQ-05", "no dev-init snapshot yet (created by make dev-init — not blocking)")

    if failed:
        print(f"{RED}precheck: environment not ready (fix the ✗ above){NC}")
        return 1
    print(f"{GREEN}precheck: environment ready{NC}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
