"""EXEC: Arb Execution — Real E2E execution tests (manual approval flow).

These tests verify the engine can detect, plan, and execute real arbitrage
trades on the devnet. Unlike DISP (dispatch routing) tests which only do
API introspection, EXEC tests trigger actual on-chain swaps, bridge wraps/
unwraps, and native conversions with real balance changes.

Each test follows a manual approval flow:

  Setup:
    - Engine set to manual mode (autoExecute=true, manualApproval=true)
    - Test wallet funded with wrapped tokens via bridge wrap flow
    - Test wallet pushes pool price to create an arb opportunity

  Preflight — Detection:
    - Wait for engine cycle, call evaluate API
    - Verify the engine detects the opportunity (asset, direction, gapBps)
    - Engine should behave well — no spamming, no infinite loops

  Preflight — Planning:
    - Poll engine queue for a pending operation
    - Verify plan was queued (not auto-executed) with expected ops
    - Engine should have ONE queued plan — no duplicates

  Execution:
    - Approve the specific operation by ID via queue API
    - Wait for engine to execute (poll history, up to 90s)

  Verification:
    - Execution record: success=true, correct asset/direction
    - Step ops match expected trade flow
    - Engine balance approximately round-trips

Requirements:
    - `make dev` with engine + bridge running (`make dev APPS=engine,bridge`)
    - Fresh devnet state recommended (`make dev-reset && make dev`)
    - ENGINE_PK and ENGINE_ADDRESS set in .env
    - TEST_USER_1_ADDRESS and TEST_USER_1_PK set in .env
    - manualApproval column in engineSettings (auto-created by prisma)
"""
from __future__ import annotations

from _helpers import (
    FAIL, BLOCKED,
    ASSET_POOL, ASSET_THRESHOLD,
    ENGINE_ADDRESS,
    TEST_WALLET_ADDRESS, TEST_WALLET_PK,
    EXEC_SWAP_AMOUNTS, SWAP_AMOUNT,
    WAIT_EXEC_LONG, WAIT_EXEC_POLL,
    result, needs, needs_engine_env,
    engine_evaluate, engine_queue_action,
    engine_history,
    find_opportunity, get_gap_bps,
    push_pool_price, restore_pool,
    ensure_test_wallet_funded,
    runner_mode, wait_for_queued_plan, wait_for_execution,
    wait_sync,
    verify_execution_record,
    plan_stage_ops,
    balance_of, TK,
    is_engine_running,
    _extract_execution_ids,
)


# ==========================================================================
# EXEC-01: ZEPH arb execution
# ==========================================================================


def test_exec_01a_zeph_evm_premium_native_close(probes):
    """EXEC-01a: ZEPH evm_premium native close (manual approval flow)

    Network state: Normal RR (4x-8x), devnet at default oracle ($1.50)

    Pool push: Sell wZSD into wZEPH-wZSD pool → wZEPH becomes expensive
    on EVM relative to oracle price → creates evm_premium opportunity
    (>100bps gap required to exceed ZEPH threshold)

    Expected trade flow (what the engine should execute):
      Open:  swapEVM      — sell overpriced wZEPH → buy wZSD on Uniswap V4
      Close: unwrap       — burn wZSD on EVM → receive ZSD on Zephyr chain
             nativeRedeem — convert ZSD → ZEPH (always available, no RR gate)
             wrap         — send ZEPH on Zephyr → claim wZEPH on EVM

    Net effect: engine captures the premium spread, ends with ~same wZEPH.
    ZSD redeem is never protocol-blocked — native close works at any RR.
    """
    asset = "ZEPH"
    direction = "evm_premium"
    pool = ASSET_POOL[asset]
    push_dir = "premium"
    swap_amount = EXEC_SWAP_AMOUNTS.get((pool, push_dir), SWAP_AMOUNT)
    expected_ops = ["swapEVM", "unwrap", "nativeRedeem", "wrap"]
    threshold = ASSET_THRESHOLD[asset]

    # ── Pre-checks ────────────────────────────────────────────────────
    # Verify required services, env vars, and engine-run process
    blocked = needs(probes, "engine", "anvil")
    if blocked:
        return blocked
    blocked = needs_engine_env()
    if blocked:
        return blocked
    if not TEST_WALLET_ADDRESS or not TEST_WALLET_PK:
        return result(BLOCKED,
            "TEST_USER_1_ADDRESS / TEST_USER_1_PK not set in .env")
    if not is_engine_running():
        return result(BLOCKED,
            "engine-run not running (start with: make dev APPS=engine)")

    # ── Phase 0: Fund test wallet ─────────────────────────────────────
    # Test wallet needs wZSD to push the pool. Wrapped tokens can only be
    # created through the real bridge wrap flow:
    #   gov sends ZSD to bridge subaddress → watcher detects → claim on EVM
    _, fund_err = ensure_test_wallet_funded("wZSD", swap_amount)
    if fund_err:
        return result(BLOCKED, f"Test wallet funding: {fund_err}")

    # ── Phase 1: Configure engine + push pool ─────────────────────────
    # Set engine to manual approval mode so plans are queued (not auto-executed).
    # Cooldown=1s avoids engine skipping this opportunity due to prior runs.
    with runner_mode(autoExecute=True, manualApproval=True, cooldownMs=1000):

        # Snapshot engine's wZEPH balance before execution — we'll verify
        # the round-trip at the end (should be ~same after arb completes)
        start_balance = None
        token_addr = TK.get("wZEPH")
        if token_addr:
            start_balance, _ = balance_of(token_addr, ENGINE_ADDRESS)

        # Snapshot existing execution IDs so we can detect NEW ones later
        history, err = engine_history(strategy="arb")
        if err:
            return result(BLOCKED, f"History endpoint: {err}")
        baseline_ids = _extract_execution_ids(history, asset)

        # Push pool price using TEST WALLET (not engine wallet).
        # Sells wZSD → buys wZEPH → makes wZEPH expensive → evm_premium.
        push_info, push_err = push_pool_price(
            pool, push_dir, swap_amount,
            pk=TEST_WALLET_PK, sender=TEST_WALLET_ADDRESS,
        )
        if push_err:
            return result(BLOCKED, f"Pool push: {push_err}")

        try:
            # ── Phase 2: Preflight — Detection ────────────────────────
            # Wait for engine to complete at least one cycle after pool push,
            # then verify it detected the evm_premium opportunity for ZEPH.
            # Engine should detect cleanly — no spamming or infinite loops.
            wait_sync(12)  # engine interval=5s + watcher sync + processing

            analysis, err = engine_evaluate()
            if err:
                return result(FAIL,
                    f"Engine unreachable after pool push: {err}")

            opps, _ = find_opportunity(analysis, asset, direction)
            gap_bps = get_gap_bps(analysis, asset)

            if not opps:
                return result(FAIL,
                    f"Detection failed: no {direction} opportunity for "
                    f"{asset}. gapBps={gap_bps}, threshold={threshold}")

            if gap_bps is not None and abs(gap_bps) < threshold:
                return result(FAIL,
                    f"Detection: gap too small. gapBps={gap_bps}, "
                    f"threshold={threshold}")

            # ── Phase 3: Preflight — Planning ─────────────────────────
            # With manualApproval=true, the engine should queue a plan
            # (status=pending) instead of auto-executing. Poll the queue
            # for a matching operation. Engine should create ONE plan —
            # not duplicates or infinite re-queuing.
            queued_op, err = wait_for_queued_plan(
                asset, direction, timeout=30,
            )
            if err or queued_op is None:
                return result(FAIL,
                    f"Plan not queued: {err or 'no matching operation'}. "
                    f"Detection confirmed gap={gap_bps}bps but engine "
                    f"did not queue a plan for approval")

            operation_id = queued_op.get("id")
            queued_plan = queued_op.get("plan", {})

            # Verify plan structure: should contain the expected trade ops
            queued_ops = plan_stage_ops(queued_plan)
            plan_note = ""
            if queued_ops:
                if queued_ops == expected_ops:
                    plan_note = f"ops={queued_ops}"
                else:
                    plan_note = (
                        f"ops={queued_ops} (expected {expected_ops})"
                    )
            else:
                plan_note = "ops extraction unavailable from queued plan"

            # ── Phase 4: Approve execution ────────────────────────────
            # Approve this specific operation by ID. The engine's
            # processApprovedQueue() picks it up on the next cycle and
            # executes the full trade flow.
            approve_data, err = engine_queue_action(
                "approve", operation_id=operation_id,
            )
            if err:
                return result(FAIL,
                    f"Queue approve failed: {err} ({plan_note})")

            updated = (approve_data or {}).get("updated", 0)
            if updated == 0:
                return result(FAIL,
                    f"Approve returned updated=0 for {operation_id}")

            # ── Phase 5: Wait for execution to complete ───────────────
            # Poll history for a NEW execution record for ZEPH.
            # Multi-step execution (swap + unwrap + nativeRedeem + wrap)
            # involves real Zephyr txns — timing varies by mining speed.
            record, err = wait_for_execution(
                asset, baseline_ids,
                timeout=WAIT_EXEC_LONG,
                poll_interval=WAIT_EXEC_POLL,
            )
            if err or record is None:
                return result(FAIL,
                    err or "No execution record after approval")

            # ── Phase 6: Verify execution record ──────────────────────
            # Check: success=true, asset/direction match, step ops match,
            # and engine wZEPH balance approximately round-trips (within
            # 10% tolerance — some slippage/fees expected).
            return verify_execution_record(
                record, asset, direction,
                expected_ops=expected_ops,
                balance_token="wZEPH",
                balance_tolerance=0.10,
                start_balance=start_balance,
            )

        finally:
            # Always restore pool price regardless of test outcome
            if push_info:
                restore_pool(push_info)


def test_exec_01b_zeph_evm_premium_cex_close(probes):
    """EXEC-01b: ZEPH evm_premium CEX close"""
    pass


def test_exec_01c_zeph_evm_discount_native_close(probes):
    """EXEC-01c: ZEPH evm_discount native close"""
    pass


def test_exec_01d_zeph_evm_discount_cex_close(probes):
    """EXEC-01d: ZEPH evm_discount CEX close"""
    pass


def test_exec_01e_zeph_defensive_mode(probes):
    """EXEC-01e: ZEPH in defensive RR mode"""
    pass


def test_exec_01f_zeph_crisis_mode(probes):
    """EXEC-01f: ZEPH in crisis RR mode"""
    pass


# ==========================================================================
# Export
# ==========================================================================

TESTS = {
    "EXEC-01a": test_exec_01a_zeph_evm_premium_native_close,
    "EXEC-01b": test_exec_01b_zeph_evm_premium_cex_close,
    "EXEC-01c": test_exec_01c_zeph_evm_discount_native_close,
    "EXEC-01d": test_exec_01d_zeph_evm_discount_cex_close,
    "EXEC-01e": test_exec_01e_zeph_defensive_mode,
    "EXEC-01f": test_exec_01f_zeph_crisis_mode,
}
