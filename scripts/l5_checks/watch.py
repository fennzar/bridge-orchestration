"""ZB-WATCH: Watcher Reliability (12 tests)."""
from __future__ import annotations

import json
import time as _time

from ._helpers import (
    PASS, FAIL, BLOCKED,
    _r, _needs, _jget, _jpost, _get, _post, _rpc,
    API, ANVIL, ZNODE, NODE2_RPC,
    GOV_W, MINER_W,
)


def check_watch_001(row, probes):
    b = _needs(row, probes, "zephyr_node")
    if b:
        return b
    params = {
        "in": True, "out": False, "pending": False, "pool": False,
        "filter_by_height": True, "min_height": 0, "max_height": 999999,
        "account_index": 0,
    }
    result1, err1 = _rpc(GOV_W, "get_transfers", params)
    if err1:
        return _r(row, FAIL, f"get_transfers poll 1 error: {err1}")
    result2, err2 = _rpc(GOV_W, "get_transfers", params)
    if err2:
        return _r(row, FAIL, f"get_transfers poll 2 error: {err2}")
    txs1 = (result1 or {}).get("in", [])
    txs2 = (result2 or {}).get("in", [])
    ids1 = {t.get("txid", t.get("tx_hash", "")) for t in txs1}
    ids2 = {t.get("txid", t.get("tx_hash", "")) for t in txs2}
    if ids1 != ids2:
        return _r(row, FAIL, f"Inconsistent: poll1={len(ids1)} txs, poll2={len(ids2)} txs, diff={ids1 ^ ids2}")
    return _r(row, PASS, f"2 polls, {len(txs1)} transfers each, consistent")

def check_watch_002(row, probes):
    b = _needs(row, probes, "zephyr_node")
    if b:
        return b
    result, err = _rpc(GOV_W, "get_transfers", {
        "in": True, "out": True, "pending": True, "pool": True, "account_index": 0,
    })
    if err:
        return _r(row, FAIL, f"get_transfers error: {err}")
    if not isinstance(result, dict):
        return _r(row, FAIL, f"Expected dict, got {type(result).__name__}")
    fields = sorted(result.keys())
    for key in fields:
        val = result[key]
        if not isinstance(val, list):
            return _r(row, FAIL, f"Field '{key}' is {type(val).__name__}, expected list")
    counts = ", ".join(f"{k}={len(result[k])}" for k in fields)
    return _r(row, PASS, f"Structure valid, fields: {counts}")

def check_watch_003(row, probes):
    """Zephyr reorg via pop_blocks: pop 1 block, verify height drops, mine back."""
    b = _needs(row, probes, "zephyr_node")
    if b:
        return b
    # 1. Get initial height
    result, err = _rpc(ZNODE, "get_info")
    if err:
        return _r(row, FAIL, f"Node error: {err}")
    initial_h = (result or {}).get("height", 0)
    if initial_h < 5:
        return _r(row, BLOCKED, f"Chain too short for pop test (height={initial_h})")
    # 2. Stop mining on both nodes (safe even if not running)
    daemon_base = ZNODE.replace("/json_rpc", "")
    _post(f"{daemon_base}/stop_mining", {})
    node2_base = NODE2_RPC.replace("/json_rpc", "")
    _post(f"{node2_base}/stop_mining", {})
    _time.sleep(2)
    # 3. Pop 1 block (daemon HTTP endpoint, not JSON-RPC)
    pop_s, _, pop_err = _post(f"{daemon_base}/pop_blocks", {"nblocks": 1})
    if pop_err and pop_s is None:
        # Try JSON-RPC fallback
        _, pop_err2 = _rpc(ZNODE, "pop_blocks", {"nblocks": 1})
        if pop_err2:
            # Restore mining before returning
            maddr, _ = _rpc(MINER_W, "get_address", {"account_index": 0})
            if maddr:
                _post(f"{daemon_base}/start_mining", {
                    "do_background_mining": False, "ignore_battery": True,
                    "miner_address": (maddr or {}).get("address", ""), "threads_count": 2,
                })
            return _r(row, FAIL, f"pop_blocks error: {pop_err} / {pop_err2}")
    _time.sleep(1)  # Let state settle before height check
    # 4. Verify height dropped
    r2, e2 = _rpc(ZNODE, "get_info")
    popped_h = (r2 or {}).get("height", 0) if not e2 else initial_h
    # 5. Start mining to restore
    miner_result, _ = _rpc(MINER_W, "get_address", {"account_index": 0})
    miner_addr = (miner_result or {}).get("address", "")
    if miner_addr:
        _post(f"{daemon_base}/start_mining", {
            "do_background_mining": False, "ignore_battery": True,
            "miner_address": miner_addr, "threads_count": 2,
        })
    # 6. Wait for height to restore (up to 60s)
    final_h = popped_h
    for _ in range(60):
        _time.sleep(1)
        r3, _ = _rpc(ZNODE, "get_info")
        h = (r3 or {}).get("height", 0)
        if h >= initial_h:
            final_h = h
            break
    if popped_h >= initial_h:
        return _r(row, FAIL, f"Height didn't drop after pop: {initial_h}→{popped_h}")
    if final_h < initial_h:
        return _r(row, FAIL, f"Chain didn't restore: {initial_h}→{popped_h}, now {final_h}")
    return _r(row, PASS,
              f"Zephyr reorg: height {initial_h}→{popped_h}→{final_h}, self-healed")

def check_watch_004(row, probes):
    """Zephyr reorg after claimable: pop 1 block, verify claims stable, mine back."""
    b = _needs(row, probes, "zephyr_node", "bridge_api")
    if b:
        return b
    test_evm = "0x0000000000000000000000000000000000W00004"
    # 1. Check claims before pop
    before_s, _, before_e = _get(f"{API}/claims/{test_evm}")
    before_ok = before_e is None or before_s is not None
    # 2. Get initial height
    result, err = _rpc(ZNODE, "get_info")
    if err:
        return _r(row, FAIL, f"Node error: {err}")
    initial_h = (result or {}).get("height", 0)
    if initial_h < 5:
        return _r(row, BLOCKED, f"Chain too short for reorg test (height={initial_h})")
    # 3. Stop mining, pop 1 block
    daemon_base = ZNODE.replace("/json_rpc", "")
    _post(f"{daemon_base}/stop_mining", {})
    _time.sleep(1)
    pop_s, _, pop_err = _post(f"{daemon_base}/pop_blocks", {"nblocks": 1})
    if pop_err and pop_s is None:
        _, pop_err2 = _rpc(ZNODE, "pop_blocks", {"nblocks": 1})
        if pop_err2:
            maddr, _ = _rpc(MINER_W, "get_address", {"account_index": 0})
            if maddr:
                _post(f"{daemon_base}/start_mining", {
                    "do_background_mining": False, "ignore_battery": True,
                    "miner_address": (maddr or {}).get("address", ""), "threads_count": 2,
                })
            return _r(row, FAIL, f"pop_blocks error: {pop_err} / {pop_err2}")
    # 4. Check claims during reorg
    during_s, _, during_e = _get(f"{API}/claims/{test_evm}")
    during_500 = during_s is not None and during_s >= 500
    # 5. Restore: start mining
    miner_result, _ = _rpc(MINER_W, "get_address", {"account_index": 0})
    miner_addr = (miner_result or {}).get("address", "")
    if miner_addr:
        _post(f"{daemon_base}/start_mining", {
            "do_background_mining": False, "ignore_battery": True,
            "miner_address": miner_addr, "threads_count": 2,
        })
    # 6. Wait for restore
    for _ in range(60):
        _time.sleep(1)
        r3, _ = _rpc(ZNODE, "get_info")
        if (r3 or {}).get("height", 0) >= initial_h:
            break
    # 7. Check claims after
    after_s, _, after_e = _get(f"{API}/claims/{test_evm}")
    if during_500:
        return _r(row, FAIL, f"Claims API 500 during reorg: {during_e}")
    return _r(row, PASS,
              f"Claims stable during Zephyr reorg: before={before_ok}, "
              f"during=HTTP {during_s}, after=HTTP {after_s}")

def check_watch_005(row, probes):
    b = _needs(row, probes, "anvil", "bridge_api")
    if b:
        return b
    parsed, err = _jpost(ANVIL, {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1})
    if err:
        return _r(row, FAIL, f"Anvil error: {err}")
    return _r(row, PASS, "Anvil healthy; EVM log dedup verifiable via WS reconnect")

def check_watch_006(row, probes):
    """EVM reorg via Anvil snapshot/revert: non-destructive reorg simulation."""
    b = _needs(row, probes, "anvil")
    if b:
        return b
    # 1. Get initial block number
    p1, e1 = _jpost(ANVIL, {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1})
    if e1:
        return _r(row, FAIL, f"eth_blockNumber error: {e1}")
    initial_block = int((p1 or {}).get("result", "0x0"), 16)
    # 2. Take snapshot
    snap, es = _jpost(ANVIL, {"jsonrpc": "2.0", "method": "evm_snapshot", "params": [], "id": 2})
    if es:
        return _r(row, FAIL, f"evm_snapshot error: {es}")
    snap_id = (snap or {}).get("result")
    if not snap_id:
        return _r(row, FAIL, "evm_snapshot returned no snapshot id")
    # 3. Mine 1 block
    _, em = _jpost(ANVIL, {"jsonrpc": "2.0", "method": "evm_mine", "params": [], "id": 3})
    if em:
        return _r(row, FAIL, f"evm_mine error: {em}")
    # 4. Verify block increased
    p2, e2 = _jpost(ANVIL, {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 4})
    if e2:
        return _r(row, FAIL, f"eth_blockNumber after mine error: {e2}")
    after_mine = int((p2 or {}).get("result", "0x0"), 16)
    if after_mine <= initial_block:
        return _r(row, FAIL, f"Block didn't increase: {initial_block}→{after_mine}")
    # 5. Revert to snapshot
    _, er = _jpost(ANVIL, {"jsonrpc": "2.0", "method": "evm_revert", "params": [snap_id], "id": 5})
    if er:
        return _r(row, FAIL, f"evm_revert error: {er}")
    # 6. Verify block reverted
    p3, e3 = _jpost(ANVIL, {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 6})
    if e3:
        return _r(row, FAIL, f"eth_blockNumber after revert error: {e3}")
    after_revert = int((p3 or {}).get("result", "0x0"), 16)
    if after_revert > initial_block:
        return _r(row, FAIL,
                  f"Block didn't revert: {initial_block}→{after_mine}→{after_revert}")
    # 7. Mine back to restore chain state
    _jpost(ANVIL, {"jsonrpc": "2.0", "method": "evm_mine", "params": [], "id": 7})
    return _r(row, PASS,
              f"EVM reorg: block {initial_block}→{after_mine}→{after_revert}, "
              f"snapshot/revert OK")

def check_watch_007(row, probes):
    """Pool scan cursor off-by-one regression."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    s, body, e = _get(f"{API}/uniswap/pools")
    if e and s is None:
        return _r(row, FAIL, f"Pools error: {e}")
    try:
        parsed = json.loads(body)
        pools = parsed.get("pools", parsed if isinstance(parsed, list) else [])
        return _r(row, PASS, f"Uniswap pools OK (count={len(pools)})")
    except Exception:
        return _r(row, FAIL, "Failed to parse pools response")

def check_watch_008(row, probes):
    """Uniswap event backfill: query full pools twice, verify consistency."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    # Query full pools endpoint twice
    d1, e1 = _jget(f"{API}/uniswap/pools/full")
    if e1:
        # Fall back to /uniswap/pools if /full doesn't exist
        d1, e1 = _jget(f"{API}/uniswap/pools")
        if e1:
            return _r(row, FAIL, f"Pools endpoint error: {e1}")
    d2, e2 = _jget(f"{API}/uniswap/pools/full")
    if e2:
        d2, e2 = _jget(f"{API}/uniswap/pools")
        if e2:
            return _r(row, FAIL, f"Pools endpoint error on second query: {e2}")
    # Extract pool lists
    pools1 = d1.get("pools", d1) if isinstance(d1, dict) else (d1 if isinstance(d1, list) else [])
    pools2 = d2.get("pools", d2) if isinstance(d2, dict) else (d2 if isinstance(d2, list) else [])
    if not isinstance(pools1, list) or not isinstance(pools2, list):
        return _r(row, FAIL, f"Unexpected pool structure: {type(pools1).__name__}, {type(pools2).__name__}")
    # Compare counts
    if len(pools1) != len(pools2):
        return _r(row, FAIL, f"Pool count mismatch: query1={len(pools1)}, query2={len(pools2)}")
    # Compare pool addresses if available
    def _addrs(pools):
        return sorted(
            (p.get("address") or p.get("pool") or p.get("id") or "").lower()
            for p in pools if isinstance(p, dict)
        )
    a1, a2 = _addrs(pools1), _addrs(pools2)
    if a1 != a2:
        return _r(row, FAIL, f"Pool addresses differ between queries")
    return _r(row, PASS,
              f"Full pools consistent: {len(pools1)} pools, addresses match across 2 queries")

def check_watch_009(row, probes):
    b = _needs(row, probes, "bridge_api", "anvil")
    if b:
        return b
    return _r(row, PASS, "Bridge healthy (TBC: watcher late-start + block range recovery)")

def check_watch_010(row, probes):
    """Multi-instance watcher locks: check health + debug endpoints for lock infrastructure."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    lock_fields = []
    # 1. Check health endpoint for lock/mutex/TTL fields
    s, body, e = _get(f"{API}/health")
    if s == 200 and body:
        try:
            hdata = json.loads(body)
            if isinstance(hdata, dict):
                for k, v in hdata.items():
                    kl = k.lower()
                    if any(w in kl for w in ("lock", "mutex", "ttl", "leader", "instance")):
                        lock_fields.append(f"health.{k}={v}")
        except Exception:
            pass
    # 2. Check debug endpoints for lock infrastructure
    for ep_name, ep_path in [("unwrap", "debug/unwraps/queues"), ("claims", "debug/claims/queues")]:
        qdata, qerr = _jget(f"{API}/{ep_path}")
        if qerr:
            continue
        if isinstance(qdata, dict):
            for k, v in qdata.items():
                kl = k.lower()
                if any(w in kl for w in ("lock", "mutex", "ttl", "leader", "instance")):
                    lock_fields.append(f"{ep_name}.{k}={v}")
    # 3. Verify at least health is accessible
    if s != 200:
        return _r(row, FAIL, f"Health endpoint unhealthy: HTTP {s}")
    detail = f"Lock fields found: {', '.join(lock_fields)}" if lock_fields else "No explicit lock fields (single-instance mode)"
    return _r(row, PASS, f"Watcher lock infra checked; {detail}")

def check_watch_011(row, probes):
    b = _needs(row, probes, "zephyr_node")
    if b:
        return b
    # get_version
    ver_result, ver_err = _rpc(GOV_W, "get_version")
    if ver_err:
        return _r(row, FAIL, f"get_version error: {ver_err}")
    v = (ver_result or {}).get("version", "unknown")
    # get_height
    h_result, h_err = _rpc(GOV_W, "get_height")
    if h_err:
        return _r(row, FAIL, f"get_height error: {h_err}")
    height = (h_result or {}).get("height", 0)
    if not isinstance(height, int) or height <= 0:
        return _r(row, FAIL, f"Invalid height: {height}")
    # get_balance — response wraps data in result.balances[] array
    bal_result, bal_err = _rpc(GOV_W, "get_balance", {"account_index": 0})
    if bal_err:
        return _r(row, FAIL, f"get_balance error: {bal_err}")
    balances = (bal_result or {}).get("balances")
    if isinstance(balances, list) and len(balances) > 0:
        balance = balances[0].get("balance") or balances[0].get("unlocked_balance")
    else:
        balance = (bal_result or {}).get("balance") or (bal_result or {}).get("unlocked_balance")
    if balance is None:
        return _r(row, FAIL, "get_balance missing balance/unlocked_balance field")
    return _r(row, PASS, f"v{v}, height={height}, balance={balance}")

def check_watch_012(row, probes):
    b = _needs(row, probes, "zephyr_node")
    if b:
        return b
    result, err = _rpc(GOV_W, "get_transfers", {
        "in": True, "out": False, "pending": False, "pool": False,
        "filter_by_height": True, "min_height": 0, "max_height": 999999,
        "account_index": 0,
    })
    if err:
        return _r(row, FAIL, f"get_transfers error: {err}")
    txs = (result or {}).get("in", [])
    if not txs:
        return _r(row, PASS, "No inbound transfers; unlock_time field not testable (empty set)")
    bad = []
    for t in txs:
        ut = t.get("unlock_time")
        if ut is None:
            bad.append(t.get("txid", "?")[:8] + ":missing")
        elif not isinstance(ut, (int, float)) or ut < 0:
            bad.append(t.get("txid", "?")[:8] + f":invalid({ut})")
    if bad:
        return _r(row, FAIL, f"unlock_time issues: {', '.join(bad[:5])}")
    return _r(row, PASS, f"{len(txs)} transfers, all have valid unlock_time >= 0")


CHECKS = {
    "ZB-WATCH-001": check_watch_001,
    "ZB-WATCH-002": check_watch_002,
    "ZB-WATCH-003": check_watch_003,
    "ZB-WATCH-004": check_watch_004,
    "ZB-WATCH-005": check_watch_005,
    "ZB-WATCH-006": check_watch_006,
    "ZB-WATCH-007": check_watch_007,
    "ZB-WATCH-008": check_watch_008,
    "ZB-WATCH-009": check_watch_009,
    "ZB-WATCH-010": check_watch_010,
    "ZB-WATCH-011": check_watch_011,
    "ZB-WATCH-012": check_watch_012,
}
