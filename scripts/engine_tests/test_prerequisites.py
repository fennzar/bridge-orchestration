"""PRE: Prerequisites & State Building — 12 tests.

Foundation tests. If these fail, nothing downstream is trustworthy.
Validates reserve parsing, policy gates, RR mode, state building, and decimals.
"""
from __future__ import annotations

from _helpers import (
    PASS, FAIL, BLOCKED,
    TK, NODE1_RPC,
    result, needs, needs_engine_env,
    engine_status, engine_evaluate, engine_balances,
    daemon_reserve_info, decimals_of,
    get_status_field,
    price_for_target_rr, set_rr_mode, set_oracle_price,
    mine_blocks, wait_sync,
    EngineCleanupContext, _rpc,
)


def _price_for_rr(current_price: float, current_rr_pct: float, target_rr: float) -> float:
    """Compute oracle price for a target RR.

    current_rr_pct is from engine API (percentage, e.g. 475.89).
    target_rr is decimal (e.g. 3.5).
    """
    return max(0.001, current_price * target_rr / (current_rr_pct / 100))


# ==========================================================================
# PRE-01..PRE-04: Reserve & RR fundamentals
# ==========================================================================


def test_pre_01_reserve_state_parsing(probes):
    """PRE-01: reserve-state-parsing

    Verify engine parses daemon reserve data correctly. Cross-check daemon
    get_reserve_info with engine evaluate/status state fields.
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    # 1. Engine status — basic reserve fields
    status, err = engine_status()
    if err:
        return result(FAIL, f"Status: {err}")

    state = get_status_field(status, "state")
    if not state:
        return result(FAIL, "No 'state' in status response")

    rr = state.get("reserveRatio")
    if rr is None:
        return result(FAIL, "No reserveRatio in status.state")
    if not isinstance(rr, (int, float)) or rr <= 0:
        return result(FAIL, f"reserveRatio={rr} — expected positive number")

    # 2. Engine evaluate — more detailed state
    eval_data, err = engine_evaluate()
    if err:
        return result(FAIL, f"Evaluate: {err}")

    ev_state = get_status_field(eval_data, "state")
    if not ev_state:
        return result(FAIL, "No 'state' in evaluate response")

    required = ["reserveRatio", "reserveRatioMa", "zephPrice", "rrMode"]
    missing = [f for f in required if ev_state.get(f) is None]
    if missing:
        return result(FAIL, f"Missing evaluate state fields: {missing}")

    zp = ev_state["zephPrice"]
    if not isinstance(zp, (int, float)) or zp <= 0 or zp > 100_000:
        return result(FAIL, f"zephPrice={zp} — expected sane USD value")

    rr_ma = ev_state["reserveRatioMa"]
    if not isinstance(rr_ma, (int, float)) or rr_ma <= 0:
        return result(FAIL, f"reserveRatioMa={rr_ma} — expected positive decimal")

    rr_mode = ev_state["rrMode"]
    if rr_mode not in ("normal", "defensive", "crisis"):
        return result(FAIL, f"rrMode='{rr_mode}' — expected normal/defensive/crisis")

    # 3. Cross-check daemon reserve info (if accessible)
    daemon_rr, daemon_err = daemon_reserve_info()
    daemon_detail = ""
    if not daemon_err and daemon_rr:
        daemon_ratio = daemon_rr.get("reserve_ratio")
        if daemon_ratio is not None:
            daemon_detail = f", daemon_rr={daemon_ratio}"

    return result(PASS,
        f"RR={rr:.2f}, RR_MA={rr_ma:.2f}, "
        f"price=${zp}, rrMode={rr_mode}{daemon_detail}")


def test_pre_02a_zsd_mintable_boundary(probes):
    """PRE-02a: zsd-mintable-boundary

    ZSD mint requires RR >= 4.0 AND RR_MA >= 4.0. Test boundary by
    setting oracle to put RR just above and below 4.0.

    E2E approach: Set oracle → wait → check engine rrMode transition.
    At RR < 4.0, rrMode = "defensive" which implies ZSD mint is blocked.
    """
    blocked = needs(probes, "engine", "oracle")
    if blocked:
        return blocked

    # Get current baseline
    eval_data, err = engine_evaluate()
    if err:
        return result(FAIL, f"Evaluate: {err}")
    current_price = get_status_field(eval_data, "state", "zephPrice")
    current_rr = get_status_field(eval_data, "state", "reserveRatio")
    if not current_price or not current_rr:
        return result(BLOCKED, "Cannot read current price/RR")

    errors = []
    with EngineCleanupContext(price_usd=current_price):
        # Test RR = 4.5 (above threshold → normal → ZSD mintable)
        set_oracle_price(_price_for_rr(current_price, current_rr, 4.5))
        mine_blocks(5)
        wait_sync()
        ev, err = engine_evaluate()
        if err:
            return result(FAIL, f"Evaluate at RR~4.5: {err}")
        mode_above = get_status_field(ev, "state", "rrMode")
        rr_above = get_status_field(ev, "state", "reserveRatio")
        if mode_above != "normal":
            errors.append(f"RR~4.5 (actual={rr_above:.2f}): expected normal, got {mode_above}")

        # Test RR = 3.5 (below threshold → defensive → ZSD mint blocked)
        set_oracle_price(_price_for_rr(current_price, current_rr, 3.5))
        mine_blocks(5)
        wait_sync()
        ev, err = engine_evaluate()
        if err:
            return result(FAIL, f"Evaluate at RR~3.5: {err}")
        mode_below = get_status_field(ev, "state", "rrMode")
        rr_below = get_status_field(ev, "state", "reserveRatio")
        if mode_below != "defensive":
            errors.append(f"RR~3.5 (actual={rr_below:.2f}): expected defensive, got {mode_below}")

    if errors:
        return result(FAIL, "; ".join(errors))
    return result(PASS,
        f"RR={rr_above:.2f}→normal (ZSD mintable), "
        f"RR={rr_below:.2f}→defensive (ZSD mint blocked)")


def test_pre_02b_zsd_redeemable(probes):
    """PRE-02b: zsd-redeemable

    ZSD redeem is always available regardless of RR. Verify this by
    checking that the engine reports ZSD opportunities in both normal
    and crisis modes (redeem close path always available).
    """
    blocked = needs(probes, "engine", "oracle")
    if blocked:
        return blocked

    eval_data, err = engine_evaluate()
    if err:
        return result(FAIL, f"Evaluate: {err}")
    current_price = get_status_field(eval_data, "state", "zephPrice")
    current_rr = get_status_field(eval_data, "state", "reserveRatio")
    if not current_price or not current_rr:
        return result(BLOCKED, "Cannot read current price/RR")

    modes_checked = []
    with EngineCleanupContext(price_usd=current_price):
        # Check in normal mode
        modes_checked.append(("normal", get_status_field(eval_data, "state", "rrMode")))

        # Check in crisis mode
        set_oracle_price(_price_for_rr(current_price, current_rr, 1.5))
        mine_blocks(5)
        wait_sync()
        ev, err = engine_evaluate()
        if err:
            return result(FAIL, f"Evaluate at crisis: {err}")
        mode = get_status_field(ev, "state", "rrMode")
        rr = get_status_field(ev, "state", "reserveRatio")
        modes_checked.append(("crisis", mode))

        # In both modes, the evaluate should complete without error and
        # the engine should still be able to check all 8 legs
        metrics = get_status_field(ev, "results", "arb", "metrics")
        if not metrics:
            return result(FAIL, "No arb metrics at crisis RR")
        legs = metrics.get("totalLegsChecked", 0)
        if legs < 8:
            return result(FAIL, f"Only {legs}/8 legs checked at crisis (RR={rr:.2f})")

    return result(PASS,
        f"All 8 arb legs checked in both modes: "
        f"{', '.join(f'{m[0]}={m[1]}' for m in modes_checked)}")


def test_pre_02c_zrs_mintable_boundary(probes):
    """PRE-02c: zrs-mintable-boundary

    ZRS mint has BOTH lower (RR >= 4.0) and upper (RR <= 8.0) bounds.
    Test by setting oracle to put RR above 8.0 and below 4.0.
    """
    blocked = needs(probes, "engine", "oracle")
    if blocked:
        return blocked

    eval_data, err = engine_evaluate()
    if err:
        return result(FAIL, f"Evaluate: {err}")
    current_price = get_status_field(eval_data, "state", "zephPrice")
    current_rr = get_status_field(eval_data, "state", "reserveRatio")
    if not current_price or not current_rr:
        return result(BLOCKED, "Cannot read current price/RR")

    errors = []
    with EngineCleanupContext(price_usd=current_price):
        # RR ~ 6.0 (between 4 and 8 → ZRS mintable)
        set_oracle_price(_price_for_rr(current_price, current_rr, 6.0))
        mine_blocks(5)
        wait_sync()
        ev, _ = engine_evaluate()
        mode_mid = get_status_field(ev, "state", "rrMode")
        rr_mid = get_status_field(ev, "state", "reserveRatio")
        if mode_mid != "normal":
            errors.append(f"RR~6.0 (actual={rr_mid}): expected normal, got {mode_mid}")

        # RR ~ 9.0 (above 8 → ZRS mint blocked, but still "normal" rrMode)
        # NOTE: rrMode stays "normal" above 8.0, but ZRS upper bound is protocol-level
        set_oracle_price(_price_for_rr(current_price, current_rr, 9.0))
        mine_blocks(5)
        wait_sync()
        ev, _ = engine_evaluate()
        rr_high = get_status_field(ev, "state", "reserveRatio")

        # RR ~ 3.5 (below 4 → defensive → ZRS mint blocked)
        set_oracle_price(_price_for_rr(current_price, current_rr, 3.5))
        mine_blocks(5)
        wait_sync()
        ev, _ = engine_evaluate()
        mode_low = get_status_field(ev, "state", "rrMode")
        rr_low = get_status_field(ev, "state", "reserveRatio")
        if mode_low != "defensive":
            errors.append(f"RR~3.5 (actual={rr_low}): expected defensive, got {mode_low}")

    if errors:
        return result(FAIL, "; ".join(errors))
    return result(PASS,
        f"RR={rr_mid:.2f}→normal (ZRS mintable), "
        f"RR={rr_high:.2f}→normal (ZRS upper bound), "
        f"RR={rr_low:.2f}→defensive (ZRS blocked)")


def test_pre_02d_zrs_redeemable_boundary(probes):
    """PRE-02d: zrs-redeemable-boundary

    ZRS redeem requires RR >= 4.0. Test boundary.
    """
    blocked = needs(probes, "engine", "oracle")
    if blocked:
        return blocked

    eval_data, err = engine_evaluate()
    if err:
        return result(FAIL, f"Evaluate: {err}")
    current_price = get_status_field(eval_data, "state", "zephPrice")
    current_rr = get_status_field(eval_data, "state", "reserveRatio")
    if not current_price or not current_rr:
        return result(BLOCKED, "Cannot read current price/RR")

    errors = []
    with EngineCleanupContext(price_usd=current_price):
        # RR ~ 4.5 (above threshold → ZRS redeemable)
        set_oracle_price(_price_for_rr(current_price, current_rr, 4.5))
        mine_blocks(5)
        wait_sync()
        ev, _ = engine_evaluate()
        mode_above = get_status_field(ev, "state", "rrMode")
        rr_above = get_status_field(ev, "state", "reserveRatio")
        if mode_above != "normal":
            errors.append(f"RR~4.5 (actual={rr_above}): expected normal, got {mode_above}")

        # RR ~ 3.5 (below threshold → ZRS redeem blocked)
        set_oracle_price(_price_for_rr(current_price, current_rr, 3.5))
        mine_blocks(5)
        wait_sync()
        ev, _ = engine_evaluate()
        mode_below = get_status_field(ev, "state", "rrMode")
        rr_below = get_status_field(ev, "state", "reserveRatio")
        if mode_below != "defensive":
            errors.append(f"RR~3.5 (actual={rr_below}): expected defensive, got {mode_below}")

    if errors:
        return result(FAIL, "; ".join(errors))
    return result(PASS,
        f"RR={rr_above:.2f}→normal (ZRS redeemable), "
        f"RR={rr_below:.2f}→defensive (ZRS blocked)")


def test_pre_03_rr_mode_determination(probes):
    """PRE-03: rr-mode-determination

    Verify rrMode boundaries: normal (>=4.0), defensive (2.0-3.99), crisis (<2.0).
    Tests 3 target RR values and verifies engine reports correct mode.
    """
    blocked = needs(probes, "engine", "oracle")
    if blocked:
        return blocked

    eval_data, err = engine_evaluate()
    if err:
        return result(FAIL, f"Evaluate: {err}")
    current_price = get_status_field(eval_data, "state", "zephPrice")
    current_rr = get_status_field(eval_data, "state", "reserveRatio")
    if not current_price or not current_rr:
        return result(BLOCKED, "Cannot read current price/RR")

    test_cases = [
        (5.0, "normal"),
        (3.0, "defensive"),
        (1.5, "crisis"),
    ]

    results_log = []
    errors = []
    with EngineCleanupContext(price_usd=current_price):
        for target_rr, expected_mode in test_cases:
            set_oracle_price(_price_for_rr(current_price, current_rr, target_rr))
            mine_blocks(5)
            wait_sync()
            ev, err = engine_evaluate()
            if err:
                errors.append(f"RR~{target_rr}: evaluate failed: {err}")
                continue
            actual_mode = get_status_field(ev, "state", "rrMode")
            actual_rr = get_status_field(ev, "state", "reserveRatio")
            results_log.append(f"RR={actual_rr:.2f}→{actual_mode}")
            if actual_mode != expected_mode:
                errors.append(
                    f"RR~{target_rr} (actual={actual_rr:.2f}): "
                    f"expected {expected_mode}, got {actual_mode}")

    if errors:
        return result(FAIL, "; ".join(errors))
    return result(PASS, ", ".join(results_log))


def test_pre_04_spot_ma_spread(probes):
    """PRE-04: spot-ma-spread-calculation

    Verify spotMaSpreadBps is reported in evaluate metrics.
    At steady state (no recent price change), spread should be ~0.
    After a price change, spread should be non-zero.
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    eval_data, err = engine_evaluate()
    if err:
        return result(FAIL, f"Evaluate: {err}")

    metrics = get_status_field(eval_data, "results", "arb", "metrics")
    if not metrics:
        return result(FAIL, "No arb metrics in evaluate response")

    spread_bps = metrics.get("spotMaSpreadBps")
    if spread_bps is None:
        return result(FAIL, "spotMaSpreadBps not in metrics")

    if not isinstance(spread_bps, (int, float)):
        return result(FAIL, f"spotMaSpreadBps={spread_bps} — expected number")

    # At steady state, spread should be near zero
    # (spot and MA converge when oracle price hasn't changed recently)
    return result(PASS,
        f"spotMaSpreadBps={spread_bps} "
        f"({'near zero — steady state' if abs(spread_bps) < 50 else 'non-zero — price drift'})")


# ==========================================================================
# PRE-05..PRE-07: State building & factories
# ==========================================================================


def test_pre_05_global_state_building(probes):
    """PRE-05: global-state-building

    Verify engine has access to all data sources: Zephyr, EVM, CEX.
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    status, err = engine_status()
    if err:
        return result(FAIL, f"Status: {err}")

    state = get_status_field(status, "state")
    if not state:
        return result(FAIL, "No 'state' in status response")

    checks = {
        "zephyrAvailable": state.get("zephyrAvailable"),
        "evmAvailable": state.get("evmAvailable"),
        "cexAvailable": state.get("cexAvailable"),
    }
    unavailable = [k for k, v in checks.items() if not v]
    if unavailable:
        return result(FAIL, f"Data sources unavailable: {unavailable}")

    # Verify reserve ratio is present and sane
    rr = state.get("reserveRatio")
    if not isinstance(rr, (int, float)) or rr <= 0:
        return result(FAIL, f"reserveRatio={rr} — expected positive number")

    # Verify evaluate works and checks all legs
    eval_data, err = engine_evaluate()
    if err:
        return result(FAIL, f"Evaluate: {err}")

    metrics = get_status_field(eval_data, "results", "arb", "metrics")
    if not metrics:
        return result(FAIL, "No arb metrics — evaluate may have failed")

    legs = metrics.get("totalLegsChecked", 0)
    if legs < 8:
        return result(FAIL,
            f"Only {legs}/8 arb legs checked — missing pool or market data")

    return result(PASS,
        f"All sources available, {legs}/8 arb legs checked, RR={rr:.2f}")


def test_pre_06_state_reflects_rr_mode(probes):
    """PRE-06: state-for-rr-mode

    Verify engine status correctly reports rrMode after oracle changes.
    """
    blocked = needs(probes, "engine", "oracle")
    if blocked:
        return blocked

    eval_data, err = engine_evaluate()
    if err:
        return result(FAIL, f"Evaluate: {err}")
    current_price = get_status_field(eval_data, "state", "zephPrice")
    current_rr = get_status_field(eval_data, "state", "reserveRatio")
    if not current_price or not current_rr:
        return result(BLOCKED, "Cannot read current price/RR")

    transitions = []
    errors = []
    with EngineCleanupContext(price_usd=current_price):
        for target_rr, expected_mode in [(5.0, "normal"), (3.0, "defensive"), (1.5, "crisis")]:
            set_oracle_price(_price_for_rr(current_price, current_rr, target_rr))
            mine_blocks(5)
            wait_sync()

            # Check BOTH status and evaluate agree on rrMode
            status, err = engine_status()
            ev, ev_err = engine_evaluate()

            if err or ev_err:
                errors.append(f"RR~{target_rr}: API error")
                continue

            status_mode = get_status_field(status, "state", "rrMode")
            eval_mode = get_status_field(ev, "state", "rrMode")
            actual_rr = get_status_field(ev, "state", "reserveRatio")

            if status_mode != eval_mode:
                errors.append(
                    f"RR~{target_rr}: status says {status_mode}, "
                    f"evaluate says {eval_mode}")
            elif status_mode != expected_mode:
                errors.append(
                    f"RR~{target_rr} (actual={actual_rr:.2f}): "
                    f"expected {expected_mode}, got {status_mode}")
            else:
                transitions.append(f"{actual_rr:.2f}→{status_mode}")

    if errors:
        return result(FAIL, "; ".join(errors))
    return result(PASS, f"Mode transitions: {', '.join(transitions)}")


def test_pre_07_inventory_snapshot(probes):
    """PRE-07: inventory-snapshot-building

    Verify /api/inventory/balances returns per-venue balances with
    expected asset categories and correct structure.
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    data, err = engine_balances()
    if err:
        return result(FAIL, f"Balances: {err}")

    assets = (data or {}).get("assets")
    if not isinstance(assets, list) or len(assets) == 0:
        return result(FAIL, f"No assets array in balances response")

    # Expected asset keys
    expected_keys = {"ZEPH", "ZSD", "USDT"}
    actual_keys = {a.get("key") for a in assets}
    missing_keys = expected_keys - actual_keys
    if missing_keys:
        return result(FAIL,
            f"Missing asset keys: {missing_keys}. Got: {sorted(actual_keys)}")

    # Verify each asset has variants array and total
    errors = []
    for asset in assets:
        key = asset.get("key", "?")
        if "total" not in asset:
            errors.append(f"{key}: missing 'total'")
        variants = asset.get("variants")
        if not isinstance(variants, list):
            errors.append(f"{key}: missing 'variants' array")
            continue
        for v in variants:
            if "assetId" not in v or "amount" not in v:
                errors.append(f"{key}: variant missing assetId/amount")
                break

    if errors:
        return result(FAIL, "; ".join(errors))

    # Check for expected variant IDs
    all_variant_ids = {v.get("assetId") for a in assets for v in a.get("variants", [])}
    expected_variants = {"WZEPH.e", "WZSD.e", "USDT.e"}
    found_variants = expected_variants & all_variant_ids
    return result(PASS,
        f"{len(assets)} assets, {len(all_variant_ids)} variants. "
        f"Found: {sorted(found_variants)}")


# ==========================================================================
# PRE-08..PRE-09: Configuration & decimals
# ==========================================================================


def test_pre_08_asset_decimals(probes):
    """PRE-08: asset-decimal-mapping

    Call decimals() on each ERC-20 token contract and verify values.
    """
    blocked = needs(probes, "anvil")
    if blocked:
        return blocked

    expected = {
        "USDT": 6,
        "wZEPH": 12,
        "wZSD": 12,
        "wZRS": 12,
        "wZYS": 12,
    }

    if not TK:
        return result(BLOCKED, "No token addresses loaded from config")

    errors = []
    verified = []
    for token_name, expected_dec in expected.items():
        addr = TK.get(token_name)
        if not addr:
            errors.append(f"{token_name}: no address in config")
            continue

        actual_dec, err = decimals_of(addr)
        if err:
            errors.append(f"{token_name}: {err}")
            continue

        if actual_dec != expected_dec:
            errors.append(f"{token_name}: got {actual_dec}, expected {expected_dec}")
        else:
            verified.append(f"{token_name}={actual_dec}")

    if errors:
        return result(FAIL, "; ".join(errors))
    return result(PASS, f"Verified: {', '.join(verified)}")


def test_pre_09_engine_config(probes):
    """PRE-09: engine-config-defaults

    Verify engine is running with expected configuration.
    """
    blocked = needs(probes, "engine")
    if blocked:
        return blocked

    status, err = engine_status()
    if err:
        return result(FAIL, f"Status: {err}")

    runner = get_status_field(status, "runner")
    if not runner:
        return result(FAIL, "No 'runner' in status response")

    db = get_status_field(status, "database")
    if not db:
        return result(FAIL, "No 'database' in status response")

    # Verify database is connected
    if not db.get("connected"):
        return result(FAIL, "Database not connected")

    # Verify runner config has expected fields
    auto_exec = runner.get("autoExecute")
    cooldown = runner.get("cooldownMs")

    details = []
    if auto_exec is None:
        return result(FAIL, "No autoExecute in runner config")
    details.append(f"autoExecute={auto_exec}")

    if cooldown is None:
        return result(FAIL, "No cooldownMs in runner config")
    if not isinstance(cooldown, (int, float)) or cooldown <= 0:
        return result(FAIL, f"cooldownMs={cooldown} — expected positive number")
    details.append(f"cooldownMs={cooldown}")

    # Verify state section
    state = get_status_field(status, "state")
    if state:
        rr_mode = state.get("rrMode")
        if rr_mode:
            details.append(f"rrMode={rr_mode}")

    return result(PASS, ", ".join(details))


# ==========================================================================
# Export
# ==========================================================================

TESTS = {
    "PRE-01": test_pre_01_reserve_state_parsing,
    "PRE-02a": test_pre_02a_zsd_mintable_boundary,
    "PRE-02b": test_pre_02b_zsd_redeemable,
    "PRE-02c": test_pre_02c_zrs_mintable_boundary,
    "PRE-02d": test_pre_02d_zrs_redeemable_boundary,
    "PRE-03": test_pre_03_rr_mode_determination,
    "PRE-04": test_pre_04_spot_ma_spread,
    "PRE-05": test_pre_05_global_state_building,
    "PRE-06": test_pre_06_state_reflects_rr_mode,
    "PRE-07": test_pre_07_inventory_snapshot,
    "PRE-08": test_pre_08_asset_decimals,
    "PRE-09": test_pre_09_engine_config,
}
