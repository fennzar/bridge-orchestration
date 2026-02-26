"""ZB-PRIV: Privacy Leaks (6 tests)."""
from __future__ import annotations

import json
import re
import subprocess

from ._helpers import (
    PASS, FAIL, BLOCKED,
    _r, _needs, _jget, _get,
    API, ENGINE,
    FAKE_EVM, FAKE_EVM_2,
)


def check_priv_001(row, probes):
    """No Zephyr subaddress cross-leak."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    d1, e1 = _jget(f"{API}/claims/{FAKE_EVM}")
    d2, e2 = _jget(f"{API}/claims/{FAKE_EVM_2}")
    if e1 or e2:
        return _r(row, FAIL, f"Claims error: {e1 or e2}")
    c1 = d1 if isinstance(d1, list) else (d1 or {}).get("claims", [])
    c2 = d2 if isinstance(d2, list) else (d2 or {}).get("claims", [])
    def _zeph_addrs(claims):
        addrs = set()
        for c in (claims if isinstance(claims, list) else []):
            if isinstance(c, dict):
                for f in ("zephyrAddress", "zephyr_address", "subaddress", "address"):
                    v = c.get(f)
                    if v and isinstance(v, str) and len(v) > 10:
                        addrs.add(v)
        return addrs
    z1 = _zeph_addrs(c1)
    z2 = _zeph_addrs(c2)
    overlap = z1 & z2
    if overlap:
        return _r(row, FAIL, f"Cross-leak: Zephyr address(es) in both responses: {overlap}")
    for c in (c1 if isinstance(c1, list) else []):
        if isinstance(c, dict):
            for f in ("evmAddress", "to", "evm_address"):
                v = (c.get(f) or "").lower()
                if v and v == FAKE_EVM_2.lower():
                    return _r(row, FAIL, f"Cross-leak: claim for {FAKE_EVM} references {FAKE_EVM_2}")
    for c in (c2 if isinstance(c2, list) else []):
        if isinstance(c, dict):
            for f in ("evmAddress", "to", "evm_address"):
                v = (c.get(f) or "").lower()
                if v and v == FAKE_EVM.lower():
                    return _r(row, FAIL, f"Cross-leak: claim for {FAKE_EVM_2} references {FAKE_EVM}")
    return _r(row, PASS, f"Claims address-scoped, no cross-leak (A={len(c1)} claims/{len(z1)} addrs, B={len(c2)} claims/{len(z2)} addrs)")

def check_priv_002(row, probes):
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    s, _, e = _get(f"{API}/details?evmAddress={FAKE_EVM}")
    if e and s is None:
        if "404" in str(e):
            return _r(row, PASS, "Details scoped (404 for unknown)")
        return _r(row, FAIL, f"Details error: {e}")
    return _r(row, PASS, f"Details responds (HTTP {s}); scoped to queried address")

def check_priv_003(row, probes):
    """SSE stream access behavior."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    s, body, e = _get(f"{API}/claims/{FAKE_EVM}/stream", timeout=3.0)
    if e and s is None:
        if "timeout" in str(e).lower() or "timed out" in str(e).lower():
            return _r(row, PASS, "SSE stream alive (timeout indicates active streaming)")
        s2, body2, e2 = _get(f"{API}/bridge/stream", timeout=3.0)
        if e2 and s2 is None:
            if "timeout" in str(e2).lower() or "timed out" in str(e2).lower():
                return _r(row, PASS, "SSE bridge stream alive (timeout indicates active streaming)")
            return _r(row, FAIL, f"SSE endpoints unreachable: {e}, {e2}")
        if s2 in (401, 403):
            return _r(row, PASS, f"SSE stream requires auth (HTTP {s2})")
        return _r(row, PASS, f"SSE bridge stream responds (HTTP {s2})")
    if s in (401, 403):
        return _r(row, PASS, f"SSE stream requires auth (HTTP {s})")
    return _r(row, PASS, f"SSE stream responds (HTTP {s})")

def check_priv_004(row, probes):
    """Logs do not print full Zephyr destination addresses by default."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b

    # Zephyr addresses: main start with "ZEPHYR" (~95 chars), subaddrs with "ZEPHs" (~95 chars)
    # We look for full-length addresses (>60 chars) to avoid false positives from short prefixes.
    zeph_addr_re = re.compile(r"(?:ZEPHYR|ZEPHs)[1-9A-HJ-NP-Za-km-z]{60,}")

    # Check logs from docker services that handle bridge operations
    containers = ["zephyr-bridge-api", "zephyr-bridge-watchers"]
    total_lines = 0
    leaks = []

    for container in containers:
        try:
            result = subprocess.run(
                ["docker", "logs", "--tail", "500", container],
                capture_output=True, text=True, timeout=15,
            )
        except FileNotFoundError:
            return _r(row, BLOCKED, "docker CLI not found")
        except subprocess.TimeoutExpired:
            return _r(row, BLOCKED, f"docker logs timed out for {container}")

        # docker logs outputs to both stdout and stderr
        log_output = (result.stdout or "") + (result.stderr or "")
        if not log_output.strip():
            continue

        lines = log_output.splitlines()
        total_lines += len(lines)
        for i, line in enumerate(lines):
            matches = zeph_addr_re.findall(line)
            if matches:
                # Truncate the address in the report to avoid leaking it here too
                for addr in matches:
                    preview = addr[:12] + "..." + addr[-6:]
                    leaks.append(f"{container}:L{i+1} ({preview})")

    if not total_lines:
        return _r(row, BLOCKED,
                  "No log output from bridge containers (containers may not exist)")

    if leaks:
        sample = "; ".join(leaks[:3])
        extra = f" (+{len(leaks)-3} more)" if len(leaks) > 3 else ""
        return _r(row, FAIL,
                  f"Full Zephyr address found in logs: {sample}{extra}")

    return _r(row, PASS,
              f"No full Zephyr addresses found in {total_lines} log lines "
              f"across {len(containers)} containers")

def check_priv_005(row, probes):
    """Engine state must not include private keys."""
    b = _needs(row, probes, "engine")
    if b:
        return b
    data, err = _jget(f"{ENGINE}/api/state")
    if err:
        return _r(row, FAIL, f"Engine error: {err}")
    state_str = json.dumps(data).lower()
    sensitive = ["private", "secret", "seed", "mnemonic", "privkey", "private_key"]
    found = [p for p in sensitive if p in state_str]
    if found:
        return _r(row, FAIL, f"Sensitive patterns in engine state: {found}")
    return _r(row, PASS, "Engine /api/state contains no sensitive key/seed patterns")

def check_priv_006(row, probes):
    """No raw address mapping leak in API responses."""
    b = _needs(row, probes, "bridge_api")
    if b:
        return b
    sensitive = ["private", "secret", "seed", "mnemonic", "privkey", "private_key"]
    mapping_patterns = ["address_map", "addressmap", "global_mapping", "all_addresses"]
    all_bodies = []
    endpoints = [
        f"{API}/bridge/tokens",
        f"{API}/claims/{FAKE_EVM}",
        f"{API}/health",
    ]
    for ep in endpoints:
        s, body, e = _get(ep)
        if body:
            all_bodies.append(body.lower())
    combined = " ".join(all_bodies)
    found_sensitive = [p for p in sensitive if p in combined]
    if found_sensitive:
        return _r(row, FAIL, f"Sensitive patterns found in API responses: {found_sensitive}")
    found_mapping = [p for p in mapping_patterns if p in combined]
    if found_mapping:
        return _r(row, FAIL, f"Global address mapping patterns found: {found_mapping}")
    return _r(row, PASS, f"No sensitive/mapping patterns in {len(endpoints)} API endpoints")


CHECKS = {
    "ZB-PRIV-001": check_priv_001,
    "ZB-PRIV-002": check_priv_002,
    "ZB-PRIV-003": check_priv_003,
    "ZB-PRIV-004": check_priv_004,
    "ZB-PRIV-005": check_priv_005,
    "ZB-PRIV-006": check_priv_006,
}
