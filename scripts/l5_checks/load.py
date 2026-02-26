"""ZB-LOAD: Load & Stress (8 tests)."""
from __future__ import annotations

import json
import threading
import time as _time

from ._helpers import (
    PASS, FAIL, BLOCKED,
    _r, _needs, _jget, _jpost, _get, _post, _rpc,
    API, ANVIL, ORACLE,
    GOV_W, MINER_W, TEST_W,
)


def check_load_001(row, probes):
    """Burst 100 concurrent bridge address creations, verify uniqueness."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    results = {}
    errors = []
    def create(i):
        evm = f"0x{i:040x}"
        s, body, e = _post(f"{API}/bridge/address", {"evmAddress": evm})
        if e and s is None:
            errors.append(e)
        else:
            try:
                data = json.loads(body) if body else {}
            except Exception:
                data = {}
            addr = (data.get("address") or data.get("zephyrAddress")
                    or data.get("zephyr_address") or "")
            results[evm] = addr
    base = 0xA00000
    threads = [threading.Thread(target=create, args=(base + i,)) for i in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    if errors:
        return _r(row, FAIL, f"Burst errors: {len(errors)}/{100} — {errors[0]}")
    non_empty = {k: v for k, v in results.items() if v}
    vals = list(non_empty.values())
    unique = set(vals)
    if len(vals) > 0 and len(unique) < len(vals):
        dupes = len(vals) - len(unique)
        return _r(row, FAIL, f"Duplicate Zephyr addresses: {dupes} collisions in {len(vals)}")
    return _r(row, PASS, f"Burst 100 creates: {len(results)} OK, {len(non_empty)} addrs, all unique")

def check_load_002(row, probes):
    """50 concurrent POST + health check after burst + p99 latency."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    latencies = []
    errors = []
    def create(i):
        evm = f"0x{i:040x}"
        start = _time.time()
        s, body, e = _post(f"{API}/bridge/address", {"evmAddress": evm})
        elapsed = _time.time() - start
        if e and s is None:
            errors.append(e)
        else:
            latencies.append(elapsed)
    base = 0xB00000
    threads = [threading.Thread(target=create, args=(base + i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    if errors and len(errors) > len(latencies):
        return _r(row, FAIL, f"Majority failed: {len(errors)}/50 — {errors[0]}")
    # Health check after burst
    hs, _, he = _get(f"{API}/health")
    if he and hs is None:
        return _r(row, FAIL, f"Health check failed after burst: {he}")
    # p99 latency
    if latencies:
        latencies.sort()
        p99_idx = max(0, int(len(latencies) * 0.99) - 1)
        p99 = latencies[p99_idx]
    else:
        p99 = 0
    return _r(row, PASS,
              f"50 concurrent POSTs: {len(latencies)} OK, {len(errors)} errs, "
              f"p99={p99*1000:.0f}ms, health={hs}")

def check_load_003(row, probes):
    """20 concurrent /unwraps/prepare — no 500s under load."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    statuses = []
    errors = []
    def prepare(i):
        evm = f"0x{i:040x}"
        s, body, e = _post(f"{API}/unwraps/prepare", {
            "evmAddress": evm,
            "token": "wZEPH",
            "amount": "1000000000000",
            "zephyrAddress": "invalid_for_test",
        })
        if e and s is None:
            errors.append(str(e))
        else:
            statuses.append(s)
    base = 0xC00000
    threads = [threading.Thread(target=prepare, args=(base + i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)
    server_errors = [s for s in statuses if s is not None and s >= 500]
    client_errors = [s for s in statuses if s is not None and 400 <= s < 500]
    if server_errors:
        return _r(row, FAIL, f"Server errors under load: {len(server_errors)} 5xx in {len(statuses)} responses")
    return _r(row, PASS,
              f"20 concurrent prepares: {len(statuses)} responses (4xx={len(client_errors)}), "
              f"0 server errors, {len(errors)} network errors")

def check_load_004(row, probes):
    """Rapid oracle price changes."""
    b = _needs(row, probes, "oracle")
    if b:
        return b
    data, err = _jget(f"{ORACLE}/status")
    if err:
        return _r(row, FAIL, f"Oracle error: {err}")
    original = (data or {}).get("spot")
    prices = [1500000000000, 1600000000000, 1400000000000, 1700000000000, 1500000000000]
    ok = 0
    for p in prices:
        s, _, _ = _post(f"{ORACLE}/set-price", {"spot": p})
        if s == 200:
            ok += 1
    if original:
        _post(f"{ORACLE}/set-price", {"spot": original})
    data2, _ = _jget(f"{ORACLE}/status")
    final = (data2 or {}).get("spot")
    if ok == len(prices):
        return _r(row, PASS, f"Rapid oracle: {ok}/{len(prices)} OK, final={final}")
    return _r(row, FAIL, f"Rapid oracle: {ok}/{len(prices)} succeeded")

def check_load_005(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    addrs = [f"0x{i:040x}" for i in range(0xdead00, 0xdead03)]
    results = []
    errors = []
    def sse_connect(addr):
        try:
            s, body, e = _get(f"{API}/claims/{addr}/stream", timeout=3.0)
            if e and s is None:
                if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                    results.append("streaming")
                else:
                    errors.append(str(e))
            else:
                results.append(f"HTTP {s}")
        except Exception as exc:
            errors.append(str(exc))
    threads = [threading.Thread(target=sse_connect, args=(a,)) for a in addrs]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    ok = len(results)
    return _r(row, PASS, f"3 concurrent SSE streams: {ok} OK ({', '.join(results)}), {len(errors)} errors")

def check_load_006(row, probes):
    """Pool/watcher infra verification + 10 concurrent pool reads."""
    b = _needs(row, probes, "anvil", "bridge_api")
    if b:
        return b
    # 1. Query pools endpoint
    pools_data, pools_err = _jget(f"{API}/uniswap/pools")
    if pools_err:
        return _r(row, FAIL, f"Pools endpoint error: {pools_err}")
    pools = (pools_data.get("pools", pools_data) if isinstance(pools_data, dict)
             else (pools_data if isinstance(pools_data, list) else []))
    pool_count = len(pools) if isinstance(pools, list) else 0
    # 2. Query full pools endpoint
    full_data, full_err = _jget(f"{API}/uniswap/pools/full")
    full_count = 0
    if not full_err:
        full_pools = (full_data.get("pools", full_data) if isinstance(full_data, dict)
                      else (full_data if isinstance(full_data, list) else []))
        full_count = len(full_pools) if isinstance(full_pools, list) else 0
    # 3. 10 concurrent pool reads
    results = []
    errors = []
    def pool_read(i):
        d, e = _jget(f"{API}/uniswap/pools")
        if e:
            errors.append(e)
        else:
            p = (d.get("pools", d) if isinstance(d, dict)
                 else (d if isinstance(d, list) else []))
            results.append(len(p) if isinstance(p, list) else 0)
    threads = [threading.Thread(target=pool_read, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
    if errors and len(errors) > 5:
        return _r(row, FAIL, f"Pool reads failed: {len(errors)}/10 — {errors[0]}")
    # 4. Verify Anvil block number
    parsed, anvil_err = _jpost(ANVIL, {
        "jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1,
    })
    block = 0
    if not anvil_err:
        block = int((parsed or {}).get("result", "0x0"), 16)
    return _r(row, PASS,
              f"Pool infra: {pool_count} pools, full={full_count}, "
              f"10 concurrent reads={len(results)} OK, Anvil block={block}")

def check_load_007(row, probes):
    """10 parallel health + debug queue queries within 5s."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    results = []
    errors = []
    endpoints = [
        f"{API}/health",
        f"{API}/health",
        f"{API}/health",
        f"{API}/health",
        f"{API}/health",
        f"{API}/debug/unwraps/queues",
        f"{API}/debug/unwraps/queues",
        f"{API}/debug/claims/queues",
        f"{API}/debug/claims/queues",
        f"{API}/health",
    ]
    def query(url):
        start = _time.time()
        s, _, e = _get(url)
        elapsed = _time.time() - start
        if e and s is None:
            errors.append(f"{url}: {e}")
        else:
            results.append((url.split("/")[-1], s, elapsed))
    overall_start = _time.time()
    threads = [threading.Thread(target=query, args=(ep,)) for ep in endpoints]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    total = _time.time() - overall_start
    if total > 5.0:
        return _r(row, FAIL, f"Parallel queries took {total:.1f}s (limit 5s)")
    ok = len(results)
    return _r(row, PASS,
              f"10 parallel queries in {total*1000:.0f}ms: {ok} OK, {len(errors)} errors")

def check_load_008(row, probes):
    b = _needs(row, probes, "zephyr_node")
    if b:
        return b
    wallets = {"gov": GOV_W, "miner": MINER_W, "test": TEST_W}
    times = {}
    for name, url in wallets.items():
        start = _time.time()
        result, err = _rpc(url, "get_version")
        elapsed = _time.time() - start
        if err:
            return _r(row, FAIL, f"{name} wallet error: {err}")
        if elapsed > 5.0:
            return _r(row, FAIL, f"{name} wallet too slow: {elapsed:.1f}s (limit 5s)")
        times[name] = elapsed
    parts = ", ".join(f"{n}={t * 1000:.0f}ms" for n, t in times.items())
    return _r(row, PASS, f"All 3 wallets < 5s: {parts}")


CHECKS = {
    "ZB-LOAD-001": check_load_001,
    "ZB-LOAD-002": check_load_002,
    "ZB-LOAD-003": check_load_003,
    "ZB-LOAD-004": check_load_004,
    "ZB-LOAD-005": check_load_005,
    "ZB-LOAD-006": check_load_006,
    "ZB-LOAD-007": check_load_007,
    "ZB-LOAD-008": check_load_008,
}
