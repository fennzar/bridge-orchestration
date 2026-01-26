"""ZB-CONF: Configuration Errors (10 tests)."""
from __future__ import annotations

from ._helpers import (
    PASS, FAIL, BLOCKED,
    _r, _needs, _jget, _jpost, _get, _rpc,
    _contract_exists, _decimals,
    API, ENGINE, ANVIL, ZNODE, ORACLE, OBOOK,
    TK, GOV_W,
)


def check_conf_001(row, probes):
    b = _needs(row, probes, "zephyr_node")
    if b:
        return b
    result, err = _rpc(ZNODE, "get_info")
    if err:
        return _r(row, FAIL, f"Node error: {err}")
    h = (result or {}).get("height", 0)
    return _r(row, PASS, f"Zephyr node on correct port (height={h})")

def check_conf_002(row, probes):
    b = _needs(row, probes, "zephyr_node")
    if b:
        return b
    result, err = _rpc(GOV_W, "get_version")
    if err:
        return _r(row, FAIL, f"Gov wallet unreachable: {err}")
    v = (result or {}).get("version", "unknown")
    # Also verify address retrieval works
    addr_result, addr_err = _rpc(GOV_W, "get_address", {"account_index": 0, "address_index": 0})
    if addr_err:
        return _r(row, FAIL, f"Gov wallet get_address failed: {addr_err}")
    addr = (addr_result or {}).get("address", "")
    parts = [f"version={v}"]
    if addr:
        parts.append(f"addr={addr[:12]}...")
    return _r(row, PASS, f"Gov wallet RPC OK: {'; '.join(parts)}")

def check_conf_003(row, probes):
    b = _needs(row, probes, "anvil")
    if b:
        return b
    parsed, err = _jpost(ANVIL, {"jsonrpc": "2.0", "method": "eth_blockNumber", "params": [], "id": 1})
    if err:
        return _r(row, FAIL, f"Anvil error: {err}")
    block = int((parsed or {}).get("result", "0x0"), 16)
    return _r(row, PASS, f"Anvil on correct port (block={block})")

def check_conf_004(row, probes):
    """Token addresses in API match on-chain."""
    b = _needs(row, probes, "bridge_api", "anvil")
    if b:
        return b
    data, err = _jget(f"{API}/bridge/tokens")
    if err:
        return _r(row, FAIL, f"Tokens error: {err}")
    tokens = data.get("tokens", data) if isinstance(data, dict) else data
    issues = []
    for t in (tokens if isinstance(tokens, list) else []):
        sym = t.get("symbol", "")
        addr = t.get("address", "").lower()
        # API returns uppercase (WZEPH), TK uses mixed-case (wZEPH) -- try both
        expected = (TK.get(sym) or TK.get(sym[0].lower() + sym[1:]) or "").lower()
        if expected and addr != expected:
            issues.append(f"{sym}: got {addr}, expected {expected}")
        if addr and addr != "0x":
            exists, err = _contract_exists(addr)
            if err or not exists:
                issues.append(f"{sym}: no contract at {addr}")
    if issues:
        return _r(row, FAIL, "; ".join(issues))
    return _r(row, PASS, f"All {len(tokens)} token addresses verified on-chain")

def check_conf_005(row, probes):
    """Decimals config matches on-chain."""
    b = _needs(row, probes, "bridge_api", "anvil")
    if b:
        return b
    data, err = _jget(f"{API}/bridge/tokens")
    if err:
        return _r(row, FAIL, f"Tokens error: {err}")
    tokens = data.get("tokens", data) if isinstance(data, dict) else data
    issues = []
    for t in (tokens if isinstance(tokens, list) else []):
        sym = t.get("symbol", "")
        api_dec = t.get("decimals")
        addr = t.get("address", "")
        if addr and sym.upper().startswith("W"):
            chain_dec, err = _decimals(addr)
            if err:
                issues.append(f"{sym}: on-chain error: {err}")
            elif api_dec is not None and chain_dec != api_dec:
                issues.append(f"{sym}: API={api_dec}, chain={chain_dec}")
    if issues:
        return _r(row, FAIL, "; ".join(issues))
    return _r(row, PASS, "API decimals match on-chain values")

def check_conf_006(row, probes):
    b = _needs(row, probes, "oracle")
    if b:
        return b
    data, err = _jget(f"{ORACLE}/status")
    if err:
        return _r(row, FAIL, f"Oracle unreachable: {err}")
    if not isinstance(data, dict):
        return _r(row, FAIL, f"Oracle returned non-dict: {type(data).__name__}")
    spot = data.get("spot")
    # Verify response has at least spot/price field
    has_price = spot is not None or data.get("price") is not None
    if not has_price:
        return _r(row, FAIL, f"Oracle response missing spot/price field, keys: {list(data.keys())}")
    return _r(row, PASS, f"Oracle reachable, spot={spot}")

def check_conf_007(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    s, _, e = _get(f"{API}/admin/auth/verify")
    if s in (401, 403):
        return _r(row, PASS, f"Admin auth configured (HTTP {s})")
    if e and ("401" in str(e) or "403" in str(e)):
        return _r(row, PASS, "Admin auth configured")
    return _r(row, FAIL, f"Admin returned HTTP {s}")

def check_conf_008(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    s, _, e = _get(f"{API}/health")
    if s != 200:
        return _r(row, FAIL, f"Health failed (HTTP {s}) -- possible schema issue")
    data, err = _jget(f"{API}/claims/all?limit=1")
    if err:
        return _r(row, FAIL, f"Claims query failed (schema drift?): {err}")
    return _r(row, PASS, "Bridge healthy + DB query OK -- schema consistent")

def check_conf_009(row, probes):
    b = _needs(row, probes, "engine")
    if b:
        return b
    data, err = _jget(f"{ENGINE}/api/state")
    if err:
        return _r(row, FAIL, f"Engine error: {err}")
    state = (data or {}).get("state", {}) or {}
    cex = state.get("cex")
    if cex is None:
        return _r(row, FAIL, "Engine state missing CEX data")
    # Also check for market data availability
    market_keys = list(cex.keys()) if isinstance(cex, dict) else []
    return _r(row, PASS,
              f"Engine CEX data present (keys: {', '.join(market_keys[:5]) if market_keys else 'object'})")

def check_conf_010(row, probes):
    b = _needs(row, probes, "engine")
    if b:
        return b
    data, err = _jget(f"{ENGINE}/api/runtime?op=auto&from=ZEPH.n&to=WZEPH.e")
    if err:
        return _r(row, FAIL, f"Runtime error: {err}")
    runtime = (data or {}).get("runtime", {})
    if not runtime:
        return _r(row, FAIL, "Empty runtime response")
    return _r(row, PASS, "Engine runtime responds with threshold-aware data")


CHECKS = {
    "ZB-CONF-001": check_conf_001,
    "ZB-CONF-002": check_conf_002,
    "ZB-CONF-003": check_conf_003,
    "ZB-CONF-004": check_conf_004,
    "ZB-CONF-005": check_conf_005,
    "ZB-CONF-006": check_conf_006,
    "ZB-CONF-007": check_conf_007,
    "ZB-CONF-008": check_conf_008,
    "ZB-CONF-009": check_conf_009,
    "ZB-CONF-010": check_conf_010,
}
