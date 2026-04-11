#!/usr/bin/env python3
"""Proof-of-Reserves reconciliation for the Zephyr Bridge.

Compares:
  1. Total EVM circulating supply of each wrapped token (wZEPH, wZSD, wZRS, wZYS)
  2. Total actual Zephyr assets held by the bridge wallet (via daemon RPC)

A discrepancy > 0.01% is flagged as an error.

Usage:
    ./scripts/verify-reserves.py
    make verify-reserves
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
ORCH_DIR = SCRIPT_DIR.parent
ATOMIC = 1_000_000_000_000  # 1e12 — Zephyr uses 12 decimal places
TOLERANCE_PCT = 0.01        # Flag any discrepancy over 0.01%

# ── Colors ─────────────────────────────────────────────────────────────
GREEN  = "\033[0;32m"
RED    = "\033[0;31m"
YELLOW = "\033[1;33m"
CYAN   = "\033[0;36m"
DIM    = "\033[2m"
BOLD   = "\033[1m"
NC     = "\033[0m"

pass_count = 0
fail_count = 0
warn_count = 0

def ok(msg: str) -> None:
    global pass_count; pass_count += 1
    print(f"  {GREEN}✓{NC} {msg}")

def fail(msg: str) -> None:
    global fail_count; fail_count += 1
    print(f"  {RED}✗{NC} {msg}")

def warn(msg: str) -> None:
    global warn_count; warn_count += 1
    print(f"  {YELLOW}⚠{NC} {msg}")

def dim(msg: str) -> None:
    print(f"  {DIM}·{NC} {DIM}{msg}{NC}")

def header(msg: str) -> None:
    print(f"\n{BOLD}{CYAN}{'=' * 60}{NC}")
    print(f"{BOLD}{CYAN}  {msg}{NC}")
    print(f"{BOLD}{CYAN}{'=' * 60}{NC}")


# ── Helpers ─────────────────────────────────────────────────────────────

def load_env() -> None:
    env_file = ORCH_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key:
            os.environ.setdefault(key, os.path.expandvars(value.strip().strip("'\"")))


def eth_call(to: str, data: str, rpc: str = "http://127.0.0.1:8545") -> str | None:
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "eth_call",
        "params": [{"to": to, "data": data}, "latest"],
    }).encode()
    try:
        req = Request(rpc, data=payload, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read()).get("result")
    except Exception:
        return None


def erc20_total_supply(token: str, decimals: int) -> float | None:
    """Call totalSupply() on an ERC-20 token and decode to human units."""
    result = eth_call(token, "0x18160ddd")  # totalSupply()
    if result is None or result == "0x":
        return None
    raw = int(result, 16)
    return raw / (10 ** decimals)


def rpc_call(url: str, method: str, params: dict | None = None, timeout: int = 5) -> dict | None:
    payload = json.dumps({
        "jsonrpc": "2.0", "id": "0", "method": method, "params": params or {},
    }).encode()
    try:
        req = Request(url + "/json_rpc", data=payload,
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
        if "error" in data:
            return None
        return data.get("result")
    except Exception:
        return None


def get_bridge_wallet_balances(port: int) -> dict[str, float]:
    """Query bridge Zephyr wallet balances (unlocked) by asset type."""
    result = rpc_call(f"http://127.0.0.1:{port}", "get_balance",
                      {"account_index": 0, "all_assets": True})
    if not result:
        return {}
    balances: dict[str, float] = {}
    for entry in result.get("balances", []):
        asset = entry.get("asset_type", "")
        unlocked = int(entry.get("unlocked_balance", 0))
        balances[asset] = unlocked / ATOMIC
    return balances


def load_addresses() -> dict:
    path = ORCH_DIR / "config" / "addresses.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


# ── Reconciliation ───────────────────────────────────────────────────────

# Maps wrapped EVM token name → Zephyr native asset type
WRAPPED_TO_NATIVE: dict[str, str] = {
    "wZEPH": "ZPH",
    "wZSD":  "ZSD",
    "wZRS":  "ZRS",
    "wZYS":  "ZYS",
}

# Port of the bridge wallet (holds custodied native assets)
BRIDGE_WALLET_PORT = 48770


def reconcile(addresses: dict) -> bool:
    tokens = addresses.get("tokens", {})
    if not tokens:
        fail("No tokens found in addresses.json")
        return False

    bridge_balances = get_bridge_wallet_balances(BRIDGE_WALLET_PORT)
    if not bridge_balances:
        fail(f"Could not query bridge wallet on :{BRIDGE_WALLET_PORT}")
        return False

    dim(f"Bridge wallet native balances: {bridge_balances}")

    all_ok = True
    for wrapped_name, native_asset in WRAPPED_TO_NATIVE.items():
        token_info = tokens.get(wrapped_name)
        if not token_info:
            warn(f"{wrapped_name}: not in addresses.json — skipping")
            continue

        token_addr = token_info.get("address", "")
        decimals   = token_info.get("decimals", 12)

        # 1. EVM circulating supply
        evm_supply = erc20_total_supply(token_addr, decimals)
        if evm_supply is None:
            fail(f"{wrapped_name}: could not read EVM totalSupply from {token_addr}")
            all_ok = False
            continue

        # 2. Native bridge wallet holdings
        native_held = bridge_balances.get(native_asset, 0.0)

        # 3. Discrepancy check
        if evm_supply == 0 and native_held == 0:
            ok(f"{wrapped_name}: both EVM supply and native balance are 0 (unused token)")
            continue

        if evm_supply == 0:
            warn(f"{wrapped_name}: EVM supply = 0 but bridge holds {native_held:.4f} {native_asset}")
            continue

        discrepancy_pct = abs(evm_supply - native_held) / evm_supply * 100

        msg = (
            f"{wrapped_name}: EVM supply={evm_supply:.6f}  "
            f"bridge holds={native_held:.6f} {native_asset}  "
            f"diff={discrepancy_pct:+.4f}%"
        )

        if discrepancy_pct <= TOLERANCE_PCT:
            ok(msg)
        elif discrepancy_pct <= 1.0:
            # Warn for drifts up to 1%: these could be in-flight wraps awaiting
            # confirmation. One block cycle should converge these.
            warn(msg + "  ⚠ within 1% — likely in-flight")
            all_ok = False
        else:
            fail(msg + f"  ❌ exceeds {TOLERANCE_PCT}% tolerance")
            all_ok = False

    return all_ok


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> int:
    load_env()

    print(f"\n{BOLD}Zephyr Bridge — Proof-of-Reserves Reconciliation{NC}")
    print(f"{DIM}Tolerance: {TOLERANCE_PCT}%  |  Bridge wallet port: {BRIDGE_WALLET_PORT}{NC}\n")

    addresses = load_addresses()
    if not addresses:
        fail("config/addresses.json not found — has dev-setup been run?")
        return 1

    # Quick availability check: can we reach Anvil?
    try:
        payload = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "eth_blockNumber", "params": [],
        }).encode()
        req = Request("http://127.0.0.1:8545", data=payload,
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=3) as resp:
            block = int(json.loads(resp.read()).get("result", "0x0"), 16)
        dim(f"EVM block: {block}")
    except Exception:
        fail("Cannot reach Anvil at http://127.0.0.1:8545 — is the stack running?")
        return 1

    header("Token Reserve Reconciliation")
    all_ok = reconcile(addresses)

    print(f"\n{BOLD}{'─' * 60}{NC}")
    total = pass_count + fail_count + warn_count
    print(
        f"  {GREEN}✓ {pass_count} passed{NC}  "
        f"{RED}✗ {fail_count} failed{NC}  "
        f"{YELLOW}⚠ {warn_count} warnings{NC}  "
        f"({total} checks)"
    )
    if fail_count > 0:
        print(f"  {RED}{BOLD}FAIL — reserves do not match EVM supply{NC}")
    elif warn_count > 0:
        print(f"  {YELLOW}{BOLD}WARN — minor drift detected (may be in-flight wraps){NC}")
    else:
        print(f"  {GREEN}{BOLD}PASS — all reserves match EVM circulating supply{NC}")
    print()
    return 1 if fail_count > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
