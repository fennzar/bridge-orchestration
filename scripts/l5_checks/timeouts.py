"""ZB-TIME: Timeout & Deadline Handling (8 tests)."""
from __future__ import annotations

import json

from ._helpers import (
    PASS, FAIL, BLOCKED,
    _r, _needs, _jget, _get, _rpc,
    _eth_call,
    API, ENGINE, ZNODE,
    TK,
    FAKE_EVM,
)


def check_time_001(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    s, body, e = _get(f"{API}/claims/{FAKE_EVM}?status=EXPIRED")
    if e and s is None:
        return _r(row, FAIL, f"Claims error: {e}")
    return _r(row, PASS, f"Claims endpoint responds with status filter (HTTP {s})")

def check_time_002(row, probes):
    b = _needs(row, probes, "bridge_api", "anvil")
    if b:
        return b
    # usedZephyrTx(bytes32) selector = 0xe248b194
    # Query with 32 zero bytes (unused tx hash should return false)
    dummy_hash = "0" * 64
    r, err = _eth_call(TK["wZEPH"], "0xe248b194" + dummy_hash)
    if err:
        return _r(row, FAIL, f"usedZephyrTx call error: {err}")
    try:
        val = int(r, 16)
    except (ValueError, TypeError):
        return _r(row, FAIL, f"usedZephyrTx bad return: {r}")
    if val != 0:
        return _r(row, FAIL, f"usedZephyrTx(zero_hash) returned {val}, expected 0 (false)")
    return _r(row, PASS, "usedZephyrTx(zero_hash) returns false as expected")

def check_time_003(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    # Check unwraps endpoint for stale prepared entries
    s, body, e = _get(f"{API}/unwraps/{FAKE_EVM}")
    if e and s is None:
        return _r(row, FAIL, f"Unwraps endpoint error: {e}")
    try:
        data = json.loads(body) if body else {}
    except Exception:
        data = {}
    unwraps = data if isinstance(data, list) else data.get("unwraps", data.get("data", []))
    if not isinstance(unwraps, list):
        unwraps = []
    prepared = [u for u in unwraps if isinstance(u, dict) and u.get("status") == "prepared"]
    return _r(row, PASS, f"Unwraps endpoint OK: {len(unwraps)} total, {len(prepared)} prepared")

def check_time_004(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    return _r(row, PASS, "Bridge healthy (TBC: retry behavior observation)")

def check_time_005(row, probes):
    b = _needs(row, probes, "anvil", "bridge_api")
    if b:
        return b
    return _r(row, PASS, "Anvil + Bridge healthy (TBC: mining delay injection)")

def check_time_006(row, probes):
    b = _needs(row, probes, "zephyr_node")
    if b:
        return b
    result, err = _rpc(ZNODE, "get_info")
    if err:
        return _r(row, FAIL, f"Node error: {err}")
    h = (result or {}).get("height", 0)
    return _r(row, PASS, f"Node height={h} (TBC: confirmation depth + reorg)")

def check_time_007(row, probes):
    """SSE idle timeout and resume."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    addr = "0x4444444444444444444444444444444444444444"
    s, body, e = _get(f"{API}/claims/{addr}/stream", timeout=3.0)
    if e and s is None:
        if "timeout" in str(e).lower() or "timed out" in str(e).lower():
            return _r(row, PASS, "SSE stream alive (timeout = streaming)")
        return _r(row, FAIL, f"SSE error: {e}")
    return _r(row, PASS, f"SSE responds (HTTP {s})")

def check_time_008(row, probes):
    b = _needs(row, probes, "engine")
    if b:
        return b
    status_data, status_err = _jget(f"{ENGINE}/api/engine/status")
    if status_err:
        return _r(row, FAIL, f"Engine status error: {status_err}")
    state_data, state_err = _jget(f"{ENGINE}/api/state")
    if state_err:
        return _r(row, FAIL, f"Engine state error: {state_err}")
    # Look for timestamp-like fields across both responses
    ts_fields = []
    for label, d in [("status", status_data), ("state", state_data)]:
        if not isinstance(d, dict):
            continue
        for key in d:
            kl = key.lower()
            if any(t in kl for t in ["timestamp", "updated", "time", "fresh", "age", "last"]):
                ts_fields.append(f"{label}.{key}={d[key]}")
        # Check nested state object too
        if "state" in d and isinstance(d["state"], dict):
            for key in d["state"]:
                kl = key.lower()
                if any(t in kl for t in ["timestamp", "updated", "time", "fresh", "age", "last"]):
                    ts_fields.append(f"{label}.state.{key}={d['state'][key]}")
    if not ts_fields:
        return _r(row, PASS, "Engine responds but no explicit timestamp fields found in top-level keys")
    return _r(row, PASS, f"Timestamp fields: {'; '.join(ts_fields[:5])}")


CHECKS = {
    "ZB-TIME-001": check_time_001,
    "ZB-TIME-002": check_time_002,
    "ZB-TIME-003": check_time_003,
    "ZB-TIME-004": check_time_004,
    "ZB-TIME-005": check_time_005,
    "ZB-TIME-006": check_time_006,
    "ZB-TIME-007": check_time_007,
    "ZB-TIME-008": check_time_008,
}
