"""Direct bridge-Postgres access for resilience scenarios that must INJECT a state the public/admin
API cannot produce — e.g. an unwrap marked `failed` whose pre-signed payout actually landed on-chain
(the INV-4 double-pay setup: a crash between broadcast and the confirmation write).

Runs `psql` inside the bridge Postgres container via `docker exec` (trust auth inside the container
— no password). The bridge DB is `zephyrbridge_dev`, table `"Unwrap"` (see the
zephyr-bridge schema.prisma). Container/db/user are overridable via env for non-default stacks.
"""
from __future__ import annotations

import os
import subprocess

PG_CONTAINER = os.environ.get("ORCH_POSTGRES_CONTAINER", "orch-postgres")
PG_USER = os.environ.get("POSTGRES_USER", "zephyr")
BRIDGE_DB = os.environ.get("BRIDGE_DB_NAME", "zephyrbridge_dev")


def psql(sql: str, timeout: float = 15.0) -> tuple[str | None, str | None]:
    """Run one SQL statement (tuples-only, unaligned). Returns (stdout_stripped, err)."""
    try:
        proc = subprocess.run(
            ["docker", "exec", PG_CONTAINER, "psql", "-U", PG_USER, "-d", BRIDGE_DB, "-tAc", sql],
            capture_output=True, text=True, timeout=timeout,
        )
    except Exception as e:  # docker missing, container down, timeout
        return None, str(e)
    if proc.returncode != 0:
        return None, (proc.stderr or "").strip() or f"psql exit {proc.returncode}"
    return proc.stdout.strip(), None


def _esc(value: str) -> str:
    return value.replace("'", "''")


def unwrap_get(unwrap_id: str, columns: list[str]) -> dict[str, str | None]:
    """Read selected `"Unwrap"` columns for a record. Empty cells come back as None.

    `columns` are trusted test-supplied identifiers (quoted as-is); `unwrap_id` is escaped.
    """
    # Join all columns into ONE tab-separated cell via concat_ws so the parse does not depend on
    # psql's column separator (`-tA` defaults to `|`, which silently broke multi-column reads). Each
    # column is COALESCE'd to the `\N` sentinel first, so a NULL is a real arg (concat_ws drops NULL
    # args, which would misalign) and round-trips back to None below.
    fields = ", ".join(f'COALESCE("{c}"::text, \'\\N\')' for c in columns)
    out, err = psql(f'''SELECT concat_ws(E'\\t', {fields}) FROM "Unwrap" WHERE id = '{_esc(unwrap_id)}';''')
    if err or out is None or out == "":
        return {c: None for c in columns}
    cells = out.split("\t")
    return {c: (None if (i >= len(cells) or cells[i] == "\\N") else cells[i]) for i, c in enumerate(columns)}
