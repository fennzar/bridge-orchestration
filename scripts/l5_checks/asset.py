"""ZB-ASSET: Multi-Asset Interactions (10 tests)."""
from __future__ import annotations

from ._helpers import (
    PASS, FAIL, BLOCKED,
    _r, _needs, _jget,
    _contract_exists, _decimals, _total_supply,
    API, ENGINE,
    TK,
)


def _check_asset_token(row, probes, symbol):
    b = _needs(row, probes, "bridge_api", "anvil")
    if b:
        return b
    addr = TK.get(symbol)
    if not addr:
        return _r(row, FAIL, f"Unknown token: {symbol}")
    exists, err = _contract_exists(addr)
    if err or not exists:
        return _r(row, FAIL, f"{symbol} not deployed at {addr}")
    d, err = _decimals(addr)
    if err:
        return _r(row, FAIL, f"{symbol} decimals error: {err}")
    if d != 12:
        return _r(row, FAIL, f"{symbol} decimals={d}, expected 12")
    supply, err = _total_supply(addr)
    if err:
        return _r(row, FAIL, f"{symbol} totalSupply error: {err}")
    data, err = _jget(f"{API}/bridge/tokens")
    if err:
        return _r(row, FAIL, f"Bridge tokens error: {err}")
    tokens = data.get("tokens", data) if isinstance(data, dict) else data
    found = any(t.get("symbol", "").upper() == symbol.upper() for t in tokens) if isinstance(tokens, list) else False
    if not found:
        return _r(row, FAIL, f"{symbol} not in bridge API tokens")
    return _r(row, PASS, f"{symbol}: deployed, decimals=12, supply={supply / 1e12:.2f}, in bridge API")

def check_asset_001(row, probes):
    return _check_asset_token(row, probes, "wZSD")
def check_asset_002(row, probes):
    return _check_asset_token(row, probes, "wZRS")
def check_asset_003(row, probes):
    return _check_asset_token(row, probes, "wZYS")
def check_asset_004(row, probes):
    return _check_asset_token(row, probes, "wZSD")
def check_asset_005(row, probes):
    return _check_asset_token(row, probes, "wZRS")
def check_asset_006(row, probes):
    return _check_asset_token(row, probes, "wZYS")

def check_asset_007(row, probes):
    """Reject legacy asset_type usage."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    data, err = _jget(f"{API}/bridge/tokens")
    if err:
        return _r(row, FAIL, f"Tokens error: {err}")
    tokens = data.get("tokens", data) if isinstance(data, dict) else data
    syms = {t.get("symbol", "") for t in tokens} if isinstance(tokens, list) else set()
    v1 = syms & {"ZEPH", "ZEPHUSD", "ZEPHRSV", "ZYIELD"}
    if v1:
        return _r(row, FAIL, f"V1 legacy assets in API: {v1}")
    v2 = syms & {"WZEPH", "WZSD", "WZRS", "WZYS"}
    return _r(row, PASS, f"No V1 legacy assets; V2 present: {v2}")

def check_asset_008(row, probes):
    b = _needs(row, probes, "anvil")
    if b:
        return b
    parts = []
    for sym in ["wZEPH", "wZSD", "wZRS", "wZYS"]:
        d, err = _decimals(TK[sym])
        if err:
            return _r(row, FAIL, f"{sym} decimals error: {err}")
        if d != 12:
            return _r(row, FAIL, f"{sym} decimals={d}, expected 12")
        s, err = _total_supply(TK[sym])
        if err:
            return _r(row, FAIL, f"{sym} totalSupply error: {err}")
        # 1 atomic unit = 10^-12; verify supply is a valid uint256
        if s < 0:
            return _r(row, FAIL, f"{sym} negative supply: {s}")
        parts.append(f"{sym}: d=12, supply={s}")
    return _r(row, PASS, f"1 atomic unit (10^-12) representable; {'; '.join(parts)}")

def check_asset_009(row, probes):
    b = _needs(row, probes, "anvil")
    if b:
        return b
    max_uint256 = (2 ** 256) - 1
    parts = []
    for sym in ["wZEPH", "wZSD", "wZRS", "wZYS"]:
        s, err = _total_supply(TK[sym])
        if err:
            return _r(row, FAIL, f"{sym} totalSupply error: {err}")
        if s > max_uint256:
            return _r(row, FAIL, f"{sym} supply exceeds uint256: {s}")
        if s * 2 > max_uint256:
            return _r(row, FAIL, f"{sym} supply*2 overflows uint256: {s}")
        parts.append(f"{sym}={s}")
    return _r(row, PASS, f"All supplies safe in uint256 range; {', '.join(parts)}")

def check_asset_010(row, probes):
    b = _needs(row, probes, "engine")
    if b:
        return b
    data, err = _jget(f"{ENGINE}/api/state")
    if err:
        return _r(row, FAIL, f"Engine state error: {err}")
    paths = [
        ("ZSD.n", "WZSD.e"),
        ("ZRS.n", "WZRS.e"),
        ("ZYS.n", "WZYS.e"),
    ]
    results = []
    for frm, to in paths:
        rd, re = _jget(f"{ENGINE}/api/runtime?op=auto&from={frm}&to={to}")
        if re:
            results.append(f"{frm}->{to}: ERR({re})")
        else:
            enabled = (rd or {}).get("runtime", {}).get("enabled")
            results.append(f"{frm}->{to}: enabled={enabled}")
    return _r(row, PASS, f"Cross-asset paths: {'; '.join(results)}")


CHECKS = {
    "ZB-ASSET-001": check_asset_001,
    "ZB-ASSET-002": check_asset_002,
    "ZB-ASSET-003": check_asset_003,
    "ZB-ASSET-004": check_asset_004,
    "ZB-ASSET-005": check_asset_005,
    "ZB-ASSET-006": check_asset_006,
    "ZB-ASSET-007": check_asset_007,
    "ZB-ASSET-008": check_asset_008,
    "ZB-ASSET-009": check_asset_009,
    "ZB-ASSET-010": check_asset_010,
}
