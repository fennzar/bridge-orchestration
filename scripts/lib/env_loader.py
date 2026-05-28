"""Shared .env loader for orchestration Python scripts.

Replaces three near-identical `load_env()` copies in
patch-pool-prices.py, seed-liquidity.py, and sanity-check-post-setup-state.py.

Stdlib-only. Uses `os.environ.setdefault` so already-exported shell vars win.
Variable references (${VAR}, $VAR) are expanded against the live environment.
"""
from __future__ import annotations

import os
from pathlib import Path


def load_env(env_file: Path, *, required: bool = False) -> bool:
    """Load key=value pairs from `env_file` into os.environ.

    Args:
        env_file: Path to .env file.
        required: If True, raises FileNotFoundError when the file is missing.
                  If False (default), silently returns False on missing file.

    Returns:
        True if a file was loaded, False if missing (and not required).

    Notes:
        - Comments and blank lines are skipped.
        - Existing environment values are preserved (setdefault semantics).
        - Variable references in values are expanded via os.path.expandvars.
    """
    if not env_file.exists():
        if required:
            raise FileNotFoundError(f".env not found at {env_file}")
        return False

    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key:
            os.environ.setdefault(key, os.path.expandvars(value))
    return True
