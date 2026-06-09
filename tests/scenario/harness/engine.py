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
    """GET /api/runtime?op=…&from=…&to=… (apps/web/app/api/runtime/route.ts).

    200 → {timestamp, selection:{requested, resolved}, runtime:{operation, enabled:bool|null, context}}.
    `enabled` is the live gate verdict: for native mint/redeem it IS `reserve.policy.<asset>.<m|r>`
    (runtime.zephyr.ts), so this is how a scenario reads the engine's protocol-gate decision.
    Bad params → 400 (from/to invalid), 404 (no op for pair), 501 (op unregistered), 500 (threw);
    those bodies carry {selection, error} and _jget surfaces the HTTP error string."""
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


def runtime_enabled(runtime_resp: dict) -> bool | None:
    """The engine's live gate verdict for the requested op (None if it couldn't decide)."""
    return (runtime_resp or {}).get("runtime", {}).get("enabled")


def runtime_operation(runtime_resp: dict) -> str | None:
    """The op the engine resolved the from/to pair to (e.g. 'nativeMint')."""
    return (runtime_resp or {}).get("runtime", {}).get("operation")


def plan_conversions(plan: dict) -> list[tuple[str, str]]:
    """Every (fromAsset, toAsset) hop a serialized arb plan would execute.

    The plan JSON is opaque (`SerializedArbPlan = {[key]: JsonValue}`, report.ts) — its execution
    variants live under `view.clipOptions[].option.{open,close}.execution` and carry `fromAsset` /
    `toAsset` (view.ts). Rather than couple to that exact nesting (which drifts), walk the whole
    object and collect any node that names a from/to pair. Deduped, order-preserving.
    """
    seen: list[tuple[str, str]] = []

    def visit(node):
        if isinstance(node, dict):
            frm = node.get("fromAsset") or node.get("from")
            to = node.get("toAsset") or node.get("to")
            if isinstance(frm, str) and isinstance(to, str) and frm != to:
                pair = (frm, to)
                if pair not in seen:
                    seen.append(pair)
            for v in node.values():
                visit(v)
        elif isinstance(node, list):
            for v in node:
                visit(v)

    visit(plan)
    return seen


def native_conversions(plan: dict) -> list[tuple[str, str]]:
    """Just the native (`.n`→`.n`) hops — the ones the daemon's reserve-ratio gates apply to.
    EVM swaps / wraps are not RR-gated, so they're irrelevant to doomed-conversion checks."""
    return [(f, t) for (f, t) in plan_conversions(plan) if f.endswith(".n") and t.endswith(".n")]
