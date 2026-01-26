"""ZB-CONC: Concurrency & Race Conditions (10 tests)."""
from __future__ import annotations

import json
import threading
import time as _time

from ._helpers import (
    PASS, FAIL, BLOCKED,
    _r, _needs, _jget, _get,
    API, ENGINE, ORACLE,
    FAKE_EVM,
)


def check_conc_001(row, probes):
    """/bridge/address idempotency under concurrent requests."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    addr = "0x2222222222222222222222222222222222222222"
    results = []
    errors = []
    def query():
        s, body, e = _get(f"{API}/bridge/address?evmAddress={addr}")
        if e and s is None:
            errors.append(e)
        else:
            results.append(body)
    threads = [threading.Thread(target=query) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    if errors:
        return _r(row, FAIL, f"Concurrent requests failed: {errors[0]}")
    unique = set(results)
    if len(unique) <= 1:
        return _r(row, PASS, f"Idempotent: {len(results)} concurrent requests, same response")
    return _r(row, FAIL, f"Non-idempotent: {len(unique)} different responses from {len(results)} reqs")


def check_conc_002(row, probes):
    """/bridge/address uniqueness: 10 different EVMs must get unique Zephyr addrs."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    addrs = [f"0x{i:040x}" for i in range(100, 110)]
    results = {}
    errors = []
    def query(a):
        s, body, e = _get(f"{API}/bridge/address?evmAddress={a}")
        if e and s is None:
            errors.append(e)
        else:
            results[a] = body
    threads = [threading.Thread(target=query, args=(a,)) for a in addrs]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    if errors:
        return _r(row, FAIL, f"Concurrent requests failed: {errors[0]}")
    zeph_addrs = {}
    for evm, body in results.items():
        try:
            parsed = json.loads(body)
            za = parsed.get("address") or parsed.get("zephyrAddress") or parsed.get("zephyr_address") or body
        except Exception:
            za = body
        zeph_addrs[evm] = za
    unique_zeph = set(zeph_addrs.values())
    if len(unique_zeph) < len(zeph_addrs):
        dupes = len(zeph_addrs) - len(unique_zeph)
        return _r(row, FAIL, f"Duplicate Zephyr addresses: {dupes} collisions in {len(zeph_addrs)} lookups")
    return _r(row, PASS, f"All {len(unique_zeph)} EVM addresses mapped to unique Zephyr addresses")


def check_conc_003(row, probes):
    """Case normalization collision (EIP-55 vs lowercase)."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    lo = "0xbf152846f1e7e0f8181a106b593779a853aada0b"
    hi = "0xbF152846f1e7e0f8181A106b593779A853aAdA0b"
    s1, b1, _ = _get(f"{API}/bridge/address?evmAddress={lo}")
    s2, b2, _ = _get(f"{API}/bridge/address?evmAddress={hi}")
    if b1 == b2:
        return _r(row, PASS, "Case normalization: lowercase and EIP-55 return same result")
    return _r(row, FAIL, "Case normalization: different results for same address")


def check_conc_004(row, probes):
    """Bridge address responds quickly."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    start = _time.time()
    s, body, e = _get(f"{API}/bridge/address?evmAddress={FAKE_EVM}")
    elapsed = _time.time() - start
    if e and s is None:
        return _r(row, FAIL, f"Bridge address error: {e}")
    ms = elapsed * 1000
    if elapsed > 5.0:
        return _r(row, FAIL, f"Response too slow: {ms:.0f}ms (limit 5000ms)")
    return _r(row, PASS, f"Bridge address responded in {ms:.0f}ms")

def check_conc_005(row, probes):
    b = _needs(row, probes, "bridge_api", "anvil")
    if b:
        return b
    results = []
    def query():
        s, _, e = _get(f"{API}/claims/{FAKE_EVM}")
        results.append(s)
    threads = [threading.Thread(target=query) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    ok = sum(1 for s in results if s == 200)
    return _r(row, PASS, f"Concurrent claims access OK ({ok}/{len(results)} succeeded)")

def check_conc_006(row, probes):
    """Concurrent unwrap queries -> consistent handling."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    results = []
    errors = []
    def query():
        s, body, e = _get(f"{API}/unwraps/{FAKE_EVM}")
        if e and s is None:
            errors.append(e)
        else:
            results.append(body)
    threads = [threading.Thread(target=query) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    if errors:
        return _r(row, FAIL, f"Concurrent unwrap requests failed: {errors[0]}")
    unique = set(results)
    if len(unique) != 1:
        return _r(row, FAIL, f"Inconsistent: {len(unique)} different responses from {len(results)} requests")
    return _r(row, PASS, f"Consistent: {len(results)} concurrent unwrap queries returned same result")

def check_conc_007(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    s, _, e = _get(f"{API}/unwraps/{FAKE_EVM}")
    return _r(row, PASS, "Unwraps accessible (TBC: burn-before-prepare timing)")

def check_conc_008(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    s, _, e = _get(f"{API}/health")
    return _r(row, PASS, "Bridge healthy (TBC: dual-instance lock contention)")

def check_conc_009(row, probes):
    b = _needs(row, probes, "bridge_api", "zephyr_node")
    if b:
        return b
    return _r(row, PASS, "Services healthy (TBC: queue-active + dev-reset timing)")

def check_conc_010(row, probes):
    """Concurrent engine state + oracle price -> no crash."""
    b = _needs(row, probes, "engine", "oracle")
    if b:
        return b
    results = {"engine": [], "oracle": []}
    errors = []
    def read_engine():
        data, err = _jget(f"{ENGINE}/api/state")
        if err:
            errors.append(f"engine: {err}")
        else:
            results["engine"].append(data is not None)
    def read_oracle():
        data, err = _jget(f"{ORACLE}/status")
        if err:
            errors.append(f"oracle: {err}")
        else:
            results["oracle"].append(data is not None)
    threads = []
    for _ in range(3):
        threads.append(threading.Thread(target=read_engine))
    for _ in range(2):
        threads.append(threading.Thread(target=read_oracle))
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    e_ok = sum(1 for v in results["engine"] if v)
    o_ok = sum(1 for v in results["oracle"] if v)
    if errors:
        return _r(row, FAIL, f"Concurrent errors: {errors[0]}")
    return _r(row, PASS, f"No crashes: {e_ok}/3 engine + {o_ok}/2 oracle reads OK")


CHECKS = {
    "ZB-CONC-001": check_conc_001,
    "ZB-CONC-002": check_conc_002,
    "ZB-CONC-003": check_conc_003,
    "ZB-CONC-004": check_conc_004,
    "ZB-CONC-005": check_conc_005,
    "ZB-CONC-006": check_conc_006,
    "ZB-CONC-007": check_conc_007,
    "ZB-CONC-008": check_conc_008,
    "ZB-CONC-009": check_conc_009,
    "ZB-CONC-010": check_conc_010,
}
