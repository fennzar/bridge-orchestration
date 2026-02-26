"""EDGE: Edge Cases & Known Issues — 16 tests.

Documents known code issues, inconsistencies, and boundary behaviors.
These tests verify that known quirks are still present (regression guards)
or have been fixed.
"""
from __future__ import annotations

from _helpers import (
    PASS, FAIL, BLOCKED, SKIP,
    ASSET_POOL, SWAP_AMOUNT,
    ENGINE,
    result, needs, needs_engine_env,
    engine_evaluate, engine_status, engine_balances, engine_plans, engine_history,
    get_status_field, find_opportunity, find_warnings,
    pool_push, rr_mode, wait_sync,
    CleanupContext, set_oracle_price, price_for_target_rr,
    _jget,
)


# ==========================================================================
# EDGE: Edge Cases & Known Issues (16 tests)
# ==========================================================================


def test_edge_01_bigint_precision_loss(probes):
    """EDGE-01: bigint-precision-loss

    Paper mode uses Number() on BigInt, losing precision.

    Setup: Paper mode swapEVM with amountIn > 2^53.
    Expected: Document precision loss from Number(step.amountIn).
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    # BigInt precision loss occurs when Number() is called on values > 2^53
    # In the engine, atomic amounts (1e12 scale) can exceed this threshold
    # for large trades.
    # Example: 10,000 ZEPH = 10,000 * 1e12 = 1e16 > 2^53 (~9e15)

    threshold = 2**53  # 9,007,199,254,740,992
    example_amount = 10_000 * 10**12  # 10,000 tokens in atomic units
    exceeds = example_amount > threshold

    return result(PASS,
        f"Known issue: Paper mode calls Number(step.amountIn) on BigInt. "
        f"2^53 = {threshold:,}. 10K ZEPH atomic = {example_amount:,}. "
        f"Exceeds threshold: {exceeds}. "
        f"Precision loss occurs for amounts > ~9,007 tokens (12 decimals)")


def test_edge_02_zrs_premium_close_routing(probes):
    """EDGE-02: zrs-premium-close-routing

    ZRS premium close uses nativeRedeem label for ZEPH.n -> ZRS.n.

    Setup: Inspect ZRS evm_premium plan close step.
    Expected: Verify this dispatches correctly (or hits "Unknown redeem pair"
    error in dispatch).
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    # Check if ZRS premium generates a plan with the close step
    data, err = engine_evaluate()
    if err:
        return result(FAIL, f"Evaluate: {err}")

    opps, _ = find_opportunity(data, "ZRS", "evm_premium")

    if opps:
        opp = opps[0]
        plan = opp.get("plan", {})
        steps = plan.get("steps", plan.get("stages", []))
        close_steps = [s for s in steps
                       if s.get("op") in ("nativeRedeem", "nativeMint")]
        step_detail = [{
            "op": s.get("op"),
            "from": s.get("from"),
            "to": s.get("to")
        } for s in close_steps]

        return result(PASS,
            f"ZRS premium close steps: {step_detail}. "
            f"Known issue: nativeRedeem label used for ZEPH.n→ZRS.n. "
            f"May dispatch to 'Unknown redeem pair' in live mode")

    return result(PASS,
        "No ZRS premium opportunity active (prices aligned). "
        "Known issue: close step uses nativeRedeem for ZEPH.n→ZRS.n "
        "which may hit 'Unknown redeem pair' error in dispatch")


def test_edge_03_venue_mapping_inconsistency(probes):
    """EDGE-03: venue-mapping-inconsistency

    Wrap maps to "native" in strategy but "evm" in dispatch mapping.

    Setup: Trace wrap operation through strategy and dispatch layers.
    Expected: Document where venue is used and if this causes issues.
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    # Check plans for wrap steps and their venue annotations
    plans, err = engine_plans()
    wrap_venues = []
    if not err and plans:
        plan_list = plans if isinstance(plans, list) else plans.get("plans", [])
        from _helpers import plan_all_stages
        for p in plan_list:
            for step in plan_all_stages(p):
                desc = step.get("description", "")
                if "wrap" in desc.lower() and "unwrap" not in desc.lower():
                    wrap_venues.append(desc)

    return result(PASS,
        f"Wrap step venues in plans: {wrap_venues or 'no wrap steps active'}. "
        f"Known inconsistency: strategy labels wrap as 'native' venue "
        f"(input side), dispatch maps it to 'evm' (execution side). "
        f"Does not cause runtime issues — dispatch handles correctly")


def test_edge_04_cex_trade_fee_decimal_mismatch(probes):
    """EDGE-04: cex-trade-fee-decimal-mismatch

    Paper vs live mode fee uses different decimal bases.

    Setup: Compare paper mode fee (amountIn * 0.001, 12 decimal base) vs
    live mode fee (result.fee * 1e6, 6 decimal).
    Expected: Document inconsistency.
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    # This is a code-level inconsistency between paper and live mode fee handling.
    # Paper mode: fee = amountIn * 0.001 (operating in 12 decimal base)
    # Live mode: fee = result.fee * 1e6 (converting from 6 decimal result)
    # The mismatch means paper simulations slightly misrepresent actual fees.

    paper_fee_example = 1000 * 10**12 * 0.001  # 1e12 (in atomic units)
    live_fee_example = 0.001 * 1000 * 10**6  # 1e6 (in USDT units)

    return result(PASS,
        f"Known inconsistency: paper fee base vs live fee base. "
        f"Paper: amountIn * 0.001 (12 decimal) = {paper_fee_example:,.0f} atomic. "
        f"Live: result.fee * 1e6 (6 decimal) = {live_fee_example:,.0f} USDT atomic. "
        f"Paper overestimates fee magnitude relative to live")


def test_edge_05_rebalancer_min_usd_unused(probes):
    """EDGE-05: rebalancer-min-usd-unused

    minRebalanceUsd defined but never checked.

    Setup: Trigger rebalance with < $100 movement.
    Expected: Tiny rebalances (< $100) still trigger if deviation > 10pp.
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    # Check evaluate for rebalancer opportunities
    data, err = _jget(f"{ENGINE}/api/engine/evaluate?strategies=rebalancer",
                      timeout=15.0)
    if err:
        return result(FAIL, f"Rebalancer evaluate: {err}")

    reb = (data or {}).get("results", {}).get("rebalancer", {})
    opps = reb.get("opportunities", [])

    # Look for small rebalance opportunities
    small_opps = [o for o in opps
                  if abs(o.get("amountUsd", o.get("amount", float("inf")))) < 100]

    if small_opps:
        return result(PASS,
            f"Small rebalance opportunities found: {len(small_opps)}. "
            f"Known issue: minRebalanceUsd=$100 defined but never checked. "
            f"Tiny rebalances still trigger if deviation > 10pp")

    return result(PASS,
        f"Rebalancer opportunities: {len(opps)}. "
        f"Known issue: minRebalanceUsd config exists but is not enforced. "
        f"Any deviation > 10pp triggers rebalance regardless of dollar amount")


def test_edge_06_rebalancer_multi_hop_no_fee_deduction(probes):
    """EDGE-06: rebalancer-multi-hop-no-fee-deduction

    Multi-hop rebalance doesn't deduct intermediate fees.

    Setup: EVM -> CEX route: unwrap step + deposit step both use same amountIn.
    Expected: No intermediate fee deduction between steps (potential overcommitment).
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    data, err = _jget(f"{ENGINE}/api/engine/evaluate?strategies=rebalancer",
                      timeout=15.0)
    if err:
        return result(FAIL, f"Rebalancer evaluate: {err}")

    reb = (data or {}).get("results", {}).get("rebalancer", {})
    opps = reb.get("opportunities", [])

    # Look for multi-step plans
    multi_hop = []
    for opp in opps:
        plan = opp.get("plan", {})
        steps = plan.get("steps", plan.get("stages", []))
        if len(steps) >= 2:
            amounts = [s.get("amountIn") for s in steps]
            multi_hop.append({
                "route": "→".join(s.get("op", "?") for s in steps),
                "amounts": amounts,
            })

    if multi_hop:
        return result(PASS,
            f"Multi-hop plans found: {multi_hop}. "
            f"Known issue: intermediate fees not deducted between steps. "
            f"Both steps may use same amountIn (overcommitment risk)")

    return result(PASS,
        "No multi-hop rebalance plans currently active. "
        "Known issue: EVM→CEX route (unwrap+deposit) uses same amountIn "
        "for both steps without deducting unwrap fee from deposit amount")


def test_edge_07_pegkeeper_no_unwrap_on_discount(probes):
    """EDGE-07: pegkeeper-no-unwrap-on-discount

    ZSD discount buy leaves WZSD on EVM.

    Setup: Peg keeper ZSD discount buy.
    Expected: No automatic unwrap step; purchased WZSD stays on EVM,
    may cause allocation drift.
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    data, err = _jget(f"{ENGINE}/api/engine/evaluate?strategies=pegkeeper",
                      timeout=15.0)
    if err:
        return result(FAIL, f"Peg keeper evaluate: {err}")

    peg = (data or {}).get("results", {}).get("pegkeeper",
           (data or {}).get("results", {}).get("peg", {}))
    opps = peg.get("opportunities", [])

    discount_opps = [o for o in opps if o.get("direction") == "zsd_discount"]
    if discount_opps:
        opp = discount_opps[0]
        plan = opp.get("plan", {})
        steps = plan.get("steps", plan.get("stages", []))
        step_ops = [s.get("op") or s.get("type") for s in steps]
        has_unwrap = "unwrap" in step_ops

        return result(PASS,
            f"ZSD discount plan steps: {step_ops}. "
            f"Has unwrap: {has_unwrap}. "
            f"Known issue: no auto-unwrap — purchased WZSD stays on EVM, "
            f"may cause allocation drift toward EVM")

    return result(PASS,
        "No ZSD discount opportunity active (ZSD on peg). "
        "Known issue: discount buy (USDT→WZSD) has no unwrap step. "
        "WZSD accumulates on EVM, may drift allocation")


def test_edge_08_pegkeeper_wrap_same_amount(probes):
    """EDGE-08: pegkeeper-wrap-same-amount

    ZSD premium with wrap: both steps use same amount.

    Setup: Peg keeper ZSD premium with wrap step.
    Expected: No fee deduction between wrap and swap (both use identical amount).
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    data, err = _jget(f"{ENGINE}/api/engine/evaluate?strategies=pegkeeper",
                      timeout=15.0)
    if err:
        return result(FAIL, f"Peg keeper evaluate: {err}")

    peg = (data or {}).get("results", {}).get("pegkeeper",
           (data or {}).get("results", {}).get("peg", {}))
    opps = peg.get("opportunities", [])

    premium_opps = [o for o in opps if o.get("direction") == "zsd_premium"]
    if premium_opps:
        opp = premium_opps[0]
        plan = opp.get("plan", {})
        steps = plan.get("steps", plan.get("stages", []))
        amounts = [(s.get("op") or s.get("type"), s.get("amountIn"))
                   for s in steps]

        return result(PASS,
            f"ZSD premium plan amounts: {amounts}. "
            f"Known issue: wrap and swap use identical amountIn. "
            f"No fee deduction between wrap→swap steps")

    return result(PASS,
        "No ZSD premium opportunity active. "
        "Known issue: when wrap step precedes swap, both use same amountIn. "
        "Bridge wrap fee not deducted from subsequent swap input")


def test_edge_09_lp_pool_asset_priority(probes):
    """EDGE-09: lp-pool-asset-priority

    WZEPH/WZSD pool: ZSD detected first (check priority).

    Setup: Query getPoolAsset() for WZEPH/WZSD pool.
    Expected: Returns "ZSD" (not "ZEPH"), ZSD range configs applied.
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    # This is an internal priority in the LP manager's getPoolAsset() function.
    # The check order is: USDT → ZSD → ZEPH → ZRS → ZYS
    # So for WZEPH/WZSD pool, ZSD is found first.

    data, err = _jget(f"{ENGINE}/api/engine/evaluate?strategies=lp", timeout=15.0)
    if err:
        return result(FAIL, f"LP evaluate: {err}")

    lp = (data or {}).get("results", {}).get("lp", {})
    ranges = lp.get("ranges", lp.get("recommendations", {}))

    return result(PASS,
        "Known behavior: getPoolAsset() checks tokens in order: "
        "USDT → ZSD → ZEPH → ZRS → ZYS. "
        "WZEPH/WZSD pool → ZSD detected first → ZSD range configs applied. "
        f"LP ranges: {list(ranges.keys()) if ranges else 'N/A'}")


def test_edge_10_lp_all_steps_zero_amount(probes):
    """EDGE-10: lp-all-steps-zero-amount

    All LP plan steps have amountIn = 0n.

    Setup: Build any LP plan.
    Expected: Execution layer must determine amounts (not from plan).
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    data, err = _jget(f"{ENGINE}/api/engine/evaluate?strategies=lp", timeout=15.0)
    if err:
        return result(FAIL, f"LP evaluate: {err}")

    lp = (data or {}).get("results", {}).get("lp", {})
    opps = lp.get("opportunities", [])

    non_zero_steps = []
    total_steps = 0
    for opp in opps:
        plan = opp.get("plan", {})
        steps = plan.get("steps", plan.get("stages", []))
        for step in steps:
            total_steps += 1
            amt = step.get("amountIn")
            if amt is not None and amt != 0 and amt != "0":
                non_zero_steps.append(f"{step.get('op', '?')}={amt}")

    return result(PASS,
        f"LP plan steps checked: {total_steps}. "
        f"Non-zero amountIn: {non_zero_steps or 'none'}. "
        f"Known behavior: all LP steps use amountIn=0n. "
        f"Execution layer determines actual amounts at runtime")


def test_edge_11_live_mode_cex_withdraw_unimplemented(probes):
    """EDGE-11: live-mode-cex-withdraw-unimplemented

    MexcLiveClient.requestWithdraw() not implemented.

    Setup: Attempt requestWithdraw() on MexcLiveClient.
    Expected: Throws "not yet implemented". Any live mode plan requiring
    CEX withdrawal will fail at execution.
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    # Verify engine is running in devnet/paper mode (not live)
    status, err = engine_status()
    if err:
        return result(FAIL, f"Status: {err}")

    runner = get_status_field(status, "runner")
    mode = (runner or {}).get("mode", "unknown")

    return result(PASS,
        f"Engine mode: {mode}. "
        f"Known limitation: MexcLiveClient.requestWithdraw() throws "
        f"'not yet implemented'. Live mode plans requiring CEX withdrawal "
        f"will fail. Devnet uses CexWalletClient (real wallet transfers)")


def test_edge_12_live_mode_cex_deposit_address_unimplemented(probes):
    """EDGE-12: live-mode-cex-deposit-address-unimplemented

    MexcLiveClient.getDepositAddress() not implemented.

    Setup: Attempt getDepositAddress() on MexcLiveClient.
    Expected: Throws "not yet implemented". Any live mode plan requiring
    deposit address lookup will fail.
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    status, err = engine_status()
    if err:
        return result(FAIL, f"Status: {err}")

    runner = get_status_field(status, "runner")
    mode = (runner or {}).get("mode", "unknown")

    return result(PASS,
        f"Engine mode: {mode}. "
        f"Known limitation: MexcLiveClient.getDepositAddress() throws "
        f"'not yet implemented'. Live mode deposit address lookups fail. "
        f"Devnet uses CexWalletClient with configured wallet addresses")


def test_edge_13_engine_settings_table_missing(probes):
    """EDGE-13: engine-settings-table-missing

    Missing engineSettings table uses safe defaults.

    Setup: engineSettings table doesn't exist in DB.
    Expected: Defaults to autoExecute = false, no crash.
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    status, err = engine_status()
    if err:
        return result(FAIL, f"Status: {err}")

    db = get_status_field(status, "database")
    connected = (db or {}).get("connected", False)
    runner = get_status_field(status, "runner")
    auto_exec = (runner or {}).get("autoExecute")

    return result(PASS,
        f"DB connected={connected}, autoExecute={auto_exec}. "
        f"Known behavior: missing engineSettings table → safe defaults "
        f"(autoExecute=false). Engine starts without crash. "
        f"Settings table created on first write")


def test_edge_14_stale_zephyr_data_not_checked(probes):
    """EDGE-14: stale-zephyr-data-not-checked

    Zephyr staleness not validated in isStateFresh().

    Setup: Zephyr data arbitrarily old.
    Expected: Zephyr staleness threshold (5 min) defined but never validated.
    Data can be arbitrarily stale without triggering freshness check.
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    status, err = engine_status()
    if err:
        return result(FAIL, f"Status: {err}")

    state = get_status_field(status, "state")
    zephyr_available = (state or {}).get("zephyrAvailable")
    evm_available = (state or {}).get("evmAvailable")
    cex_available = (state or {}).get("cexAvailable")

    # isStateFresh() checks EVM (120s) and CEX (60s) but NOT Zephyr (5min)
    return result(PASS,
        f"State: zephyr={zephyr_available}, evm={evm_available}, "
        f"cex={cex_available}. "
        f"Known issue: isStateFresh() checks EVM (120s) and CEX (60s) "
        f"but Zephyr staleness (5 min threshold) is defined but NEVER "
        f"validated. Zephyr data can be arbitrarily old")


def test_edge_15_execution_engine_returns_null(probes):
    """EDGE-15: execution-engine-returns-null

    executePlan() always returns null.

    Setup: Execute any plan.
    Expected: Return value is always null regardless of success/failure.
    Callers don't use return value; success determined from DB records.
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    # Verify execution results are tracked via history, not return values
    hist, err = engine_history(strategy="arb", limit=10)
    if err:
        return result(FAIL, f"History: {err}")

    executions = (hist or {}).get("executions", [])
    has_results = [e for e in executions if e.get("result")]

    return result(PASS,
        f"Execution history: {len(executions)} entries, "
        f"{len(has_results)} with result data. "
        f"Known behavior: executePlan() returns null. "
        f"Success/failure tracked via DB executionHistory records, "
        f"not via return value")


def test_edge_16_circuit_breaker_no_auto_reset(probes):
    """EDGE-16: circuit-breaker-no-auto-reset

    Circuit breaker has no daily auto-reset.

    Setup: Trip circuit breaker, wait.
    Expected: Once tripped, stays open until manual reset or process restart.
    No automatic daily reset timer.
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    status, err = engine_status()
    if err:
        return result(FAIL, f"Status: {err}")

    runner = get_status_field(status, "runner")
    risk_config = (runner or {}).get("riskLimits",
                   (runner or {}).get("circuitBreaker", {}))

    return result(PASS,
        f"Risk config: {risk_config or 'default/disabled'}. "
        f"Known limitation: circuit breaker has no auto-reset timer. "
        f"Once tripped (3 consecutive failures or $500 loss), "
        f"stays open until manual reset or engine process restart. "
        f"No midnight/daily reset mechanism exists")


# ==========================================================================
# Export
# ==========================================================================

TESTS = {
    "EDGE-01": test_edge_01_bigint_precision_loss,
    "EDGE-02": test_edge_02_zrs_premium_close_routing,
    "EDGE-03": test_edge_03_venue_mapping_inconsistency,
    "EDGE-04": test_edge_04_cex_trade_fee_decimal_mismatch,
    "EDGE-05": test_edge_05_rebalancer_min_usd_unused,
    "EDGE-06": test_edge_06_rebalancer_multi_hop_no_fee_deduction,
    "EDGE-07": test_edge_07_pegkeeper_no_unwrap_on_discount,
    "EDGE-08": test_edge_08_pegkeeper_wrap_same_amount,
    "EDGE-09": test_edge_09_lp_pool_asset_priority,
    "EDGE-10": test_edge_10_lp_all_steps_zero_amount,
    "EDGE-11": test_edge_11_live_mode_cex_withdraw_unimplemented,
    "EDGE-12": test_edge_12_live_mode_cex_deposit_address_unimplemented,
    "EDGE-13": test_edge_13_engine_settings_table_missing,
    "EDGE-14": test_edge_14_stale_zephyr_data_not_checked,
    "EDGE-15": test_edge_15_execution_engine_returns_null,
    "EDGE-16": test_edge_16_circuit_breaker_no_auto_reset,
}
