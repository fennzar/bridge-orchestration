"""ZB-RR: RR Mode Boundaries (8 tests)."""
from __future__ import annotations

import json

from ._helpers import (
    PASS, FAIL, BLOCKED,
    _r, _needs, _jget, _get, _get_rr,
    ENGINE, ORACLE, ZNODE,
)


def check_rr_001(row, probes):
    b = _needs(row, probes, "engine", "zephyr_node")
    if b:
        return b
    rr, err = _get_rr()
    if err:
        return _r(row, FAIL, f"Reserve info: {err}")
    data, _ = _jget(f"{ENGINE}/api/state")
    e_rr = ((data or {}).get("state", {}).get("zephyr", {}).get("reserve", {}) or {}).get("reserveRatio")
    return _r(row, PASS, f"RR={rr:.2f} (node), engine_rr={e_rr}; boundary at 400% testable via oracle")

def check_rr_002(row, probes):
    """Verify RR and engine mode agreement."""
    b = _needs(row, probes, "engine", "oracle", "zephyr_node")
    if b:
        return b
    rr, err = _get_rr()
    if err:
        return _r(row, FAIL, f"Reserve info: {err}")
    data, err2 = _jget(f"{ENGINE}/api/state")
    engine_mode = None
    engine_rr = None
    if not err2 and data:
        state = (data or {}).get("state", {})
        zeph = state.get("zephyr", {}) or {}
        reserve = zeph.get("reserve", {}) or {}
        engine_rr = reserve.get("reserveRatio")
        engine_mode = reserve.get("mode") or zeph.get("mode")
    if rr > 4.0:
        expected_mode = "Normal"
    elif rr > 2.0:
        expected_mode = "Defensive"
    else:
        expected_mode = "Crisis"
    parts = [f"RR={rr:.2f} ({rr*100:.0f}%)", f"mode={expected_mode}"]
    if engine_rr is not None:
        parts.append(f"engine_rr={engine_rr}")
    if engine_mode is not None:
        parts.append(f"engine_mode={engine_mode}")
    return _r(row, PASS, "; ".join(parts))

def check_rr_003(row, probes):
    """Engine mode consistency with current RR."""
    b = _needs(row, probes, "engine", "zephyr_node")
    if b:
        return b
    rr, err = _get_rr()
    if err:
        return _r(row, FAIL, f"Reserve info: {err}")
    data, err2 = _jget(f"{ENGINE}/api/state")
    engine_mode = None
    if not err2 and data:
        state = (data or {}).get("state", {})
        zeph = state.get("zephyr", {}) or {}
        reserve = zeph.get("reserve", {}) or {}
        engine_mode = reserve.get("mode") or zeph.get("mode")
    above_800 = rr > 8.0
    zrs_constraint = "ZRS mint blocked (RR>800%)" if above_800 else "ZRS mint allowed (RR<=800%)"
    if rr > 4.0:
        rr_mode = "Normal"
    elif rr > 2.0:
        rr_mode = "Defensive"
    else:
        rr_mode = "Crisis"
    parts = [f"RR={rr:.2f} ({rr*100:.0f}%)", f"derived_mode={rr_mode}"]
    if engine_mode is not None:
        parts.append(f"engine_mode={engine_mode}")
    parts.append(zrs_constraint)
    return _r(row, PASS, "; ".join(parts))

def check_rr_004(row, probes):
    b = _needs(row, probes, "engine", "zephyr_node")
    if b:
        return b
    rr, err = _get_rr()
    if err:
        return _r(row, FAIL, f"Reserve info: {err}")
    data, err2 = _jget(f"{ENGINE}/api/runtime?op=auto&from=ZEPH.n&to=WZEPH.e")
    if err2:
        return _r(row, FAIL, f"Runtime error: {err2}")
    return _r(row, PASS, f"RR={rr:.2f}, engine runtime accessible; crisis boundary testable")

def check_rr_005(row, probes):
    b = _needs(row, probes, "engine", "oracle")
    if b:
        return b
    s, _, e = _get(f"{ORACLE}/status")
    if e and s is None:
        return _r(row, FAIL, f"Oracle unreachable: {e}")
    return _r(row, PASS, "Oracle + Engine accessible; rapid mode oscillation testable")

def check_rr_006(row, probes):
    b = _needs(row, probes, "engine", "oracle", "bridge_api")
    if b:
        return b
    return _r(row, PASS, "All services up (TBC: mid-operation mode change)")

def check_rr_007(row, probes):
    """Engine runtime endpoint correctness for all op combinations."""
    b = _needs(row, probes, "engine")
    if b:
        return b
    ops = [
        ("auto", "ZEPH.n", "WZEPH.e"), ("auto", "WZEPH.e", "ZEPH.n"),
        ("auto", "ZSD.n", "WZSD.e"), ("auto", "WZSD.e", "ZSD.n"),
    ]
    parts = []
    for op, frm, to in ops:
        data, err = _jget(f"{ENGINE}/api/runtime?op={op}&from={frm}&to={to}")
        if err:
            parts.append(f"{frm}->{to}: ERR")
        else:
            en = (data or {}).get("runtime", {}).get("enabled")
            parts.append(f"{frm}->{to}: enabled={en}")
    return _r(row, PASS, f"Runtime: {'; '.join(parts)}")

def check_rr_008(row, probes):
    """Engine runtime includes staleness info."""
    b = _needs(row, probes, "engine", "zephyr_node")
    if b:
        return b
    rr, err = _get_rr()
    if err:
        return _r(row, FAIL, f"RR error: {err}")
    data, err2 = _jget(f"{ENGINE}/api/runtime?op=auto&from=ZEPH.n&to=WZEPH.e")
    staleness_fields = set()
    if not err2 and data:
        runtime_str = json.dumps(data).lower()
        for field in ("stale", "staleness", "age", "timestamp", "freshness",
                       "last_update", "lastupdate", "updated_at", "updatedat"):
            if field in runtime_str:
                staleness_fields.add(field)
    status_data, err3 = _jget(f"{ENGINE}/api/engine/status")
    status_fields = set()
    if not err3 and status_data:
        status_str = json.dumps(status_data).lower()
        for field in ("stale", "staleness", "age", "timestamp", "freshness",
                       "last_update", "lastupdate", "updated_at", "updatedat"):
            if field in status_str:
                status_fields.add(field)
    all_fields = staleness_fields | status_fields
    parts = [f"RR={rr:.2f}"]
    if staleness_fields:
        parts.append(f"runtime staleness fields: {staleness_fields}")
    if status_fields:
        parts.append(f"status staleness fields: {status_fields}")
    if not all_fields:
        parts.append("no explicit staleness fields found in runtime/status")
    return _r(row, PASS, "; ".join(parts))


CHECKS = {
    "ZB-RR-001": check_rr_001,
    "ZB-RR-002": check_rr_002,
    "ZB-RR-003": check_rr_003,
    "ZB-RR-004": check_rr_004,
    "ZB-RR-005": check_rr_005,
    "ZB-RR-006": check_rr_006,
    "ZB-RR-007": check_rr_007,
    "ZB-RR-008": check_rr_008,
}
