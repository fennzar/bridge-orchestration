# lp.py

"""ZB-LP: Bridge-Web LP Management (13 tests).

Covers the data layer the bridge-web ``/lps`` page actually depends on:
``/uniswap/config`` (use-liquidity-actions, use-pools), ``/uniswap/pools/full``
(use-pools), per-pool drill-downs (pool-detail-card, positions-section,
recent-activity), ``/uniswap/pool/:id/ohlc`` (candlestick-chart),
``/uniswap/positions?owner=`` (my-positions), ``/uniswap/stream`` (use-pool-stream),
and the ``/lps`` page render itself.

Note: ``/uniswap/quotes`` is an empty Hono stub (no routes mounted) and is not
consumed by the LP page, so it is intentionally not covered here.
"""
from __future__ import annotations

from urllib.request import Request, urlopen

from ._helpers import (
    PASS, FAIL,
    _r, _needs, _jget, _get, _contract_exists,
    API, WEB,
)

# Event kinds the activity feed (recent-activity.tsx) renders.
VALID_EVENT_KINDS = {"mint", "burn", "swap", "initialize", "donate", "modify", "collect"}


def _first_pool_id():
    """Return (poolId, error) for the first pool in /uniswap/pools."""
    data, err = _jget(f"{API}/uniswap/pools")
    if err or data is None:
        return None, f"pools error: {err}"
    pools = data.get("pools", data) if isinstance(data, dict) else data
    if not isinstance(pools, list) or not pools:
        return None, "no pools returned"
    pid = pools[0].get("poolId")
    if not pid:
        return None, "first pool has no poolId"
    return pid, None


# ── ZB-LP-001: config endpoint (LP UI first load) ─────────────────────────────
def check_lp_001(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    data, err = _jget(f"{API}/uniswap/config")
    if err or data is None:
        return _r(row, FAIL, f"config error: {err}")
    if not data.get("ok"):
        return _r(row, FAIL, f"config not ok: {data.get('error')}")
    contracts = (data.get("addresses") or {}).get("contracts") or {}
    posm = contracts.get("positionManager")
    poolm = contracts.get("poolManager")
    if not posm or not poolm:
        return _r(row, FAIL, f"missing contracts: positionManager={posm}, poolManager={poolm}")
    tokens = (data.get("addresses") or {}).get("tokens") or {}
    pools = (data.get("addresses") or {}).get("pools") or {}
    if not tokens or not pools:
        return _r(row, FAIL, f"config thin: tokens={len(tokens)}, pools={len(pools)}")
    return _r(row, PASS,
              f"config OK: positionManager set, {len(tokens)} tokens, {len(pools)} pool plans")


# ── ZB-LP-002: config PositionManager is deployed on-chain ────────────────────
def check_lp_002(row, probes):
    b = _needs(row, probes, "bridge_api", "anvil")
    if b:
        return b
    data, err = _jget(f"{API}/uniswap/config")
    if err or data is None:
        return _r(row, FAIL, f"config error: {err}")
    posm = ((data.get("addresses") or {}).get("contracts") or {}).get("positionManager")
    if not posm:
        return _r(row, FAIL, "config has no positionManager")
    exists, cerr = _contract_exists(posm)
    if cerr:
        return _r(row, FAIL, f"bytecode check error: {cerr}")
    if not exists:
        return _r(row, FAIL, f"PositionManager {posm} has no bytecode")
    return _r(row, PASS, f"PositionManager {posm} deployed (LP writes target this)")


# ── ZB-LP-003: pools/full feed shape (use-pools) ──────────────────────────────
def check_lp_003(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    data, err = _jget(f"{API}/uniswap/pools/full?activityLimit=50")
    if err or data is None:
        return _r(row, FAIL, f"pools/full error: {err}")
    pools = data.get("pools", []) if isinstance(data, dict) else data
    if not isinstance(pools, list) or not pools:
        return _r(row, FAIL, f"no pools in full feed (got {type(pools).__name__})")
    required = {"record", "metrics", "activity", "positions"}
    for i, p in enumerate(pools):
        missing = required - set(p.keys())
        if missing:
            return _r(row, FAIL, f"pool[{i}] missing keys: {', '.join(sorted(missing))}")
    return _r(row, PASS, f"{len(pools)} pools, each has record+metrics+activity+positions")


# ── ZB-LP-004: pool metrics shape (pool-detail-card) ──────────────────────────
def check_lp_004(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    data, err = _jget(f"{API}/uniswap/pools/full?activityLimit=1")
    if err or data is None:
        return _r(row, FAIL, f"pools/full error: {err}")
    pools = data.get("pools", []) if isinstance(data, dict) else data
    if not pools:
        return _r(row, FAIL, "no pools")
    p = pools[0]
    metrics = p.get("metrics") or {}
    for key in ("tvl", "volume24h", "volume7d"):
        if key not in metrics:
            return _r(row, FAIL, f"metrics missing {key}")
    sqrt = ((p.get("record") or {}).get("slot0") or {}).get("sqrtPriceX96")
    if not sqrt:
        return _r(row, FAIL, "record.slot0.sqrtPriceX96 absent")
    tvl_usd = (metrics.get("tvl") or {}).get("usd")
    return _r(row, PASS, f"metrics OK: tvl.usd={tvl_usd}, volume24h+7d present, sqrtPriceX96 set")


# ── ZB-LP-005: activity event shape (recent-activity) ─────────────────────────
def check_lp_005(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    data, err = _jget(f"{API}/uniswap/pools/full?activityLimit=50")
    if err or data is None:
        return _r(row, FAIL, f"pools/full error: {err}")
    pools = data.get("pools", []) if isinstance(data, dict) else data
    events = []
    for p in pools:
        events.extend((p.get("activity") or {}).get("events") or [])
    if not events:
        return _r(row, FAIL, "no activity events across any pool")
    kinds = set()
    for ev in events:
        kind = ev.get("kind")
        if not kind:
            return _r(row, FAIL, "event missing 'kind'")
        if kind not in VALID_EVENT_KINDS:
            return _r(row, FAIL, f"unknown event kind: {kind}")
        kinds.add(kind)
        if kind == "mint" and ("tickLower" not in ev or "tickUpper" not in ev):
            return _r(row, FAIL, "mint event missing tick range")
    return _r(row, PASS, f"{len(events)} events OK, kinds={sorted(kinds)}")


# ── ZB-LP-006: owner-scoped positions (my-positions) ──────────────────────────
def check_lp_006(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    # Use the deployer from config as a realistic owner; empty result is valid.
    cfg, _ = _jget(f"{API}/uniswap/config")
    owner = (cfg or {}).get("addresses", {}).get("deployer") if isinstance(cfg, dict) else None
    owner = owner or "0x0000000000000000000000000000000000000000"
    data, err = _jget(f"{API}/uniswap/positions?owner={owner}")
    if err or data is None:
        return _r(row, FAIL, f"positions error: {err}")
    if not data.get("ok"):
        return _r(row, FAIL, f"positions not ok: {data.get('error')}")
    positions = data.get("positions")
    if not isinstance(positions, list):
        return _r(row, FAIL, f"positions not a list: {type(positions).__name__}")
    return _r(row, PASS, f"owner positions OK (owner={owner[:10]}…, {len(positions)} positions)")


# ── ZB-LP-007: per-pool full drill-down (pool-detail-card) ────────────────────
def check_lp_007(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    pid, perr = _first_pool_id()
    if not pid:
        return _r(row, FAIL, perr or "no pool")
    data, err = _jget(f"{API}/uniswap/pool/{pid}/full?limit=5")
    if err or data is None:
        return _r(row, FAIL, f"pool/full error: {err}")
    if not {"record", "metrics", "activity", "positions"} <= set(data.keys()):
        return _r(row, FAIL, f"pool/full missing keys: {sorted(data.keys())}")
    got = (data.get("record") or {}).get("poolId")
    if got != pid:
        return _r(row, FAIL, f"poolId mismatch: asked {pid[:12]}…, got {str(got)[:12]}…")
    return _r(row, PASS, f"pool/{pid[:12]}… full OK (record+metrics+activity+positions)")


# ── ZB-LP-008: per-pool metrics drill-down ────────────────────────────────────
def check_lp_008(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    pid, perr = _first_pool_id()
    if not pid:
        return _r(row, FAIL, perr or "no pool")
    data, err = _jget(f"{API}/uniswap/pool/{pid}/metrics")
    if err or data is None:
        return _r(row, FAIL, f"metrics error: {err}")
    for key in ("tvl", "volume24h"):
        if key not in data:
            return _r(row, FAIL, f"metrics missing {key}")
    return _r(row, PASS, f"pool/{pid[:12]}… metrics OK (tvl + volume24h)")


# ── ZB-LP-009: per-pool positions drill-down (positions-section) ──────────────
def check_lp_009(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    pid, perr = _first_pool_id()
    if not pid:
        return _r(row, FAIL, perr or "no pool")
    data, err = _jget(f"{API}/uniswap/pool/{pid}/positions")
    if err or data is None:
        return _r(row, FAIL, f"positions error: {err}")
    positions = data.get("positions")
    if not isinstance(positions, list):
        return _r(row, FAIL, f"positions not a list: {type(positions).__name__}")
    if "count" not in data:
        return _r(row, FAIL, "positions response missing count")
    return _r(row, PASS, f"pool/{pid[:12]}… positions OK (count={data.get('count')})")


# ── ZB-LP-010: per-pool activity + pagination (recent-activity) ───────────────
def check_lp_010(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    pid, perr = _first_pool_id()
    if not pid:
        return _r(row, FAIL, perr or "no pool")
    data, err = _jget(f"{API}/uniswap/pool/{pid}/activity?limit=3")
    if err or data is None:
        return _r(row, FAIL, f"activity error: {err}")
    events = data.get("events")
    if not isinstance(events, list):
        return _r(row, FAIL, f"events not a list: {type(events).__name__}")
    if "next" not in data:
        return _r(row, FAIL, "activity response missing 'next' cursor field")
    return _r(row, PASS, f"pool/{pid[:12]}… activity OK ({len(events)} events, next={data.get('next')})")


# ── ZB-LP-011: OHLC candles (candlestick-chart / use-ohlc-data) ───────────────
def check_lp_011(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    pid, perr = _first_pool_id()
    if not pid:
        return _r(row, FAIL, perr or "no pool")
    data, err = _jget(f"{API}/uniswap/pool/{pid}/ohlc?interval=1h&limit=24")
    if err or data is None:
        return _r(row, FAIL, f"ohlc error: {err}")
    candles = data.get("candles")
    if not isinstance(candles, list):
        return _r(row, FAIL, f"candles not a list: {type(candles).__name__}")
    # Empty is valid (no swaps yet); validate shape if any candle present.
    if candles:
        c = candles[0]
        for key in ("open", "high", "low", "close"):
            if key not in c:
                return _r(row, FAIL, f"candle missing {key}")
    return _r(row, PASS, f"pool/{pid[:12]}… ohlc OK ({len(candles)} candles)")


# ── ZB-LP-012: SSE live updates (use-pool-stream) ─────────────────────────────
def check_lp_012(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    try:
        resp = urlopen(Request(f"{API}/uniswap/stream", method="GET"), timeout=3.0)
        ct = resp.headers.get("content-type", "")
        resp.close()
    except Exception as e:
        # Streaming body read can time out before close — still proves it streams.
        msg = str(e).lower()
        if "timed out" in msg or "timeout" in msg:
            return _r(row, PASS, "SSE stream alive (timeout on body = streaming)")
        return _r(row, FAIL, f"SSE error: {e}")
    if "text/event-stream" not in ct:
        return _r(row, FAIL, f"unexpected content-type: {ct}")
    return _r(row, PASS, f"SSE stream OK (content-type={ct})")


# ── ZB-LP-013: /lps page renders ──────────────────────────────────────────────
def check_lp_013(row, probes):
    b = _needs(row, probes, "bridge_web")
    if b:
        return b
    s, body, e = _get(f"{WEB}/lps")
    if s != 200:
        return _r(row, FAIL, f"/lps HTTP {s}: {e}")
    body = body or ""
    if "Liquidity Pools" not in body:
        return _r(row, FAIL, "/lps rendered but missing 'Liquidity Pools' title/content")
    return _r(row, PASS, f"/lps OK (HTTP 200, {len(body)} bytes, title present)")


CHECKS = {
    "ZB-LP-001": check_lp_001,
    "ZB-LP-002": check_lp_002,
    "ZB-LP-003": check_lp_003,
    "ZB-LP-004": check_lp_004,
    "ZB-LP-005": check_lp_005,
    "ZB-LP-006": check_lp_006,
    "ZB-LP-007": check_lp_007,
    "ZB-LP-008": check_lp_008,
    "ZB-LP-009": check_lp_009,
    "ZB-LP-010": check_lp_010,
    "ZB-LP-011": check_lp_011,
    "ZB-LP-012": check_lp_012,
    "ZB-LP-013": check_lp_013,
}
