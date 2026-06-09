"""Scenario test harness — thin wrappers over the kept stdlib control plane.

The chain/market control plane lives in ../../scripts (test_common.py, lib/seed_helpers.py)
and is NOT rewritten. These modules import and re-expose it with intention-revealing names
plus the few helpers harvested from the retired l5_checks (pool-push). Import surface:

    from harness import chain, control, pool, bridge, engine

conftest.py puts ../../scripts and ../../scripts/lib on sys.path before these import.
"""
