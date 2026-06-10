"""MKT-STALE-PRICE — the engine has no freshness gate on the NATIVE pricing record.

A custodial market-maker that keeps trading on a DEAD price feed will happily be arbitraged to
zero: if the Zephyr oracle stops updating, the daemon's spot/MA keep reporting the last value and
the engine acts on it as if live. Code review found NO oracle/pricing-record freshness check in the
engine — only EVM/CEX *watcher* liveness flags (`state.evm.watcher.stale`, `state.cex.watcher.stale`)
and a disabled-by-default `staleDataThresholdMs`. Those guard the watcher feeds, NOT the native
Zephyr price the reserve-ratio gates consume — so the engine cannot refuse a stale native feed.

This gap can't be exercised positively on devnet (the fake oracle holds its last price, so neither
daemon nor engine ever sees a "stale" signal to react to). The faithful red is therefore an
ABSENCE assertion scoped to the NATIVE pricing data the engine trades on — `evaluate.state`
(reserveRatio/zephPrice) and `state.zephyr` (reserve.rates, reserveRatio, policy). That subtree must
expose a freshness indicator for the native price so a safety gate is *possible*. It exposes none
(only watcher staleness elsewhere) → KNOWN-GAP(INV-14). The day a native-price freshness field
appears (the fix), this flips to UNEXPECTED_PASS → promote the invariant.

NOTE: an earlier version scanned the WHOLE state blob and false-passed on `evm/cex.watcher.stale`.
Watcher liveness ≠ native-oracle freshness; the scan is now scoped to the native subtree only.
"""
from __future__ import annotations

import pytest

from harness import engine

pytestmark = [pytest.mark.needs_stack, pytest.mark.inv("INV-14")]

# Field names that would indicate the engine tracks how fresh the NATIVE price is.
# Deliberately excludes a bare `stale`/`isStale` (those name the watcher feeds, not the oracle)
# and a bare `height`/`timestamp` snapshot stamp (present, but no age/gate is computed from it).
_FRESHNESS_KEYS = (
    "priceAge", "priceAgeBlocks", "priceAgeMs", "lastPriceUpdate", "lastPriceHeight",
    "priceTimestamp", "priceUpdatedAt", "priceStale", "isPriceStale", "freshness",
    "reserveAge", "oracleAge", "reportAge", "pricingAge", "priceFresh", "oracleStale",
)


def _has_freshness_signal(node, depth: int = 0) -> bool:
    """Recursively look for a native-price freshness/age key in a (native-scoped) state blob."""
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


def _native_nodes() -> list:
    """The native-pricing portions of engine state the reserve-ratio gates actually consume.

    `evaluate.state` = {reserveRatio, reserveRatioMa, zephPrice, rrMode}; `state.zephyr` =
    {height, reserve:{rates, reserveRatio, policy, ...}, feesBps, durations}. Explicitly NOT the
    evm/cex watcher subtrees (those carry the only `stale` flags, and they're not the oracle).
    """
    ev, err = engine.evaluate()
    assert not err and ev, f"evaluate errored: {err}"
    st, _ = engine.state()
    inner = (st or {}).get("state", st or {})  # /api/state wraps payload under .state
    return [(ev or {}).get("state"), (inner or {}).get("zephyr")]


def test_mkt_engine_tracks_native_price_freshness():
    """The engine surfaces how fresh the NATIVE price is so execution can gate on it (INV-14).

    Scoped to the native subtree (NOT the watcher flags). `state.zephyr` now carries
    `priceTimestamp`/`priceAgeSeconds`/`priceStale` derived from the pricing record's own timestamp
    (domain/zephyr/freshness.ts), and the arb auto-exec gate refuses a stale feed
    (checkPriceFreshness; proven deterministically in tests/domain/zephyr/freshness.spec.ts since the
    stale path can't be reached on devnet). Promoted from @known_gap. (Sanity: assert the native
    price is actually there, so a green means "freshness signal present", not "no price at all".)
    """
    natives = _native_nodes()
    es = natives[0] or {}
    assert es.get("zephPrice") is not None or es.get("reserveRatio") is not None, (
        "evaluate.state carries no native price — can't assess freshness coverage"
    )

    found = any(_has_freshness_signal(n) for n in natives)
    assert found, (
        "engine surfaces no NATIVE price-freshness signal (checked evaluate.state + state.zephyr) — "
        "no way to gate reserve-ratio conversions on a stale oracle. Watcher staleness "
        "(evm/cex.watcher.stale) is not the native price."
    )
