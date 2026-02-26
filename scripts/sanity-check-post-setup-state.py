#!/usr/bin/env python3
"""Post-setup sanity check — reports devnet state vs spec targets.

Cross-references the running devnet against the spec in
docs/plans/pool-seeding-targets.md. Reports oracle prices, pool prices,
pool liquidity, wallet balances, and engine inventory.

Usage:
    ./scripts/sanity-check.py              # Report current state only
    ./scripts/sanity-check.py --price 1.50 # Compare against $1.50 spec targets
    make sanity-check                      # Via Makefile
    make sanity-check PRICE=1.50           # With target price
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
ORCH_DIR = SCRIPT_DIR.parent
ATOMIC = 1_000_000_000_000  # 1e12

# Spec constants
INVENTORY_TARGET_USD = 10_000
MARGIN_TOKENS = 5_000
POOL_BUDGETS = {
    "USDT-USDC": 500_000,
    "wZSD-USDT": 50_000,
    "wZEPH-wZSD": 50_000,
    "wZYS-wZSD": 30_000,
    "wZRS-wZEPH": 30_000,
}

# ── Colors ──────────────────────────────────────────────────────────────

GREEN = "\033[0;32m"
RED = "\033[0;31m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
CYAN = "\033[0;36m"
DIM = "\033[2m"
BOLD = "\033[1m"
NC = "\033[0m"

pass_count = 0
fail_count = 0
warn_count = 0


def ok(msg: str) -> None:
    global pass_count
    pass_count += 1
    print(f"  {GREEN}✓{NC} {msg}")


def fail(msg: str) -> None:
    global fail_count
    fail_count += 1
    print(f"  {RED}✗{NC} {msg}")


def warn(msg: str) -> None:
    global warn_count
    warn_count += 1
    print(f"  {YELLOW}⚠{NC} {msg}")


def dim(msg: str) -> None:
    print(f"  {DIM}-{NC} {DIM}{msg}{NC}")


def header(msg: str) -> None:
    print(f"\n{BOLD}{CYAN}{'=' * 60}{NC}")
    print(f"{BOLD}{CYAN}  {msg}{NC}")
    print(f"{BOLD}{CYAN}{'=' * 60}{NC}")


def subheader(msg: str) -> None:
    print(f"\n  {BOLD}{msg}{NC}")


def fmt(val: float, decimals: int = 2) -> str:
    if abs(val) >= 1000:
        return f"{val:,.{decimals}f}"
    return f"{val:.{decimals}f}"


def check(label: str, actual: float, expected: float, tolerance_pct: float = 5.0,
          unit: str = "", show_usd: bool = False, usd_price: float = 0,
          min_only: bool = False) -> None:
    """Check actual vs expected with tolerance. Pass/fail when expected > 0.

    min_only: only fail if actual is BELOW expected (minus tolerance).
              Having more than expected is always OK (e.g., LP residuals).
    """
    if expected <= 0:
        dim(f"{label}: {fmt(actual)} {unit}")
        return
    diff_pct = ((actual - expected) / expected) * 100
    suffix = ""
    if show_usd and usd_price > 0:
        suffix = f"  (${fmt(actual * usd_price)})"
    detail = f"{label}: {fmt(actual)} {unit} (expected {fmt(expected)}, {diff_pct:+.1f}%){suffix}"
    if min_only and diff_pct >= -tolerance_pct:
        ok(detail)
    elif abs(diff_pct) <= tolerance_pct:
        ok(detail)
    elif min_only and diff_pct >= -tolerance_pct * 2:
        warn(detail)
    elif abs(diff_pct) <= tolerance_pct * 2:
        warn(detail)
    else:
        fail(detail)


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
            os.environ.setdefault(key, os.path.expandvars(value))


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


def eth_call(to: str, data: str, rpc: str = "http://127.0.0.1:8545") -> str | None:
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "eth_call",
        "params": [{"to": to, "data": data}, "latest"],
    }).encode()
    try:
        req = Request(rpc, data=payload,
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
        return result.get("result")
    except Exception:
        return None


def eth_balance(address: str, rpc: str = "http://127.0.0.1:8545") -> float | None:
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "eth_getBalance",
        "params": [address, "latest"],
    }).encode()
    try:
        req = Request(rpc, data=payload,
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
        return int(result.get("result", "0x0"), 16) / 1e18
    except Exception:
        return None


def erc20_balance(token: str, account: str, decimals: int) -> float | None:
    padded = account.lower().replace("0x", "").zfill(64)
    result = eth_call(token, f"0x70a08231{padded}")
    if result is None:
        return None
    return int(result, 16) / (10 ** decimals)


def get_zephyr_balances(port: int) -> dict[str, float]:
    result = rpc_call(f"http://127.0.0.1:{port}", "get_balance",
                      {"account_index": 0, "all_assets": True})
    if not result:
        return {}
    balances = {}
    for entry in result.get("balances", []):
        asset = entry.get("asset_type", "")
        unlocked = int(entry.get("unlocked_balance", 0))
        balances[asset] = unlocked / ATOMIC
    return balances


def get_pool_slot0(state_view: str, pool_id: str) -> tuple[int, int] | None:
    pid = pool_id.replace("0x", "")
    result = eth_call(state_view, f"0xc815641c{pid}")
    if result is None or result == "0x":
        return None
    hex_data = result.replace("0x", "")
    if len(hex_data) < 128:
        return None
    sqrt_price = int(hex_data[0:64], 16)
    tick_raw = int(hex_data[64:128], 16)
    if tick_raw >= 2**255:
        tick_raw -= 2**256
    return sqrt_price, tick_raw


def get_pool_liquidity(state_view: str, pool_id: str) -> int | None:
    pid = pool_id.replace("0x", "")
    result = eth_call(state_view, f"0xfa6793d5{pid}")
    if result is None or result == "0x":
        return None
    return int(result, 16)


def sqrt_price_to_price(sqrt_price_x96: int, dec0: int, dec1: int) -> float:
    price = (sqrt_price_x96 / (2**96)) ** 2
    price *= 10 ** (dec0 - dec1)
    return price


def load_addresses() -> dict:
    path = ORCH_DIR / "config" / "addresses.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def compute_expected_usd(oracle_usd: dict[str, float]) -> dict[str, float]:
    """Compute expected USD prices from oracle, same as patch-pool-prices.py."""
    return {
        "ZEPH": oracle_usd.get("ZEPH", 0),
        "ZSD": oracle_usd.get("ZSD", 0),
        "ZRS": oracle_usd.get("ZRS", 0),
        "ZYS": oracle_usd.get("ZYS", 0),
        "USDT": 1.0,
        "USDC": 1.0,
    }


# ── Report Sections ─────────────────────────────────────────────────────

def report_oracle_prices(target_price: float | None) -> dict[str, float]:
    header("Oracle Prices")

    result = rpc_call("http://127.0.0.1:47767", "get_reserve_info")
    if not result:
        fail("Could not query daemon get_reserve_info")
        return {}

    pr = result.get("pr", {})
    spot_h = float(pr.get("spot", 0)) / ATOMIC
    stable_h = float(pr.get("stable", 0)) / ATOMIC
    reserve_h = float(pr.get("reserve", 0)) / ATOMIC
    yield_h = float(pr.get("yield_price", 0)) / ATOMIC

    zeph_usd = spot_h
    zsd_usd = stable_h * zeph_usd
    zrs_usd = reserve_h * zeph_usd if reserve_h > 0 else 0
    zys_usd = yield_h * zsd_usd if yield_h > 0 else 0

    subheader("Daemon Pricing Report")
    dim(f"spot        = {spot_h}  →  ZEPH = ${fmt(zeph_usd, 4)}")
    dim(f"stable      = {stable_h}  →  ZSD  = ${fmt(zsd_usd, 4)}")
    dim(f"reserve     = {reserve_h}  →  ZRS  = ${fmt(zrs_usd, 4)}")
    dim(f"yield_price = {yield_h}  →  ZYS  = ${fmt(zys_usd, 4)}")

    if target_price is not None:
        subheader("vs Target Price")
        check("ZEPH spot", zeph_usd, target_price, tolerance_pct=1, unit="USD")

    # Fake oracle
    subheader("Fake Oracle (:5555)")
    try:
        req = Request("http://127.0.0.1:5555/status", headers={})
        with urlopen(req, timeout=3) as resp:
            oracle_data = json.loads(resp.read())
        oracle_spot = oracle_data.get("spot", 0)
        oracle_usd = oracle_spot / ATOMIC
        if abs(oracle_usd - zeph_usd) < 0.01:
            ok(f"Oracle spot = ${fmt(oracle_usd, 4)} (matches daemon)")
        else:
            warn(f"Oracle spot = ${fmt(oracle_usd, 4)} (daemon has ${fmt(zeph_usd, 4)})")
        dim(f"mode = {oracle_data.get('mode', '?')}")
    except Exception:
        warn("Could not reach fake oracle on :5555")

    # Reserve ratio
    rr = result.get("reserve_ratio", 0)
    try:
        rr_val = int(rr) / ATOMIC
        dim(f"Reserve ratio = {fmt(rr_val, 4)}")
    except (ValueError, TypeError):
        dim(f"Reserve ratio = {rr}")

    return {"ZEPH": zeph_usd, "ZSD": zsd_usd, "ZRS": zrs_usd, "ZYS": zys_usd}


def report_pool_prices(addresses: dict, usd_prices: dict[str, float],
                       target_price: float | None) -> None:
    header("Pool Prices (Uniswap V4)")

    state_view = addresses.get("contracts", {}).get("stateView")
    pools = addresses.get("pools", {})
    tokens = addresses.get("tokens", {})

    if not state_view or not pools:
        fail("Missing stateView or pools in addresses.json")
        return

    zeph = usd_prices.get("ZEPH", 0)
    zsd = usd_prices.get("ZSD", 0)
    zrs = usd_prices.get("ZRS", 0)
    zys = usd_prices.get("ZYS", 0)

    # Expected pool prices from daemon oracle (always compare)
    expected = {}
    if zsd > 0:
        expected["wZEPH-wZSD"] = zeph / zsd
        expected["wZSD-USDT"] = zsd / 1.0
    if zsd > 0 and zys > 0:
        expected["wZYS-wZSD"] = zys / zsd
    if zeph > 0 and zrs > 0:
        expected["wZRS-wZEPH"] = zrs / zeph
    expected["USDT-USDC"] = 1.0

    # Token decimals
    dec_map: dict[str, int] = {}
    for info in tokens.values():
        addr = info.get("address", "").lower()
        dec_map[addr] = info.get("decimals", 18)

    subheader("Pool Price vs Oracle")
    print(f"  {'Pool':<14} {'On-Chain':>10} {'Oracle':>10} {'Config':>10} {'Diff':>8}  {'Status'}")
    print(f"  {'─'*14} {'─'*10} {'─'*10} {'─'*10} {'─'*8}  {'─'*6}")

    for pool_name, pool_data in pools.items():
        pool_id = pool_data.get("state", {}).get("poolId")
        plan = pool_data.get("plan", {})
        config_price = plan.get("pricing", {}).get("price", "?")

        if not pool_id:
            dim(f"{pool_name}: no poolId in state")
            continue

        slot0 = get_pool_slot0(state_view, pool_id)
        if slot0 is None:
            fail(f"{pool_name}: could not read slot0")
            continue

        sqrt_price, tick = slot0
        if sqrt_price == 0:
            fail(f"{pool_name}: sqrtPriceX96 = 0 (uninitialized)")
            continue

        # Get decimals from state.currency0/currency1
        c0_addr = pool_data.get("state", {}).get("currency0", "").lower()
        c1_addr = pool_data.get("state", {}).get("currency1", "").lower()
        dec0 = dec_map.get(c0_addr, 12)
        dec1 = dec_map.get(c1_addr, 12)

        # raw_price = token1_per_token0 (V4 convention)
        raw_price = sqrt_price_to_price(sqrt_price, dec0, dec1)

        # Pool name is "BASE-QUOTE". Determine if base is currency0 or currency1.
        # Find base token address from plan or by matching symbols.
        base_sym = pool_name.split("-")[0]
        # Check if base symbol matches currency1 (higher address)
        c1_sym = ""
        for tname, tinfo in tokens.items():
            if tinfo.get("address", "").lower() == c1_addr:
                c1_sym = tname
                break

        if base_sym == c1_sym:
            onchain_price = 1.0 / raw_price if raw_price > 0 else 0
        else:
            onchain_price = raw_price

        exp = expected.get(pool_name, 0)
        if exp > 0:
            diff_pct = ((onchain_price - exp) / exp) * 100
            diff_str = f"{diff_pct:+.1f}%"
            if abs(diff_pct) < 2:
                status = f"{GREEN}OK{NC}"
            elif abs(diff_pct) < 10:
                status = f"{YELLOW}~{NC}"
            else:
                status = f"{RED}BAD{NC}"
        else:
            diff_str = "N/A"
            status = f"{DIM}?{NC}"

        print(f"  {pool_name:<14} {onchain_price:>10.4f} {exp:>10.4f} {config_price:>10} {diff_str:>8}  {status}")

    # Liquidity
    subheader("Pool Liquidity")
    for pool_name, pool_data in pools.items():
        pool_id = pool_data.get("state", {}).get("poolId")
        if not pool_id:
            continue
        liq = get_pool_liquidity(state_view, pool_id)
        if liq is not None and liq > 0:
            ok(f"{pool_name}: liquidity = {liq:,}")
        elif liq == 0:
            fail(f"{pool_name}: liquidity = 0 (empty pool)")
        else:
            warn(f"{pool_name}: could not read liquidity")


def report_evm_wallets(addresses: dict, usd_prices: dict[str, float],
                       target_price: float | None) -> None:
    header("EVM Wallet Balances")

    tokens = addresses.get("tokens", {})
    engine_addr = os.environ.get("ENGINE_ADDRESS", "")
    cex_addr = os.environ.get("CEX_ADDRESS", "")
    deployer_addr = os.environ.get("DEPLOYER_ADDRESS", "")

    zeph = usd_prices.get("ZEPH", 0)
    zsd = usd_prices.get("ZSD", 0)
    zrs = usd_prices.get("ZRS", 0)
    zys = usd_prices.get("ZYS", 0)

    usd_map = {
        "wZEPH": zeph, "wZSD": zsd, "wZRS": zrs, "wZYS": zys,
        "USDT": 1.0, "USDC": 1.0,
    }

    # Expected engine EVM balances (from spec: $10K per asset)
    engine_expected = {}
    if target_price is not None:
        if zeph > 0:
            engine_expected["wZEPH"] = INVENTORY_TARGET_USD / zeph
        if zsd > 0:
            engine_expected["wZSD"] = INVENTORY_TARGET_USD / zsd
        if zrs > 0:
            engine_expected["wZRS"] = INVENTORY_TARGET_USD / zrs
        if zys > 0:
            engine_expected["wZYS"] = INVENTORY_TARGET_USD / zys
        engine_expected["USDT"] = 10_000
        engine_expected["USDC"] = 10_000

    cex_expected = {}
    if target_price is not None:
        cex_expected["USDT"] = 10_000

    wallets = [
        ("Engine", engine_addr, engine_expected),
        ("CEX", cex_addr, cex_expected),
        ("Deployer", deployer_addr, {}),
    ]

    for wallet_name, addr, expectations in wallets:
        if not addr:
            continue
        subheader(f"{wallet_name} ({addr[:10]}...{addr[-6:]})")

        total_usd = 0.0
        for token_name in ["wZEPH", "wZSD", "wZRS", "wZYS", "USDT", "USDC"]:
            info = tokens.get(token_name)
            if not info:
                continue
            bal = erc20_balance(info["address"], addr, info["decimals"])
            if bal is None:
                print(f"    {token_name:<8} {'?':>14}")
                continue
            price = usd_map.get(token_name, 0)
            usd_val = bal * price
            total_usd += usd_val

            exp = expectations.get(token_name, 0)
            if exp > 0:
                # min_only: LP residuals mean engine often has MORE than
                # budgeted inventory; only fail if below expected.
                check(token_name, bal, exp, tolerance_pct=10,
                      show_usd=True, usd_price=price, min_only=True)
            elif bal > 0.01:
                print(f"    {token_name:<8} {fmt(bal):>14}  (${fmt(usd_val)})")
            else:
                print(f"    {token_name:<8} {fmt(bal):>14}  {DIM}--{NC}")

        # ETH
        eth = eth_balance(addr)
        if eth is not None:
            if wallet_name == "Engine" and target_price is not None:
                check("ETH", eth, 10.0, tolerance_pct=5)
            elif wallet_name == "CEX" and target_price is not None:
                check("ETH", eth, 10.0, tolerance_pct=5)
            else:
                print(f"    {'ETH':<8} {fmt(eth, 4):>14}")
        dim(f"Total tokens ≈ ${fmt(total_usd)}")


def report_zephyr_wallets(usd_prices: dict[str, float],
                          target_price: float | None) -> None:
    header("Zephyr Wallet Balances")

    zeph = usd_prices.get("ZEPH", 0)
    zsd = usd_prices.get("ZSD", 0)
    zrs = usd_prices.get("ZRS", 0)
    zys = usd_prices.get("ZYS", 0)
    price_map = {"ZPH": zeph, "ZSD": zsd, "ZRS": zrs, "ZYS": zys}

    # Engine expected: $10K inventory + 5K margin per asset
    engine_expected = {}
    if target_price is not None:
        if zeph > 0:
            engine_expected["ZPH"] = (INVENTORY_TARGET_USD / zeph) + MARGIN_TOKENS
        if zsd > 0:
            engine_expected["ZSD"] = (INVENTORY_TARGET_USD / zsd) + MARGIN_TOKENS
        if zrs > 0:
            engine_expected["ZRS"] = (INVENTORY_TARGET_USD / zrs) + MARGIN_TOKENS
        if zys > 0:
            engine_expected["ZYS"] = (INVENTORY_TARGET_USD / zys) + MARGIN_TOKENS

    cex_expected = {}
    if target_price is not None and zeph > 0:
        cex_expected["ZPH"] = INVENTORY_TARGET_USD / zeph

    wallets = [
        ("Engine", 48771, engine_expected),
        ("CEX", 48772, cex_expected),
        ("Gov", 48769, {}),
        ("Bridge", 48770, {}),
        ("Test", 48768, {}),
    ]

    for name, port, expectations in wallets:
        subheader(f"{name} Wallet (:{port})")
        balances = get_zephyr_balances(port)
        if not balances:
            fail("Could not query wallet")
            continue

        total_usd = 0.0
        for asset in ["ZPH", "ZSD", "ZRS", "ZYS"]:
            bal = balances.get(asset, 0)
            usd_val = bal * price_map.get(asset, 0)
            total_usd += usd_val

            exp = expectations.get(asset, 0)
            if exp > 0:
                check(asset, bal, exp, tolerance_pct=15,
                      show_usd=True, usd_price=price_map.get(asset, 0))
            elif bal > 0:
                print(f"    {asset:<6} {fmt(bal):>14}  (${fmt(usd_val)})")
            else:
                print(f"    {asset:<6} {fmt(bal):>14}  {DIM}--{NC}")

        dim(f"Total ≈ ${fmt(total_usd)}")


def report_seeding_config(addresses: dict, usd_prices: dict[str, float]) -> None:
    header("Seeding Config (addresses.json)")

    seeding = addresses.get("seeding", {})
    if not seeding:
        warn("No seeding section in addresses.json")
        return

    stored_prices = seeding.get("usdPrices", {})
    subheader("Stored USD Prices (at time of dev-setup)")
    for asset in ["ZEPH", "ZSD", "ZRS", "ZYS"]:
        stored = stored_prices.get(asset, 0)
        current = usd_prices.get(asset, 0)
        if current > 0 and abs(stored - current) / current < 0.02:
            ok(f"{asset}: ${stored:.4f}")
        elif current > 0:
            warn(f"{asset}: stored=${stored:.4f}  current=${current:.4f}")
        else:
            dim(f"{asset}: ${stored:.4f}")

    subheader("Wrap Amounts")
    for asset, amt in seeding.get("wrapAmounts", {}).items():
        dim(f"{asset}: {fmt(amt)}")

    subheader("Gov → Engine Funding")
    for asset, amt in seeding.get("funding", {}).items():
        dim(f"{asset}: {fmt(amt)}")

    dim(f"CEX ZPH: {seeding.get('cexZeph', '?')}")
    dim(f"Inventory target: ${seeding.get('inventory', 0):,}")


def report_chain_info() -> None:
    header("Chain Info")

    result = rpc_call("http://127.0.0.1:47767", "get_info")
    if result:
        ok(f"Daemon height: {result.get('height', '?')}")
    else:
        fail("Could not query daemon")

    try:
        payload = json.dumps({"jsonrpc": "2.0", "id": 1,
                               "method": "eth_blockNumber", "params": []}).encode()
        req = Request("http://127.0.0.1:8545", data=payload,
                      headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        block = int(data.get("result", "0x0"), 16)
        ok(f"Anvil block: {block}")
    except Exception:
        fail("Could not query Anvil")


# ── Main ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Post-setup sanity check")
    parser.add_argument("--price", type=float, default=None,
                        help="Target ZEPH price in USD (e.g. 1.50). "
                             "Enables pass/fail checks against spec targets.")
    args = parser.parse_args()

    load_env()

    mode = f"checking against ${fmt(args.price, 2)} spec" if args.price else "report only"
    print(f"\n{BOLD}Bridge Orchestration — Post-Setup Sanity Check{NC}")
    print(f"{DIM}Spec: docs/plans/pool-seeding-targets.md  ({mode}){NC}")

    addresses = load_addresses()
    if not addresses:
        fail("config/addresses.json not found — has dev-setup been run?")
        sys.exit(1)

    report_chain_info()
    usd_prices = report_oracle_prices(args.price)
    if not usd_prices:
        fail("Cannot continue without oracle prices")
        sys.exit(1)

    report_seeding_config(addresses, usd_prices)
    report_pool_prices(addresses, usd_prices, args.price)
    report_evm_wallets(addresses, usd_prices, args.price)
    report_zephyr_wallets(usd_prices, args.price)

    # Summary
    print(f"\n{BOLD}{'─' * 60}{NC}")
    if args.price:
        total = pass_count + fail_count + warn_count
        print(f"  {GREEN}✓ {pass_count} passed{NC}  "
              f"{RED}✗ {fail_count} failed{NC}  "
              f"{YELLOW}⚠ {warn_count} warnings{NC}  "
              f"({total} checks)")
        if fail_count > 0:
            print(f"  {RED}{BOLD}FAIL{NC}")
        elif warn_count > 0:
            print(f"  {YELLOW}{BOLD}WARN{NC}")
        else:
            print(f"  {GREEN}{BOLD}PASS{NC}")
    else:
        print(f"{DIM}  Report complete. Use --price <usd> to enable pass/fail checks.{NC}")
    print()


if __name__ == "__main__":
    main()
