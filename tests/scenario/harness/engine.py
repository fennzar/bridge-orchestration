"""Engine observation — read what the strategy engine decided for a given market state.

The engine is launch-critical and ships enabled, so its reactions to market moves are
money-critical. These wrap the read endpoints (evaluate/plans/analysis/state/runtime/history)
so scenarios can assert "engine saw market state X → produced/withheld decision Y".
See memory: Engine API Response Structures.
"""
from __future__ import annotations

import test_common as _tc

ENGINE = _tc.ENGINE_URL


def evaluate(strategies: str = "arb") -> tuple[dict | None, str | None]:
    """GET /api/engine/evaluate?strategies=… → {timestamp, state, results, errors}."""
    return _tc._jget(f"{ENGINE}/api/engine/evaluate?strategies={strategies}", timeout=20.0)


def state() -> tuple[dict | None, str | None]:
    """GET /api/state → full GlobalState {zephyr, evm, cex}."""
    return _tc._jget(f"{ENGINE}/api/state", timeout=15.0)


def analysis() -> tuple[dict | None, str | None]:
    """GET /api/arbitrage/analysis → {assets: [ArbMarketAnalysis]}."""
    return _tc._jget(f"{ENGINE}/api/arbitrage/analysis", timeout=15.0)


def plans() -> tuple[dict | None, str | None]:
    """GET /api/arbitrage/plans → {plans: [SerializedArbPlan]}."""
    return _tc._jget(f"{ENGINE}/api/arbitrage/plans", timeout=15.0)


def runtime(op: str = "auto", frm: str = "ZEPH.n", to: str = "WZEPH.e") -> tuple[dict | None, str | None]:
    """GET /api/runtime?op=…&from=…&to=… → {mode, reserveRatio, operations, blockedReasons}."""
    return _tc._jget(f"{ENGINE}/api/runtime?op={op}&from={frm}&to={to}", timeout=15.0)


def history(strategy: str = "arb", mode: str = "paper", limit: int = 50) -> tuple[dict | None, str | None]:
    """GET /api/engine/history → {executions, count, stats24h}."""
    return _tc._jget(
        f"{ENGINE}/api/engine/history?strategy={strategy}&mode={mode}&limit={limit}", timeout=15.0
    )


def status() -> tuple[dict | None, str | None]:
    """GET /api/engine/status → {database, state} (does not depend on daemon pricing)."""
    return _tc._jget(f"{ENGINE}/api/engine/status", timeout=10.0)


# ── small extractors so scenarios read declaratively ─────────────────────────
def rr_mode(evaluation: dict) -> str | None:
    return (evaluation or {}).get("state", {}).get("rrMode")


def reserve_ratio(evaluation: dict) -> float | None:
    rr = (evaluation or {}).get("state", {}).get("reserveRatio")
    try:
        return float(rr) if rr is not None else None
    except (TypeError, ValueError):
        return None


def opportunities(evaluation: dict, strategy: str = "arb") -> list[dict]:
    return (evaluation or {}).get("results", {}).get(strategy, {}).get("opportunities", [])


def auto_executable_plans(plans_resp: dict) -> list[dict]:
    """Plans the engine would auto-execute (not merely propose)."""
    out = []
    for p in (plans_resp or {}).get("plans", []):
        summary = p.get("summary", {})
        if summary.get("shouldAutoExecute") or p.get("autoExecute"):
            out.append(p)
    return out
