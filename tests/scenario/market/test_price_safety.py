"""MKT-STALE-PRICE — the engine has no freshness gate on the native pricing record.

A custodial market-maker that keeps trading on a DEAD price feed will happily be arbitraged to
zero: if the Zephyr oracle stops updating, the daemon's spot/MA keep reporting the last value and
the engine acts on it as if live. Code review found NO oracle/pricing-record freshness check in the
engine (only CEX/watcher market-data staleness and a disabled-by-default `staleDataThresholdMs`) —
so the engine cannot refuse stale native pricing.

This gap can't be exercised positively on devnet (the fake oracle holds its last price, so neither
daemon nor engine ever sees a "stale" signal to react to). The faithful red is therefore an
ABSENCE assertion: the engine's state/evaluate output must expose a freshness indicator for the
native price so a safety gate is *possible*. It exposes none → KNOWN-GAP(INV-14). The day a
freshness field appears (the fix), this flips to UNEXPECTED_PASS → promote the invariant.
"""
from __future__ import annotations

import pytest

from harness import engine

pytestmark = [pytest.mark.needs_stack, pytest.mark.inv("INV-14")]

# Field names that would indicate the engine tracks how fresh the native price is.
_FRESHNESS_KEYS = (
    "priceAge", "priceAgeBlocks", "priceAgeMs", "lastPriceUpdate", "lastPriceHeight",
    "priceTimestamp", "priceUpdatedAt", "stale", "isStale", "priceStale", "freshness",
    "reserveAge", "oracleAge", "reportAge", "pricingAge",
)


def _has_freshness_signal(node, depth: int = 0) -> bool:
    """Recursively look for any freshness/age/staleness key in a state blob."""
    if depth > 6:
        return False
    if isinstance(node, dict):
        for k, v in node.items():
            if any(fk.lower() == str(k).lower() for fk in _FRESHNESS_KEYS):
                return True
            if _has_freshness_signal(v, depth + 1):
                return True
    elif isinstance(node, list):
        return any(_has_freshness_signal(v, depth + 1) for v in node)
    return False


@pytest.mark.known_gap(
    inv="INV-14",
    reason="engine exposes no freshness/age signal on the native pricing record — it cannot "
    "detect or refuse a stale Zephyr oracle feed (no gate in code; CEX-only staleness handling).",
)
def test_mkt_engine_tracks_native_price_freshness():
    """The engine should surface how fresh the native price is so execution can gate on it.

    Assert a freshness signal exists in evaluate state and/or full state. None does today → red.
    """
    ev, err = engine.evaluate()
    assert not err and ev, f"evaluate errored: {err}"
    st, _ = engine.state()

    found = _has_freshness_signal((ev or {}).get("state")) or _has_freshness_signal(st or {})
    assert found, (
        "engine surfaces no native price-freshness signal (checked evaluate.state + /api/state) — "
        "no way to gate execution on a stale oracle"
    )
