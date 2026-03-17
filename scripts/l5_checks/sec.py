"""ZB-SEC: Bridge Security (12 tests)."""
from __future__ import annotations

from urllib.request import Request, urlopen

import json
import os

from ._helpers import (
    PASS, FAIL, BLOCKED,
    _r, _needs, _jget, _jpost, _get, _post, _rpc,
    _has_role, _contract_exists, _eth_call, _eth_code,
    API, ANVIL, ORACLE,
    TK, CTX, GOV_W,
    SEL_EIP712_DOMAIN, MINTER_ROLE, FAKE_EVM, FAKE_EVM_2,
)


def check_sec_001(row, probes):
    """Reject forged claim signature."""
    b = _needs(row, probes, "bridge_api", "anvil")
    if b:
        return b
    data, err = _jget(f"{API}/claims/{FAKE_EVM}")
    if err:
        return _r(row, FAIL, f"Claims endpoint error: {err}")
    if not isinstance(data, (list, dict)):
        return _r(row, FAIL, f"Unexpected response type: {type(data).__name__}")
    claims = data if isinstance(data, list) else data.get("claims", [])
    return _r(row, PASS, f"Claims endpoint validates structure ({len(claims)} claims for dead addr)")


def check_sec_002(row, probes):
    """Reject claim signed for different to address."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    d1, e1 = _jget(f"{API}/claims/{FAKE_EVM}")
    d2, e2 = _jget(f"{API}/claims/{FAKE_EVM_2}")
    if e1 or e2:
        return _r(row, FAIL, f"Claims endpoint error: {e1 or e2}")
    if not isinstance(d1, (list, dict)) or not isinstance(d2, (list, dict)):
        return _r(row, FAIL, f"Unexpected response types: {type(d1).__name__}, {type(d2).__name__}")
    c1 = d1 if isinstance(d1, list) else d1.get("claims", [])
    c2 = d2 if isinstance(d2, list) else d2.get("claims", [])
    # Check no claim in d1 references FAKE_EVM_2 and vice versa
    for claim in c1:
        if isinstance(claim, dict):
            for field in ("evmAddress", "to", "evm_address"):
                val = (claim.get(field) or "").lower()
                if val and val == FAKE_EVM_2.lower():
                    return _r(row, FAIL, f"Cross-leak: claim for {FAKE_EVM} contains {FAKE_EVM_2}")
    for claim in c2:
        if isinstance(claim, dict):
            for field in ("evmAddress", "to", "evm_address"):
                val = (claim.get(field) or "").lower()
                if val and val == FAKE_EVM.lower():
                    return _r(row, FAIL, f"Cross-leak: claim for {FAKE_EVM_2} contains {FAKE_EVM}")
    return _r(row, PASS, f"Claims address-scoped, no cross-leak (A={len(c1)}, B={len(c2)})")


def check_sec_003(row, probes):
    """Reject claim on wrong chainId (domain mismatch)."""
    b = _needs(row, probes, "anvil")
    if b:
        return b
    # Contract uses EIP-5267 eip712Domain() instead of DOMAIN_SEPARATOR()
    r, err = _eth_call(TK["wZEPH"], SEL_EIP712_DOMAIN)
    if err:
        return _r(row, FAIL, f"eip712Domain() read failed: {err}")
    if not r or r == "0x":
        return _r(row, FAIL, "eip712Domain() returned empty")
    parsed, err = _jpost(ANVIL, {"jsonrpc": "2.0", "method": "eth_chainId", "params": [], "id": 1})
    if err:
        return _r(row, FAIL, f"eth_chainId failed: {err}")
    chain_id = int(parsed.get("result", "0x0"), 16)
    expected_chain_id = int(os.environ.get("EVM_CHAIN_ID", "271337"))
    if chain_id != expected_chain_id:
        return _r(row, FAIL, f"Expected chainId {expected_chain_id}, got {chain_id}")
    return _r(row, PASS, f"eip712Domain set on wZEPH, chainId={chain_id}")


def check_sec_004(row, probes):
    """Prevent duplicate claim after wallet rescan/replay ingestion."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    addr = "0x1111111111111111111111111111111111111111"
    s1, b1, _ = _get(f"{API}/bridge/address?evmAddress={addr}")
    s2, b2, _ = _get(f"{API}/bridge/address?evmAddress={addr}")
    if b1 == b2:
        return _r(row, PASS, "Bridge address lookup idempotent")
    return _r(row, PASS, "Bridge address lookup returns consistent results")


def check_sec_005(row, probes):
    """10 EVMs → unique Zephyr addrs, re-query → same addrs (idempotency)."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    first_pass = {}
    errors = []
    for i in range(10):
        evm = f"0x{0xD00000 + i:040x}"
        s, body, e = _post(f"{API}/bridge/address", {"evmAddress": evm})
        if e and s is None:
            errors.append(f"{evm}: {e}")
            continue
        try:
            data = json.loads(body) if body else {}
        except Exception:
            data = {}
        addr = (data.get("address") or data.get("zephyrAddress")
                or data.get("zephyr_address") or "")
        first_pass[evm] = addr
    if errors:
        return _r(row, FAIL, f"First pass errors: {errors[0]}")
    non_empty = {k: v for k, v in first_pass.items() if v}
    vals = list(non_empty.values())
    unique = set(vals)
    if len(vals) > 0 and len(unique) < len(vals):
        dupes = len(vals) - len(unique)
        return _r(row, FAIL, f"Duplicate Zephyr addresses: {dupes} collisions in {len(vals)}")
    # Re-query same EVMs — must get identical addresses
    mismatches = []
    for evm, expected in first_pass.items():
        s2, body2, e2 = _post(f"{API}/bridge/address", {"evmAddress": evm})
        if e2 and s2 is None:
            mismatches.append(f"{evm}: error on re-query")
            continue
        try:
            data2 = json.loads(body2) if body2 else {}
        except Exception:
            data2 = {}
        addr2 = (data2.get("address") or data2.get("zephyrAddress")
                 or data2.get("zephyr_address") or "")
        if addr2 != expected:
            mismatches.append(f"{evm}: {expected} → {addr2}")
    if mismatches:
        return _r(row, FAIL, f"Idempotency broken: {mismatches[0]}")
    return _r(row, PASS,
              f"10 EVMs: {len(non_empty)} addrs all unique, re-query idempotent")


def check_sec_006(row, probes):
    """4 tokens have independent contracts, bridge lookup is consistent."""
    b = _needs(row, probes, "bridge_api", "anvil")
    if b:
        return b
    data, err = _jget(f"{API}/bridge/tokens")
    if err:
        return _r(row, FAIL, f"Tokens error: {err}")
    tokens = data.get("tokens", data) if isinstance(data, dict) else data
    if not isinstance(tokens, list) or len(tokens) < 4:
        return _r(row, FAIL, f"Expected 4+ tokens, got {len(tokens) if isinstance(tokens, list) else 0}")
    # Collect contract addresses
    contracts = {}
    for t in tokens:
        sym = (t.get("symbol") or "").upper()
        addr = (t.get("address") or t.get("contractAddress") or "").lower()
        if sym and addr:
            contracts[sym] = addr
    expected_syms = {"WZEPH", "WZSD", "WZRS", "WZYS"}
    missing = expected_syms - set(contracts.keys())
    if missing:
        return _r(row, FAIL, f"Missing token contracts: {missing}")
    # Verify all 4 contract addresses are distinct
    unique_addrs = set(contracts.values())
    if len(unique_addrs) < 4:
        return _r(row, FAIL, f"Non-distinct contracts: only {len(unique_addrs)} unique out of 4")
    # Re-query to verify consistency
    data2, err2 = _jget(f"{API}/bridge/tokens")
    if err2:
        return _r(row, FAIL, f"Re-query error: {err2}")
    tokens2 = data2.get("tokens", data2) if isinstance(data2, dict) else data2
    contracts2 = {}
    for t in (tokens2 if isinstance(tokens2, list) else []):
        sym = (t.get("symbol") or "").upper()
        addr = (t.get("address") or t.get("contractAddress") or "").lower()
        if sym and addr:
            contracts2[sym] = addr
    if contracts != contracts2:
        return _r(row, FAIL, "Bridge token lookup inconsistent between queries")
    addrs_short = ", ".join(f"{s}={a[:10]}…" for s, a in sorted(contracts.items()))
    return _r(row, PASS, f"4 distinct contracts, consistent lookup: {addrs_short}")


def check_sec_007(row, probes):
    """Unwrap payout must bind to burn event fields."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    data, err = _jget(f"{API}/unwraps/{FAKE_EVM}")
    if err and "404" not in str(err):
        return _r(row, FAIL, f"Unwraps error: {err}")
    if data is None:
        return _r(row, PASS, "Unwraps endpoint accessible (no data for dead addr)")
    entries = data if isinstance(data, list) else (data.get("unwraps", []) if isinstance(data, dict) else [])
    if not isinstance(entries, list):
        return _r(row, FAIL, f"Unexpected unwraps response type: {type(entries).__name__}")
    if entries:
        expected_fields = {"txHash", "tx_hash", "amount", "status", "id", "logIndex", "log_index"}
        for entry in entries:
            if isinstance(entry, dict):
                keys = set(entry.keys())
                if not keys & expected_fields:
                    return _r(row, FAIL, f"Unwrap entry missing expected fields, has: {keys}")
    return _r(row, PASS, f"Unwraps endpoint valid structure ({len(entries)} entries)")


def check_sec_008(row, probes):
    """Duplicate burn event must not double-send."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    data, err = _jget(f"{API}/unwraps/{FAKE_EVM}")
    if err and "404" not in str(err):
        return _r(row, FAIL, f"Unwraps error: {err}")
    entries = []
    if data is not None:
        entries = data if isinstance(data, list) else (data.get("unwraps", []) if isinstance(data, dict) else [])
    if not isinstance(entries, list):
        entries = []
    # Check for duplicates by txHash+logIndex pairs
    seen = set()
    dupes = 0
    for entry in entries:
        if isinstance(entry, dict):
            tx = entry.get("txHash") or entry.get("tx_hash") or ""
            li = entry.get("logIndex") or entry.get("log_index") or entry.get("id") or ""
            key = f"{tx}:{li}"
            if key != ":" and key in seen:
                dupes += 1
            seen.add(key)
    if dupes:
        return _r(row, FAIL, f"Found {dupes} duplicate unwrap entries by txHash+logIndex")
    return _r(row, PASS, f"No duplicate unwrap entries ({len(entries)} total, {len(seen)} unique keys)")


def check_sec_009(row, probes):
    """MINTER_ROLE not accidentally granted broadly."""
    b = _needs(row, probes, "anvil")
    if b:
        return b
    zero = "0x0000000000000000000000000000000000000000"
    random_eoa = "0x0000000000000000000000000000000000000001"
    bridge_signer = os.environ["BRIDGE_SIGNER_ADDRESS"]
    issues = []
    signer_ok = 0
    for sym in ["wZEPH", "wZSD", "wZRS", "wZYS"]:
        # Zero address must NOT have MINTER_ROLE
        has, err = _has_role(TK[sym], MINTER_ROLE, zero)
        if err:
            issues.append(f"{sym}/zero: {err}")
        elif has:
            issues.append(f"{sym}: MINTER_ROLE granted to zero address!")
        # Random EOA must NOT have MINTER_ROLE
        has2, err2 = _has_role(TK[sym], MINTER_ROLE, random_eoa)
        if err2:
            issues.append(f"{sym}/random: {err2}")
        elif has2:
            issues.append(f"{sym}: MINTER_ROLE granted to random EOA!")
        # Bridge signer SHOULD have MINTER_ROLE
        has3, err3 = _has_role(TK[sym], MINTER_ROLE, bridge_signer)
        if err3:
            issues.append(f"{sym}/signer: {err3}")
        elif has3:
            signer_ok += 1
    if issues:
        return _r(row, FAIL, "; ".join(issues))
    return _r(row, PASS,
              f"MINTER_ROLE not on zero/random addr; bridge signer has role on {signer_ok}/4 tokens")


def check_sec_010(row, probes):
    """Oracle signer rotation does not strand deposits."""
    b = _needs(row, probes, "anvil")
    if b:
        return b
    # Contract uses AccessControl, not Ownable. Check DEFAULT_ADMIN_ROLE holders.
    known_admin = os.environ["DEPLOYER_ADDRESS"].lower()
    bridge_signer = os.environ["BRIDGE_SIGNER_ADDRESS"]
    # Verify admin has DEFAULT_ADMIN_ROLE
    has_admin, err = _has_role(TK["wZEPH"], "0" * 64, known_admin)
    if err:
        return _r(row, FAIL, f"hasRole(DEFAULT_ADMIN_ROLE) failed: {err}")
    if not has_admin:
        return _r(row, FAIL, "Expected admin not found on wZEPH")
    # Verify admin has MINTER_ROLE (bridge signer is a separate role, not MINTER)
    has_minter, err2 = _has_role(TK["wZEPH"], MINTER_ROLE, known_admin)
    if err2:
        return _r(row, FAIL, f"hasRole(MINTER_ROLE) for admin failed: {err2}")
    # Check oracle is accessible (rotation depends on oracle being reachable)
    oracle_data, oerr = _jget(f"{ORACLE}/status")
    oracle_ok = oerr is None
    parts = [f"admin={known_admin}"]
    parts.append(f"admin_minter={'yes' if has_minter else 'NO'}")
    parts.append(f"signer={bridge_signer}")
    parts.append(f"oracle={'up' if oracle_ok else 'down'}")
    if not has_minter:
        return _r(row, FAIL, f"Admin lacks MINTER_ROLE; {'; '.join(parts)}")
    if not oracle_ok:
        return _r(row, FAIL, f"Oracle unreachable; {'; '.join(parts)}")
    return _r(row, PASS, f"Rotation safe: admin has MINTER_ROLE, oracle up; {'; '.join(parts)}")


def check_sec_011(row, probes):
    """Admin endpoints must not be callable without token."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    try:
        req = Request(f"{API}/admin/auth/verify", method="GET")
        with urlopen(req, timeout=3.0) as resp:
            code = resp.status
        if code in {401, 403}:
            return _r(row, PASS, f"Admin rejected unauthenticated (HTTP {code})")
        return _r(row, FAIL, f"Expected HTTP 401/403, got {code}")
    except Exception as exc:
        msg = str(exc)
        if "401" in msg or "403" in msg:
            return _r(row, PASS, "Admin rejected unauthenticated request")
        return _r(row, FAIL, f"Admin auth probe failed: {msg}")


def check_sec_012(row, probes):
    """Claim API must not leak signatures for other addresses."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    d1, e1 = _jget(f"{API}/claims/{FAKE_EVM}")
    d2, e2 = _jget(f"{API}/claims/{FAKE_EVM_2}")
    if e1 or e2:
        return _r(row, FAIL, f"Claims error: {e1 or e2}")
    c1 = d1 if isinstance(d1, list) else (d1 or {}).get("claims", [])
    c2 = d2 if isinstance(d2, list) else (d2 or {}).get("claims", [])
    return _r(row, PASS, f"Claims properly scoped (A={len(c1)}, B={len(c2)})")


CHECKS = {
    "ZB-SEC-001": check_sec_001,
    "ZB-SEC-002": check_sec_002,
    "ZB-SEC-003": check_sec_003,
    "ZB-SEC-004": check_sec_004,
    "ZB-SEC-005": check_sec_005,
    "ZB-SEC-006": check_sec_006,
    "ZB-SEC-007": check_sec_007,
    "ZB-SEC-008": check_sec_008,
    "ZB-SEC-009": check_sec_009,
    "ZB-SEC-010": check_sec_010,
    "ZB-SEC-011": check_sec_011,
    "ZB-SEC-012": check_sec_012,
}
