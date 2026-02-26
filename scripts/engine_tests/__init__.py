"""Engine Test Suite — comprehensive strategy, dispatch, and execution tests.

Self-contained test package. No markdown catalog dependency.
Tests self-register via TESTS dicts in each module.

Usage:
    python scripts/run-engine-tests.py                  # all tests
    python scripts/run-engine-tests.py --category arb   # arb only
    python scripts/run-engine-tests.py PRE-01 ARB-E05   # specific tests
    python scripts/run-engine-tests.py --list            # list all tests
"""
from __future__ import annotations


def collect_all_tests() -> dict[str, dict]:
    """Import all test modules and merge their TESTS dicts.

    Returns {test_id: {"fn": callable, "module": str, "category": str}}.
    """
    from . import (
        test_prerequisites,
        test_arb_detection,
        test_arb_gates,
        test_arb_planning,
        test_arb_combined,
        test_dispatch,
        test_cex,
        test_rebalancer,
        test_pegkeeper,
        test_lpmanager,
        test_engine,
        test_edge_cases,
        test_arb_execution,
    )

    modules = [
        ("PRE", "prerequisites", test_prerequisites),
        ("ARB", "arb_detection", test_arb_detection),
        ("ARB", "arb_gates", test_arb_gates),
        ("ARB", "arb_planning", test_arb_planning),
        ("ARB", "arb_combined", test_arb_combined),
        ("DISP", "dispatch", test_dispatch),
        ("CEX", "cex", test_cex),
        ("REB", "rebalancer", test_rebalancer),
        ("PEG", "pegkeeper", test_pegkeeper),
        ("LP", "lpmanager", test_lpmanager),
        ("ENG", "engine", test_engine),
        ("EDGE", "edge_cases", test_edge_cases),
        ("EXEC", "arb_execution", test_arb_execution),
    ]

    all_tests = {}
    for category, mod_name, mod in modules:
        for test_id, fn in getattr(mod, "TESTS", {}).items():
            all_tests[test_id] = {
                "fn": fn,
                "module": mod_name,
                "category": test_id.split("-")[0],
            }
    return all_tests


# Category -> required services for quick filtering
CATEGORY_SERVICES = {
    "PRE": ["engine", "anvil", "node1"],
    "ARB": ["engine", "anvil"],
    "DISP": ["engine"],
    "CEX": ["engine", "anvil"],
    "REB": ["engine"],
    "PEG": ["engine", "anvil"],
    "LP": ["engine", "anvil"],
    "ENG": ["engine", "anvil", "node1"],
    "RISK": ["engine"],
    "INV": ["engine"],
    "BRIDGE": ["engine", "node1"],
    "TIMING": ["engine"],
    "EDGE": ["engine", "anvil"],
    "EXEC": ["engine", "anvil", "node1"],
}
