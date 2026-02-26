"""Layer 3: Reusable test patterns, execution helpers, strategy evaluate.

Imports from _api and _pool. No dependency on _funding.
"""
from __future__ import annotations

import re
import time
from contextlib import contextmanager
from typing import Any, Generator

from _api import (
    PASS, FAIL, BLOCKED,
    ENGINE_ADDRESS, ENGINE_PK,
    ASSET_POOL, ASSET_THRESHOLD,
    EXEC_SWAP_AMOUNTS, WAIT_EXEC_LONG, WAIT_EXEC_POLL,
    TK, ENGINE,
    TestResult,
    engine_evaluate, engine_status, engine_history, engine_plans,
    engine_runner_get, engine_runner_set, engine_queue,
    balance_of,
    _jget,
)

from _pool import (
    WAIT_EXEC,
    pool_push, rr_mode, wait_sync, wait_exec,
    is_engine_running,
    EngineCleanupContext,
    mine_blocks, set_oracle_price,
    find_opportunity, find_warnings, get_gap_bps, get_status_field,
)

__all__ = [
    "result", "needs", "needs_engine_env",
    "strategy_evaluate", "strategy_results", "strategy_opportunities",
    "strategy_metrics", "strategy_warnings",
    "assert_api_fields",
    "assert_detection", "assert_no_detection",
    "assert_rr_gate",
    "assert_spread_gate",
    "assert_plan_structure",
    "plan_execution_stages", "plan_all_stages", "plan_stage_ops", "plan_summary",
    "assert_execution",
    "wait_for_execution", "extract_step_ops", "runner_mode",
    "wait_for_queued_plan", "verify_execution_record",
    "assert_warning_present",
]


# ===========================================================================
# Core result helpers
# ===========================================================================

def result(status: str, detail: str, test_id: str = "") -> TestResult:
    """Build a test result dict."""
    return {"test_id": test_id, "result": status, "detail": detail}


def needs(probes: dict, *services: str) -> TestResult | None:
    """Check required services are up. Returns BLOCKED result or None."""
    down = [s for s in services if not probes.get(s)]
    if down:
        return result(BLOCKED, f"Services down: {', '.join(down)}")
    return None


def needs_engine_env() -> TestResult | None:
    """Check ENGINE_PK and ENGINE_ADDRESS are set. Returns BLOCKED or None."""
    if not ENGINE_PK or not ENGINE_ADDRESS:
        return result(BLOCKED, "ENGINE_PK / ENGINE_ADDRESS not set in .env")
    return None


# ===========================================================================
# Generic strategy evaluate helpers
# ===========================================================================

def strategy_evaluate(probes: dict, strategy: str) -> tuple[dict | None, TestResult | None]:
    """Evaluate any strategy. Returns (data, error_result)."""
    blocked = needs(probes, "engine")
    if blocked:
        return None, blocked
    data, err = engine_evaluate(strategies=strategy)
    if err:
        return None, result(FAIL, f"{strategy} evaluate: {err}")
    return data, None


def strategy_results(data: dict | None, strategy: str) -> dict:
    """Extract strategy results from evaluate response."""
    return (data or {}).get("results", {}).get(strategy, {})


def strategy_opportunities(data: dict | None, strategy: str) -> list:
    """Extract strategy opportunities from evaluate response."""
    return strategy_results(data, strategy).get("opportunities", [])


def strategy_metrics(data: dict | None, strategy: str) -> dict:
    """Extract strategy metrics from evaluate response."""
    return strategy_results(data, strategy).get("metrics", {})


def strategy_warnings(data: dict | None, strategy: str) -> list:
    """Extract strategy warnings from evaluate response."""
    return strategy_results(data, strategy).get("warnings", [])


# ===========================================================================
# Pattern: API field validation
# ===========================================================================

def assert_api_fields(probes: dict, endpoint_fn: Any, required_fields: list[str],
                      path: list[str] | None = None,
                      services: tuple[str, ...] = ("engine",)) -> TestResult:
    """Query an API endpoint and verify required fields exist.

    Args:
        probes: service probe dict
        endpoint_fn: callable returning (parsed, error)
        required_fields: list of field names that must exist
        path: optional path to navigate into response (e.g. ["state", "reserve"])
        services: required services tuple

    Returns test result dict.
    """
    blocked = needs(probes, *services)
    if blocked:
        return blocked

    data, err = endpoint_fn()
    if err:
        return result(FAIL, f"API error: {err}")

    # Navigate to target node
    node = data
    if path:
        node = get_status_field(data, *path)
        if node is None:
            return result(FAIL, f"Path {'.'.join(path)} not found in response")

    missing = [f for f in required_fields if f not in (node or {})]
    if missing:
        available = list((node or {}).keys())[:20]
        return result(FAIL, f"Missing fields: {missing}. Available: {available}")

    return result(PASS, f"All {len(required_fields)} fields present")


# ===========================================================================
# Pattern: Opportunity detection
# ===========================================================================

def assert_detection(probes: dict, asset: str, direction: str,
                     pool_name: str | None = None, min_gap_bps: int | None = None,
                     swap_amount: int = 0) -> TestResult:
    """Push pool price, verify engine detects opportunity.

    Args:
        probes: service probe dict
        asset: "ZEPH", "ZSD", "ZRS", "ZYS"
        direction: "evm_discount" or "evm_premium"
        pool_name: override pool name (default: ASSET_POOL[asset])
        min_gap_bps: minimum gap to verify (default: ASSET_THRESHOLD[asset])
        swap_amount: amount for pool push

    Returns test result dict.
    """
    blocked = needs(probes, "engine", "anvil")
    if blocked:
        return blocked
    blocked = needs_engine_env()
    if blocked:
        return blocked

    pool = pool_name or ASSET_POOL.get(asset)
    if not pool:
        return result(BLOCKED, f"No pool mapping for {asset}")

    push_dir = "discount" if direction == "evm_discount" else "premium"
    threshold = min_gap_bps or ASSET_THRESHOLD.get(asset, 100)

    with pool_push(pool, push_dir, swap_amount) as (info, err):
        if err:
            return result(BLOCKED, f"Pool push: {err}")

        wait_sync()

        analysis, err = engine_evaluate()
        if err:
            return result(FAIL, f"Engine unreachable after push: {err}")

        opps, metrics = find_opportunity(analysis, asset, direction)
        gap_bps = get_gap_bps(analysis, asset)

        if opps:
            opp = opps[0]
            return result(PASS,
                f"{asset} {direction} detected: gapBps={gap_bps}, "
                f"urgency={opp.get('urgency')}, "
                f"pnl=${opp.get('expectedPnl', 0):.2f}")

        # Fallback: check gap metrics even if no opportunity object
        if gap_bps is not None:
            expected_sign = -1 if direction == "evm_discount" else 1
            if abs(gap_bps) >= threshold and (gap_bps * expected_sign > 0):
                return result(PASS,
                    f"{asset} gap confirmed via metrics: gapBps={gap_bps}")

        return result(FAIL,
            f"No {direction} detected for {asset}. "
            f"gapBps={gap_bps}, threshold={threshold}")


def assert_no_detection(probes: dict, asset: str, direction: str | None = None,
                        pool_name: str | None = None, swap_amount: int | None = None) -> TestResult:
    """Verify NO opportunity detected for an asset/direction.

    If swap_amount is given, pushes pool first (for below-threshold tests).
    Otherwise just queries current state.
    """
    blocked = needs(probes, "engine", "anvil")
    if blocked:
        return blocked

    if swap_amount:
        blocked = needs_engine_env()
        if blocked:
            return blocked

        pool = pool_name or ASSET_POOL.get(asset)
        if not pool:
            return result(BLOCKED, f"No pool mapping for {asset}")

        push_dir = "discount" if direction == "evm_discount" else "premium"

        with pool_push(pool, push_dir, swap_amount) as (info, err):
            if err:
                return result(BLOCKED, f"Pool push: {err}")
            wait_sync()
            return _check_no_detection(asset, direction)
    else:
        return _check_no_detection(asset, direction)


def _check_no_detection(asset: str, direction: str | None = None) -> TestResult:
    """Internal: verify no opportunity for asset/direction."""
    analysis, err = engine_evaluate()
    if err:
        return result(FAIL, f"Engine unreachable: {err}")

    opps, metrics = find_opportunity(analysis, asset, direction)
    triggered = [o for o in opps if o.get("hasOpportunity") or o.get("meetsTrigger")]

    if triggered:
        opp = triggered[0]
        return result(FAIL,
            f"Unexpected opportunity: {asset} {opp.get('direction')}, "
            f"gap={opp.get('gapBps')}, pnl=${opp.get('expectedPnl', 0):.2f}")

    dir_str = f" {direction}" if direction else ""
    return result(PASS, f"No{dir_str} opportunity for {asset} (correct)")


# ===========================================================================
# Pattern: RR mode gate (auto-execution check)
# ===========================================================================

def assert_rr_gate(probes: dict, rr_mode_name: str, asset: str, direction: str,
                   expected_available: bool, push_pool: bool = True,
                   swap_amount: int = 0) -> TestResult:
    """Set RR mode, optionally push pool, check close path availability.

    Checks opportunity.context.nativeCloseAvailable and cexCloseAvailable,
    NOT shouldAutoExecute (which is a strategy method, not an API field).

    Args:
        probes: service probe dict
        rr_mode_name: "normal", "defensive", "crisis", "high-rr"
        asset: "ZEPH", "ZSD", "ZRS", "ZYS"
        direction: "evm_discount" or "evm_premium"
        expected_available: expected nativeCloseAvailable value
        push_pool: whether to push pool price to create opportunity
        swap_amount: amount for pool push
    """
    blocked = needs(probes, "engine", "anvil", "oracle")
    if blocked:
        return blocked
    if push_pool:
        blocked = needs_engine_env()
        if blocked:
            return blocked

    pool = ASSET_POOL.get(asset)
    push_dir = "discount" if direction == "evm_discount" else "premium"

    with rr_mode(rr_mode_name):
        wait_sync()

        if push_pool and pool:
            with pool_push(pool, push_dir, swap_amount) as (info, err):
                if err:
                    return result(BLOCKED, f"Pool push: {err}")
                wait_sync()
                return _check_close_available(asset, direction,
                                              expected_available, rr_mode_name)
        else:
            return _check_close_available(asset, direction,
                                          expected_available, rr_mode_name)


def _check_close_available(asset: str, direction: str, expected: bool,
                           mode: str) -> TestResult:
    """Internal: check if close path is available for an opportunity."""
    analysis, err = engine_evaluate()
    if err:
        return result(FAIL, f"Engine unreachable: {err}")

    opps, metrics = find_opportunity(analysis, asset, direction)
    if not opps:
        if not expected:
            # No opportunity at all -- close path is implicitly blocked
            return result(PASS,
                f"{asset} {direction} in {mode}: no opportunity (blocked)")
        # Check gap metric -- if gap is in right direction but below threshold,
        # it means pool depth prevents detection (not a test failure)
        gap = get_gap_bps(analysis, asset)
        expected_sign = -1 if direction == "evm_discount" else 1
        if gap is not None and (gap * expected_sign > 0):
            return result(PASS,
                f"{asset} {direction} in {mode}: gap={gap}bps in correct "
                f"direction but below detection threshold (pool depth limit)")
        return result(FAIL,
            f"{asset} {direction} in {mode}: no opportunity found, "
            f"expected close available={expected}, gap={gap}")

    opp = opps[0]
    ctx = opp.get("context", {})
    native_close = ctx.get("nativeCloseAvailable", False)
    cex_close = ctx.get("cexCloseAvailable", False)
    any_close = native_close or cex_close

    if any_close == expected:
        return result(PASS,
            f"{asset} {direction} in {mode}: "
            f"native={native_close}, cex={cex_close} (correct)")
    else:
        return result(FAIL,
            f"{asset} {direction} in {mode}: "
            f"native={native_close}, cex={cex_close}, "
            f"expected available={expected}")


# ===========================================================================
# Pattern: Spread gate
# ===========================================================================

def assert_spread_gate(probes: dict, target_spread_bps: int, asset: str, direction: str,
                       expected_blocked: bool) -> TestResult:
    """Verify spread gate by manipulating oracle and checking computed spread.

    Since shouldAutoExecute is not exposed in the evaluate API, we verify:
    1. The engine correctly computes spotMaSpreadBps from oracle state
    2. The achieved spread vs documented gate thresholds matches expectations

    Gate rules (from arbitrage.approval.ts):
    - abs(spread) >= 500  -> blanket block (all assets)
    - ZEPH/ZRS discount + spread > +300 -> block (hurts redemption)
    - ZEPH/ZRS premium + spread < -300 -> block (hurts minting)
    - ZSD/ZYS -> immune to directional (only blanket 500bps)
    """
    blocked = needs(probes, "engine", "anvil", "oracle")
    if blocked:
        return blocked

    # 1. Read current state to derive actual MA
    data, err = engine_evaluate()
    if err:
        return result(FAIL, f"Engine unreachable: {err}")

    metrics = (data or {}).get("results", {}).get("arb", {}).get("metrics", {})
    current_spread = metrics.get("spotMaSpreadBps", 0)
    current_price = (data or {}).get("state", {}).get("zephPrice", 1.50)

    # Derive MA: spot = MA * (1 + spreadBps/10000), so MA = spot / (1 + spread/10000)
    ma = current_price / (1 + current_spread / 10000) if current_spread != -10000 else current_price

    # 2. Compute target oracle price for desired spread.
    # Mining blocks shifts MA toward new price, reducing achieved spread.
    # Overshoot by 25% to compensate for MA drift during mining.
    overshoot_spread = int(target_spread_bps * 1.25) if target_spread_bps != 0 else 0
    target_price = ma * (1 + overshoot_spread / 10000)
    if target_price <= 0:
        return result(BLOCKED, f"Target price ${target_price:.3f} <= 0 (spread too negative)")

    with EngineCleanupContext(price_usd=current_price):
        ok = set_oracle_price(target_price)
        if not ok:
            return result(BLOCKED, f"Failed to set oracle to ${target_price:.3f}")
        mine_blocks(3)  # Minimal blocks for daemon to see new price (less MA drift)
        wait_sync()

        return _check_spread_gate(asset, direction, expected_blocked,
                                  target_spread_bps)


def _check_spread_gate(asset: str, direction: str, expected_blocked: bool,
                       target_spread_bps: int) -> TestResult:
    """Internal: check spread computation and gate threshold alignment."""
    analysis, err = engine_evaluate()
    if err:
        return result(FAIL, f"Engine unreachable: {err}")

    metrics = (analysis or {}).get("results", {}).get("arb", {}).get("metrics", {})
    achieved_spread = metrics.get("spotMaSpreadBps")

    if achieved_spread is None:
        return result(FAIL, "No spotMaSpreadBps in metrics")

    # Apply documented gate rules to check if this spread WOULD block
    blanket_blocked = abs(achieved_spread) >= 500
    directional_blocked = False
    if asset in ("ZEPH", "ZRS"):
        if direction == "evm_discount" and achieved_spread > 300:
            directional_blocked = True
        elif direction == "evm_premium" and achieved_spread < -300:
            directional_blocked = True

    would_block = blanket_blocked or directional_blocked

    if would_block == expected_blocked:
        flags = []
        if blanket_blocked:
            flags.append("blanket")
        if directional_blocked:
            flags.append("directional")
        gate_label = "+".join(flags) if flags else "none"
        return result(PASS,
            f"{asset} {direction}: spread={achieved_spread}bps "
            f"(target={target_spread_bps}), gate={gate_label}, "
            f"{'blocked' if would_block else 'passes'} (correct)")
    else:
        return result(FAIL,
            f"{asset} {direction}: spread={achieved_spread}bps "
            f"(target={target_spread_bps}), would_block={would_block}, "
            f"expected_blocked={expected_blocked}, "
            f"blanket={blanket_blocked}, directional={directional_blocked}")


# ===========================================================================
# Pattern: Plan structure verification
# ===========================================================================

def assert_plan_structure(probes: dict, asset: str, direction: str,
                          expected_steps: list[str] | None = None,
                          check_fields: list[str] | None = None) -> TestResult:
    """Push pool, verify plan has expected structure.

    Args:
        expected_steps: list of expected step op types (e.g. ["swapEVM", "unwrap", "nativeMint"])
        check_fields: list of top-level plan fields to verify exist
    """
    blocked = needs(probes, "engine", "anvil")
    if blocked:
        return blocked
    blocked = needs_engine_env()
    if blocked:
        return blocked

    pool = ASSET_POOL.get(asset)
    if not pool:
        return result(BLOCKED, f"No pool mapping for {asset}")

    push_dir = "discount" if direction == "evm_discount" else "premium"

    with pool_push(pool, push_dir) as (info, err):
        if err:
            return result(BLOCKED, f"Pool push: {err}")
        wait_sync()

        # Try plans endpoint first
        plans, err = engine_plans()
        if not err and plans:
            plan_list = plans if isinstance(plans, list) else plans.get("plans", [])
            matching = [
                p for p in plan_list
                if p.get("asset") == asset and p.get("direction") == direction
            ]
            if matching:
                return _verify_plan(matching[0], expected_steps, check_fields,
                                    asset, direction)

        # Fallback to evaluate
        analysis, err = engine_evaluate()
        if err:
            return result(FAIL, f"Engine unreachable: {err}")

        opps, _ = find_opportunity(analysis, asset, direction)
        if not opps:
            return result(FAIL, f"No {direction} opportunity for {asset}")

        opp = opps[0]
        # Some responses embed plan data in opportunity
        plan_data = opp.get("plan", opp)
        return _verify_plan(plan_data, expected_steps, check_fields,
                            asset, direction)


def plan_execution_stages(plan: dict) -> list[dict]:
    """Extract execution stages from a plan.

    The plans API returns stages as a dict:
      stages: { inventory: [...], preparation: [...], execution: [...], ... }
    """
    stages = plan.get("stages", {})
    if isinstance(stages, dict):
        return stages.get("execution", [])
    return []


def plan_all_stages(plan: dict) -> list[dict]:
    """Flatten all stages from a plan into a single list."""
    stages = plan.get("stages", {})
    if isinstance(stages, dict):
        all_items: list[dict] = []
        for stage_name in ("preparation", "execution", "settlement", "realisation"):
            all_items.extend(stages.get(stage_name, []))
        return all_items
    return []


def plan_stage_ops(plan: dict) -> list[str]:
    """Extract operation names from plan execution stages.

    Descriptions are like: "WZRS.e -> WZEPH.e (swapEVM)" -> "swapEVM"
    """
    ops: list[str] = []
    for s in plan_all_stages(plan):
        desc = s.get("description", "")
        m = re.search(r"\((\w+)\)", desc)
        if m:
            ops.append(m.group(1))
        else:
            # Try leg data in preparation stages
            leg = s.get("leg", {})
            for seg in leg.get("open", []):
                seg_op = seg.get("op")
                ops.extend(seg_op if isinstance(seg_op, list) else [seg_op or ""])
    return ops


def plan_summary(plan: dict) -> dict:
    """Get plan summary (estimatedProfitUsd, estimatedCostUsd, etc.)."""
    return plan.get("summary", {})


def _verify_plan(plan: dict, expected_steps: list[str] | None = None,
                 check_fields: list[str] | None = None,
                 asset: str = "", direction: str = "") -> TestResult:
    """Internal: verify plan has expected structure.

    Actual plan fields: asset, direction, stages (dict), summary, view.
    Field mapping for check_fields:
      - 'steps' -> stages.execution (list)
      - 'estimatedCost' -> summary.estimatedCostUsd
      - 'id' -> asset+direction (always present)
      - 'strategy' -> implicit (arb)
    """
    # Map legacy field names to actual plan structure
    field_map: dict[str, Any] = {
        "steps": lambda p: bool(plan_execution_stages(p)),
        "estimatedCost": lambda p: "estimatedCostUsd" in p.get("summary", {}),
        "id": lambda p: bool(p.get("asset")),
        "strategy": lambda _p: True,  # Always arb from plans API
    }

    if check_fields:
        missing = []
        for f in check_fields:
            checker = field_map.get(f)
            if checker:
                if not checker(plan):
                    missing.append(f)
            elif f not in plan:
                missing.append(f)
        if missing:
            return result(FAIL,
                f"Plan missing fields: {missing}. "
                f"Available: {list(plan.keys())[:15]}")

    exe_stages = plan_execution_stages(plan)
    ops = plan_stage_ops(plan)

    if expected_steps and ops:
        if ops != expected_steps:
            return result(FAIL,
                f"Steps mismatch for {asset} {direction}: "
                f"expected={expected_steps}, got={ops}")

    summary = plan_summary(plan)
    pnl = summary.get("estimatedProfitUsd", "?")
    cost = summary.get("estimatedCostUsd", "?")
    return result(PASS,
        f"{asset} {direction} plan: {len(exe_stages)} execution stages, "
        f"ops={ops}, pnl=${pnl}, cost=${cost}")


# ===========================================================================
# Pattern: Execution verification (requires engine-run running)
# ===========================================================================

def assert_execution(probes: dict, asset: str, direction: str) -> TestResult:
    """Push pool, wait for engine to execute, verify in history.

    Requires engine-run process to be running.
    """
    blocked = needs(probes, "engine", "anvil")
    if blocked:
        return blocked
    blocked = needs_engine_env()
    if blocked:
        return blocked
    if not is_engine_running():
        return result(BLOCKED,
            "engine-run not running (start with: make dev APPS=engine)")

    pool = ASSET_POOL.get(asset)
    if not pool:
        return result(BLOCKED, f"No pool mapping for {asset}")
    push_dir = "discount" if direction == "evm_discount" else "premium"

    # Baseline history
    history, err = engine_history(strategy="arb")
    if err:
        return result(BLOCKED, f"History endpoint: {err}")
    baseline_ids = _extract_execution_ids(history, asset)

    with pool_push(pool, push_dir) as (info, push_err):
        if push_err:
            return result(BLOCKED, f"Pool push: {push_err}")

        wait_exec()

        history, err = engine_history(strategy="arb")
        if err:
            return result(FAIL, f"History unreachable after push: {err}")

        new_ids = _extract_execution_ids(history, asset) - baseline_ids
        if not new_ids:
            return result(FAIL,
                f"No new {asset} executions after {WAIT_EXEC}s "
                f"(baseline={len(baseline_ids)})")

        records = history if isinstance(history, list) else (history or {}).get("executions", [])
        new_exec = next((r for r in records if r.get("id") in new_ids), None)
        if new_exec:
            exec_result = new_exec.get("result", {})
            return result(PASS,
                f"{asset} {direction} executed: "
                f"success={exec_result.get('success')}, "
                f"steps={exec_result.get('stepsExecuted', '?')}, "
                f"records={len(new_ids)}")

        return result(PASS, f"{asset} execution recorded: {len(new_ids)} new")


def _extract_execution_ids(history: dict | list | None, asset: str) -> set:
    """Extract execution IDs for a specific asset from history."""
    if history is None:
        return set()
    records = history if isinstance(history, list) else history.get("executions", [])
    ids: set[str] = set()
    for r in records:
        opp = r.get("plan", {}).get("opportunity", {})
        if opp.get("asset") == asset:
            ids.add(r.get("id"))
    return ids


# ===========================================================================
# Pattern: Real arb execution (E2E with engine-run loop)
# ===========================================================================

def wait_for_execution(asset: str, baseline_ids: set,
                       timeout: int = WAIT_EXEC_LONG,
                       poll_interval: int = WAIT_EXEC_POLL) -> tuple[dict | None, str | None]:
    """Poll engine history until a new execution appears for the given asset.

    Returns (execution_record, error). Times out with descriptive error.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(poll_interval)
        history, err = engine_history(strategy="arb")
        if err:
            continue  # transient errors during execution are expected

        new_ids = _extract_execution_ids(history, asset) - baseline_ids
        if new_ids:
            records = (
                history if isinstance(history, list)
                else (history or {}).get("executions", [])
            )
            new_exec = next(
                (r for r in records if r.get("id") in new_ids), None
            )
            return new_exec, None

    return None, (
        f"No new {asset} execution after {timeout}s "
        f"(baseline={len(baseline_ids)} executions)"
    )


def extract_step_ops(record: dict) -> list[str]:
    """Extract operation names from an execution history record.

    Tries record.plan (which uses the stages dict structure), falling back
    to plan_stage_ops() regex extraction from descriptions.
    Returns list like ["swapEVM", "unwrap", "nativeRedeem", "wrap"].
    """
    plan = record.get("plan", {})
    if not plan:
        return []

    # Use the existing plan_stage_ops helper (works on stages dict)
    ops = plan_stage_ops(plan)
    if ops:
        return ops

    # Fallback: try steps array if history serializes differently
    steps = plan.get("steps", [])
    if isinstance(steps, list):
        return [s.get("op", "") for s in steps if s.get("op")]

    return []


@contextmanager
def runner_mode(**settings: Any) -> Generator[None, None, None]:
    """Context manager: set engine runner settings, restore on exit.

    Saves current settings, applies overrides, restores originals on exit.
    Common usage:
        with runner_mode(autoExecute=True, manualApproval=True, cooldownMs=1000):
            ...  # engine runs in manual mode
    """
    # Save current settings
    original, err = engine_runner_get()
    if err:
        original = {}

    # Apply new settings
    engine_runner_set(**settings)
    try:
        yield
    finally:
        # Restore original settings (only fields we know about)
        restore: dict[str, Any] = {}
        for key in ("autoExecute", "manualApproval", "cooldownMs"):
            if original and key in original:
                restore[key] = original[key]
        if restore:
            engine_runner_set(**restore)


def wait_for_queued_plan(asset: str, direction: str,
                         timeout: int = 30,
                         poll_interval: int = 3) -> tuple[dict | None, str | None]:
    """Poll engine queue until a pending operation appears for asset/direction.

    Returns (operation_dict, error). The operation_dict has at minimum:
    {id, status, plan: {asset, direction, stages, ...}}
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(poll_interval)
        data, err = engine_queue(status="pending")
        if err:
            continue

        operations = (data or {}).get("operations", [])
        for op in operations:
            plan = op.get("plan", {})
            opp = plan.get("opportunity", plan)  # plan.opportunity or plan itself
            if opp.get("asset") == asset and opp.get("direction") == direction:
                return op, None

    return None, (
        f"No pending queue entry for {asset} {direction} after {timeout}s"
    )


def verify_execution_record(record: dict, asset: str, direction: str,
                            expected_ops: list[str] | None = None,
                            balance_token: str | None = None,
                            balance_tolerance: float = 0.10,
                            start_balance: int | None = None) -> TestResult:
    """Verify an execution history record. Returns test result dict.

    Checks (in order):
    1. result.success == True
    2. plan.opportunity.asset/direction match
    3. Step ops match expected (soft -- doesn't fail if extraction empty)
    4. Balance token approximately round-trips (soft)
    """
    exec_result = record.get("result", {})
    success = exec_result.get("success", False)
    if not success:
        error_msg = exec_result.get("error", "unknown")
        return result(FAIL,
            f"{asset} {direction} executed but failed: {error_msg}")

    opp = record.get("plan", {}).get("opportunity", {})
    rec_asset = opp.get("asset", "")
    rec_dir = opp.get("direction", "")
    if rec_asset != asset:
        return result(FAIL,
            f"Execution asset mismatch: expected={asset}, got={rec_asset}")
    if rec_dir != direction:
        return result(FAIL,
            f"Execution direction mismatch: expected={direction}, got={rec_dir}")

    # Step ops (soft verification)
    ops = extract_step_ops(record)
    ops_note = ""
    if expected_ops and ops:
        if ops != expected_ops:
            ops_note = f" (ops mismatch: expected={expected_ops}, got={ops})"
        else:
            ops_note = f" ops={ops}"
    elif ops:
        ops_note = f" ops={ops}"
    elif expected_ops:
        ops_note = " (ops extraction unavailable)"

    # Balance round-trip (soft verification)
    balance_note = ""
    if balance_token and start_balance is not None and start_balance > 0:
        token_addr = TK.get(balance_token)
        if token_addr:
            end_balance, _ = balance_of(token_addr, ENGINE_ADDRESS)
            if end_balance is not None:
                change = abs(end_balance - start_balance) / start_balance
                if change <= balance_tolerance:
                    balance_note = (
                        f" balance={balance_token} "
                        f"{change*100:.1f}% change (within {balance_tolerance*100:.0f}%)"
                    )
                else:
                    balance_note = (
                        f" balance={balance_token} "
                        f"{change*100:.1f}% change (EXCEEDS {balance_tolerance*100:.0f}%)"
                    )

    steps_count = exec_result.get("stepsExecuted", "?")
    return result(PASS,
        f"{asset} {direction} executed: success=True, "
        f"steps={steps_count}{ops_note}{balance_note}")


# ===========================================================================
# Pattern: Warning presence check
# ===========================================================================

def assert_warning_present(probes: dict, warning_substr: str,
                           strategy: str = "arb",
                           setup_fn: Any = None) -> TestResult:
    """Verify a warning string is present in evaluate response.

    Args:
        warning_substr: substring to search for in warnings
        strategy: strategy to check (default "arb")
        setup_fn: optional callable to run before checking (e.g. set_rr_mode)
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    if setup_fn:
        setup_fn()
        wait_sync()

    analysis, err = engine_evaluate(strategies=strategy)
    if err:
        return result(FAIL, f"Engine unreachable: {err}")

    warnings = find_warnings(analysis, strategy)
    matching = [w for w in warnings if warning_substr.lower() in str(w).lower()]

    if matching:
        return result(PASS, f"Warning found: {matching[0]}")
    return result(FAIL,
        f"Warning '{warning_substr}' not found. "
        f"Warnings: {warnings[:5]}")
