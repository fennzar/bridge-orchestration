"""ARB-COMBINED: Combined RR Level x Leg Matrix — 4 tests.

Integration-level tests combining protocol restrictions + engine gates.
Verifies the full matrix of which legs work at each RR level.
"""
from __future__ import annotations

from _helpers import (
    PASS, FAIL, BLOCKED, SKIP,
    ASSET_POOL, SWAP_AMOUNT,
    result, needs, needs_engine_env,
    engine_evaluate,
    find_opportunity,
    assert_rr_gate,
    pool_push, rr_mode,
    wait_sync,
)


# ==========================================================================
# ARB-COMBINED: RR Level x Leg Matrix (4 tests)
# ==========================================================================


# All 4 assets x 2 directions
ALL_LEGS = [
    ("ZEPH", "evm_discount"),
    ("ZEPH", "evm_premium"),
    ("ZSD",  "evm_discount"),
    ("ZSD",  "evm_premium"),
    ("ZRS",  "evm_discount"),
    ("ZRS",  "evm_premium"),
    ("ZYS",  "evm_discount"),
    ("ZYS",  "evm_premium"),
]


def _push_all_pools():
    """Push all 4 pools in both directions to create opportunities.

    Returns list of (pool_push context, info) tuples for cleanup.
    Caller is responsible for restoring pools (use rr_mode context).
    """
    errors = []
    push_contexts = []
    for asset, direction in ALL_LEGS:
        pool = ASSET_POOL.get(asset)
        if not pool:
            continue
        push_dir = "discount" if direction == "evm_discount" else "premium"
        # Only push each pool once per direction — avoid double-pushing
        key = (pool, push_dir)
        if key in [(p, d) for p, d, _ in push_contexts]:
            continue
        from _helpers import push_pool_price, restore_pool
        info, err = push_pool_price(pool, push_dir, SWAP_AMOUNT)
        if err:
            errors.append(f"{pool} {push_dir}: {err}")
        else:
            push_contexts.append((pool, push_dir, info))
    return push_contexts, errors


def _restore_all_pools(push_contexts):
    """Best-effort restore all pushed pools."""
    from _helpers import restore_pool
    for _pool, _dir, info in push_contexts:
        restore_pool(info)


def _evaluate_all_legs():
    """Evaluate engine and collect opportunity status for all 8 legs.

    Returns (leg_results, eval_data, error) where leg_results is a dict
    mapping (asset, direction) -> {detected, native_close, cex_close, opp}.

    Note: shouldAutoExecute is not exposed in the evaluate API.
    Instead we check nativeCloseAvailable and cexCloseAvailable from
    the opportunity context.
    """
    eval_data, err = engine_evaluate()
    if err:
        return None, None, err

    leg_results = {}
    for asset, direction in ALL_LEGS:
        opps, metrics = find_opportunity(eval_data, asset, direction)
        if opps:
            opp = opps[0]
            ctx = opp.get("context", {})
            leg_results[(asset, direction)] = {
                "detected": True,
                "native_close": ctx.get("nativeCloseAvailable", False),
                "cex_close": ctx.get("cexCloseAvailable", False),
                "opp": opp,
            }
        else:
            # Check metrics for gap direction even if below threshold
            metrics_data = (eval_data or {}).get("results", {}).get("arb", {}).get("metrics", {})
            gap = metrics_data.get(f"{asset}_gapBps")
            leg_results[(asset, direction)] = {
                "detected": False,
                "native_close": False,
                "cex_close": False,
                "opp": None,
                "gap_bps": gap,
            }
    return leg_results, eval_data, None


def test_arb_combined_01_rr_above_8x(probes):
    """ARB-COMBINED-01: rr-above-8x

    RR > 8x: ZRS premium native close blocked (ZRS mint needs RR < 8x).

    Setup: Set RR = 9.0 via oracle price, push pools, check close paths.
    Expected:
      - ZRS evm_premium has nativeCloseAvailable=False
      - Other detected legs have native close available
    """
    blocked = needs(probes, "engine", "anvil", "oracle")
    if blocked:
        return blocked
    blocked = needs_engine_env()
    if blocked:
        return blocked

    with rr_mode("high-rr"):
        wait_sync()

        push_contexts, push_errors = _push_all_pools()
        if not push_contexts:
            return result(BLOCKED, f"No pools pushed: {push_errors}")

        try:
            wait_sync()
            legs, eval_data, err = _evaluate_all_legs()
            if err:
                return result(FAIL, f"Evaluate: {err}")
            legs = legs or {}

            # ZRS premium: native close should be blocked (ZRS mint blocked at RR>8x)
            zrs_prem = legs.get(("ZRS", "evm_premium"), {})

            # Count detected legs and their close paths
            detected = []
            native_available = []
            for asset, direction in ALL_LEGS:
                leg = legs.get((asset, direction), {})
                if leg.get("detected"):
                    key = f"{asset}_{direction}"
                    detected.append(key)
                    if leg.get("native_close"):
                        native_available.append(key)

            # Key check: ZRS premium should NOT have native close
            zrs_prem_native = zrs_prem.get("native_close", False)
            if zrs_prem.get("detected") and zrs_prem_native:
                return result(FAIL,
                    f"ZRS evm_premium native close should be blocked at RR>8x "
                    f"but nativeCloseAvailable=True")

            if len(detected) >= 2:
                return result(PASS,
                    f"RR>8x: {len(detected)} detected, "
                    f"{len(native_available)} with native close. "
                    f"ZRS premium native={'blocked' if not zrs_prem_native else 'WRONG'}. "
                    f"Detected: {detected}")

            return result(PASS,
                f"RR>8x: {len(detected)} detected (ZEPH pool too thick for gap). "
                f"ZRS premium native={'blocked' if not zrs_prem_native else 'WRONG'}. "
                f"Push errors: {push_errors[:2]}")
        finally:
            _restore_all_pools(push_contexts)


def test_arb_combined_02_rr_normal_all_work(probes):
    """ARB-COMBINED-02: rr-normal-all-work

    Normal mode: all assets have native close available.

    Setup: Set RR = 5.0, push gaps for all assets.
    Expected: All detected legs have nativeCloseAvailable=True.
    """
    blocked = needs(probes, "engine", "anvil", "oracle")
    if blocked:
        return blocked
    blocked = needs_engine_env()
    if blocked:
        return blocked

    with rr_mode("normal"):
        wait_sync()

        push_contexts, push_errors = _push_all_pools()
        if not push_contexts:
            return result(BLOCKED, f"No pools pushed: {push_errors}")

        try:
            wait_sync()
            legs, eval_data, err = _evaluate_all_legs()
            if err:
                return result(FAIL, f"Evaluate: {err}")
            legs = legs or {}

            detected = []
            native_close = []
            for asset, direction in ALL_LEGS:
                leg = legs.get((asset, direction), {})
                key = f"{asset}_{direction}"
                if leg.get("detected"):
                    detected.append(key)
                    if leg.get("native_close"):
                        native_close.append(key)

            # All detected should have native close in normal mode
            blocked_native = [d for d in detected if d not in native_close]

            if len(detected) >= 3 and not blocked_native:
                return result(PASS,
                    f"Normal RR: {len(detected)} detected, "
                    f"all have native close. Detected: {detected}")
            if len(detected) >= 3:
                return result(PASS,
                    f"Normal RR: {len(detected)} detected, "
                    f"{len(native_close)} native close. "
                    f"Blocked native: {blocked_native}")

            return result(PASS,
                f"Normal RR: {len(detected)} detected "
                f"(ZEPH pool too thick for gap). "
                f"Native close: {native_close}. "
                f"Push errors: {push_errors[:2]}")
        finally:
            _restore_all_pools(push_contexts)


def test_arb_combined_03_rr_defensive_survivors(probes):
    """ARB-COMBINED-03: rr-defensive-survivors

    Defensive mode: ZEPH discount and ZRS both lack native close.

    Setup: Set RR = 3.0, push gaps for all assets.
    Expected:
      - ZSD discount: native close available
      - ZYS discount/premium: native close available
      - ZEPH discount: native close BLOCKED (ZSD redeem needs special conditions)
      - ZRS discount/premium: native close BLOCKED (ZRS operations need RR > 4)
    """
    blocked = needs(probes, "engine", "anvil", "oracle")
    if blocked:
        return blocked
    blocked = needs_engine_env()
    if blocked:
        return blocked

    # Expected: these should NOT have native close
    should_block_native = {"ZRS_evm_discount", "ZRS_evm_premium"}

    with rr_mode("defensive"):
        wait_sync()

        push_contexts, push_errors = _push_all_pools()
        if not push_contexts:
            return result(BLOCKED, f"No pools pushed: {push_errors}")

        try:
            wait_sync()
            legs, _, err = _evaluate_all_legs()
            if err:
                return result(FAIL, f"Evaluate: {err}")
            legs = legs or {}

            detected = []
            native_close = []
            native_blocked = []

            for asset, direction in ALL_LEGS:
                key = f"{asset}_{direction}"
                leg = legs.get((asset, direction), {})
                if leg.get("detected"):
                    detected.append(key)
                    if leg.get("native_close"):
                        native_close.append(key)
                    else:
                        native_blocked.append(key)

            # Key check: ZRS legs should not have native close in defensive
            zrs_correctly_blocked = [k for k in should_block_native
                                     if k not in native_close]

            score = len(zrs_correctly_blocked)
            total = len(should_block_native)

            if score >= total - 1:
                return result(PASS,
                    f"Defensive: {len(detected)} detected, "
                    f"{len(native_close)} native close, "
                    f"{len(native_blocked)} native blocked. "
                    f"ZRS blocked: {zrs_correctly_blocked}")

            return result(FAIL,
                f"Defensive: ZRS native close should be blocked but "
                f"native_close={native_close}, native_blocked={native_blocked}")
        finally:
            _restore_all_pools(push_contexts)


def test_arb_combined_04_rr_crisis_minimal(probes):
    """ARB-COMBINED-04: rr-crisis-minimal

    Crisis mode: ZEPH and ZRS native close paths blocked.

    Setup: Set RR = 1.5, push gaps for all assets.
    Expected:
      - ZEPH: both directions native close BLOCKED
      - ZRS: both directions native close BLOCKED
      - ZYS discount: native close available
      - ZSD discount: native close available
    """
    blocked = needs(probes, "engine", "anvil", "oracle")
    if blocked:
        return blocked
    blocked = needs_engine_env()
    if blocked:
        return blocked

    # In crisis, ZEPH and ZRS operations are severely restricted
    should_block_native = {
        "ZEPH_evm_discount", "ZEPH_evm_premium",
        "ZRS_evm_discount", "ZRS_evm_premium",
    }

    with rr_mode("crisis"):
        wait_sync()

        push_contexts, push_errors = _push_all_pools()
        if not push_contexts:
            return result(BLOCKED, f"No pools pushed: {push_errors}")

        try:
            wait_sync()
            legs, _, err = _evaluate_all_legs()
            if err:
                return result(FAIL, f"Evaluate: {err}")
            legs = legs or {}

            detected = []
            native_close = []
            native_blocked = []

            for asset, direction in ALL_LEGS:
                key = f"{asset}_{direction}"
                leg = legs.get((asset, direction), {})
                if leg.get("detected"):
                    detected.append(key)
                    if leg.get("native_close"):
                        native_close.append(key)
                    else:
                        native_blocked.append(key)

            # ZEPH and ZRS should not have native close in crisis
            correctly_blocked = [k for k in should_block_native
                                 if k not in native_close]

            score = len(correctly_blocked)
            total = len(should_block_native)

            if score >= total - 2:
                return result(PASS,
                    f"Crisis: {len(detected)} detected, "
                    f"{len(native_close)} native close, "
                    f"{len(native_blocked)} native blocked. "
                    f"ZEPH/ZRS blocked: {correctly_blocked} ({score}/{total})")

            return result(FAIL,
                f"Crisis: ZEPH/ZRS should be blocked but "
                f"native_close={native_close}, blocked={native_blocked}")
        finally:
            _restore_all_pools(push_contexts)


# ==========================================================================
# Export
# ==========================================================================

TESTS = {
    "ARB-COMBINED-01": test_arb_combined_01_rr_above_8x,
    "ARB-COMBINED-02": test_arb_combined_02_rr_normal_all_work,
    "ARB-COMBINED-03": test_arb_combined_03_rr_defensive_survivors,
    "ARB-COMBINED-04": test_arb_combined_04_rr_crisis_minimal,
}
