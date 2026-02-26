#!/usr/bin/env python3
"""Patch pool pricing in addresses.json to match the devnet oracle.

Queries the Zephyr daemon for get_reserve_info and computes correct pool
prices from the oracle's ReservePriceReport.  Updates the pricing.price
field for each pool in:
  - FOUNDRY_REPO_PATH/.forge-snapshots/addresses.json  (used by deploy-contracts.sh)
  - ORCH_DIR/config/addresses.json                     (used by engine + seed scripts)

Also computes dynamic seeding budgets and wrap amounts from oracle USD
prices. Writes a "seeding" section to addresses.json so downstream scripts
(seed-liquidity.py, seed-via-engine.sh, engine cli.ts) can read them.

Run this BEFORE deploy-contracts.sh so pools are created with correct
initial sqrtPriceX96 values.  dev-setup.sh calls this automatically.

Prices are in "quote per base" format matching the pool plan structure:
  - wZEPH-wZSD:  ZEPH_USD / ZSD_USD  (e.g. 1.50 at $1.50 oracle)
  - wZSD-USDT:   ZSD_USD / 1.00      (e.g. 1.00 for pegged stable)
  - wZYS-wZSD:   ZYS_USD / ZSD_USD   (yield stable / stable)
  - wZRS-wZEPH:  ZRS_USD / ZEPH_USD  (reserve / zeph)
  - USDT-USDC:   always 1.0000
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent
ORCH_DIR = SCRIPT_DIR.parent

# Atomic unit divisor (1e12)
ATOMIC = 1_000_000_000_000


def load_env():
    """Load .env from ORCH_DIR."""
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


def get_reserve_info(daemon_url: str) -> dict:
    """Query daemon get_reserve_info, return the result dict."""
    payload = json.dumps({
        "jsonrpc": "2.0",
        "id": "0",
        "method": "get_reserve_info",
    }).encode()
    req = Request(
        f"{daemon_url}/json_rpc",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read())
    result = data.get("result", {})
    if not result:
        raise RuntimeError(f"get_reserve_info returned no result: {data}")
    return result


def compute_pool_prices(pr: dict) -> tuple[dict[str, str], dict[str, float]]:
    """Compute pool prices from ReservePriceReport.

    Oracle fields (all raw atomic, divide by ATOMIC to get human):
      spot          - ZEPH USD price (e.g. 15.0 = $15.00)
      stable        - ZSD rate in ZEPH (e.g. 0.06667 ZEPH per ZSD)
      reserve       - ZRS rate in ZEPH
      yield_price   - ZYS rate in ZSD

    Returns:
      (pool_prices, usd_prices) — pool prices as strings, USD prices as floats.
    """
    spot_h = float(pr.get("spot", 0)) / ATOMIC
    stable_h = float(pr.get("stable", 0)) / ATOMIC
    reserve_h = float(pr.get("reserve", 0)) / ATOMIC
    yield_h = float(pr.get("yield_price", 0)) / ATOMIC

    if spot_h <= 0 or stable_h <= 0:
        raise ValueError(f"Invalid oracle: spot_h={spot_h}, stable_h={stable_h}")

    # USD prices — spot IS the USD price (no display factor)
    # stable/reserve are rates denominated in ZEPH, yield_price in ZSD
    zeph_usd = spot_h
    zsd_usd = stable_h * zeph_usd
    zrs_usd = reserve_h * zeph_usd if reserve_h > 0 else 0
    zys_usd = yield_h * zsd_usd if yield_h > 0 else 0

    usd_prices = {
        "ZEPH": zeph_usd,
        "ZSD": zsd_usd,
        "ZRS": zrs_usd,
        "ZYS": zys_usd,
    }

    # Pool prices = quote-per-base in USD terms
    prices: dict[str, str] = {"USDT-USDC": "1.0000"}

    prices["wZSD-USDT"] = f"{zsd_usd:.4f}"
    prices["wZEPH-wZSD"] = f"{zeph_usd / zsd_usd:.4f}" if zsd_usd > 0 else "1.0000"
    if zys_usd > 0 and zsd_usd > 0:
        prices["wZYS-wZSD"] = f"{zys_usd / zsd_usd:.4f}"
    if zrs_usd > 0 and zeph_usd > 0:
        prices["wZRS-wZEPH"] = f"{zrs_usd / zeph_usd:.4f}"

    return prices, usd_prices


def compute_seeding_config(usd_prices: dict[str, float]) -> dict:
    """Compute all seeding amounts from USD prices.

    Budget targets (from pool-seeding-targets.md):
      USDT-USDC: $500K/side (deployer)
      wZSD-USDT: $50K/side
      wZEPH-wZSD: $50K/side
      wZYS-wZSD: $30K/side
      wZRS-wZEPH: $30K/side
    Inventory: $10K per asset-venue
    Margin: 5K per native asset
    """
    zeph = usd_prices["ZEPH"]
    zsd = usd_prices["ZSD"]
    zrs = usd_prices["ZRS"]
    zys = usd_prices["ZYS"]

    # Pool budgets in quote token (human units)
    budgets = {
        "USDT-USDC": {"totalQuoteHuman": "500000", "quoteSymbol": "USDC"},
        "wZSD-USDT": {"totalQuoteHuman": str(int(50000 / 1.0)), "quoteSymbol": "USDT"},
        "wZEPH-wZSD": {"totalQuoteHuman": str(int(50000 / zsd)), "quoteSymbol": "wZSD"},
        "wZYS-wZSD": {"totalQuoteHuman": str(int(30000 / zsd)), "quoteSymbol": "wZSD"},
        "wZRS-wZEPH": {"totalQuoteHuman": str(int(30000 / zeph)), "quoteSymbol": "wZEPH"},
    }

    # Wrap amounts = LP needs + EVM inventory ($10K per asset)
    inv = 10000  # $10K per asset-venue
    wrap_zeph = int((50000 + 30000 + inv) / zeph)  # wZEPH-wZSD LP base + wZRS-wZEPH LP quote + inventory
    wrap_zsd = int((50000 + 50000 + 30000 + inv) / zsd)  # LP quotes + inventory
    wrap_zrs = int((30000 + inv) / zrs)
    wrap_zys = int((30000 + inv) / zys)

    # Native inventory ($10K per asset) + CEX ZPH ($10K)
    native_inv_zeph = int(inv / zeph)
    native_inv_zsd = int(inv / zsd)
    native_inv_zrs = int(inv / zrs)
    native_inv_zys = int(inv / zys)
    cex_zeph = int(inv / zeph)

    margin = 5000  # per asset, for tx fees

    # Total gov -> engine funding
    funding = {
        "ZPH": wrap_zeph + native_inv_zeph + margin,  # cex_zeph sent from gov directly
        "ZSD": wrap_zsd + native_inv_zsd + margin,
        "ZRS": wrap_zrs + native_inv_zrs + margin,
        "ZYS": wrap_zys + native_inv_zys + margin,
        # USDT/USDC are minted by deployer, not transferred from gov
        "USDT": int(50000 + inv),  # wZSD-USDT LP quote + engine inventory
        "USDC": inv,               # engine inventory only
    }

    return {
        "budgets": budgets,
        "wrapAmounts": {"ZPH": wrap_zeph, "ZSD": wrap_zsd, "ZRS": wrap_zrs, "ZYS": wrap_zys},
        "funding": funding,
        "cexZeph": cex_zeph,
        "inventory": inv,
        "usdPrices": {
            "ZEPH": round(zeph, 4),
            "ZSD": round(zsd, 4),
            "ZRS": round(zrs, 4),
            "ZYS": round(zys, 4),
        },
    }


def patch_addresses_json(filepath: Path, prices: dict[str, str],
                         seeding: dict | None = None,
                         budgets: dict | None = None) -> int:
    """Patch pricing.price (and optionally budgets + seeding) in addresses.json.

    Returns the number of pools patched.
    """
    if not filepath.exists():
        print(f"  SKIP: {filepath} not found")
        return 0

    data = json.loads(filepath.read_text())
    pools = data.get("pools", {})
    patched = 0

    for pool_name, new_price in prices.items():
        pool = pools.get(pool_name)
        if not pool:
            continue
        plan = pool.get("plan")
        if not plan:
            continue
        pricing = plan.get("pricing")
        if not pricing:
            continue

        old_price = pricing.get("price", "?")
        if old_price != new_price:
            pricing["price"] = new_price
            print(f"  {pool_name}: {old_price} -> {new_price}")
            patched += 1
        else:
            print(f"  {pool_name}: {new_price} (already correct)")

    # Patch pool budgets from seeding config
    if budgets:
        for pool_name, budget_info in budgets.items():
            pool = pools.get(pool_name)
            if not pool:
                continue
            plan = pool.get("plan")
            if not plan:
                continue
            budget = plan.get("budget")
            if not budget:
                continue
            old_budget = budget.get("totalQuoteHuman", "?")
            new_budget = budget_info["totalQuoteHuman"]
            if old_budget != new_budget:
                budget["totalQuoteHuman"] = new_budget
                print(f"  {pool_name} budget: {old_budget} -> {new_budget}")
                patched += 1

    # Write seeding config as top-level key
    if seeding:
        data["seeding"] = seeding
        patched += 1

    if patched > 0:
        filepath.write_text(json.dumps(data, indent=2) + "\n")

    return patched


def main():
    load_env()

    daemon_url = os.environ.get("ZEPHYR_D_RPC_URL", "http://127.0.0.1:47767")
    foundry_path = os.environ.get("FOUNDRY_REPO_PATH", "")

    if not foundry_path:
        print("ERROR: FOUNDRY_REPO_PATH not set")
        sys.exit(1)

    foundry_addr = Path(foundry_path) / ".forge-snapshots" / "addresses.json"
    orch_addr = ORCH_DIR / "config" / "addresses.json"

    print("Patching pool prices to match devnet oracle...")
    print(f"  Daemon: {daemon_url}")

    # Query daemon for current prices
    try:
        reserve_info = get_reserve_info(daemon_url)
    except Exception as e:
        print(f"  WARNING: Could not query daemon: {e}")
        print("  Skipping price patch (pools will use existing prices)")
        return

    pr = reserve_info.get("pr", {})
    if not pr:
        print("  WARNING: No pricing report in reserve_info")
        return

    # Show oracle USD prices
    spot_h = float(pr.get("spot", 0)) / ATOMIC
    zeph_usd = spot_h
    zsd_usd = (float(pr.get("stable", 0)) / ATOMIC) * zeph_usd
    zrs_usd = (float(pr.get("reserve", 0)) / ATOMIC) * zeph_usd
    zys_usd = (float(pr.get("yield_price", 0)) / ATOMIC) * zsd_usd
    print(f"  Oracle USD: ZEPH=${zeph_usd:.4f} ZSD=${zsd_usd:.4f} "
          f"ZRS=${zrs_usd:.4f} ZYS=${zys_usd:.4f}")

    # Compute pool prices and USD prices
    prices, usd_prices = compute_pool_prices(pr)
    print(f"  Computed {len(prices)} pool prices")

    # Compute dynamic seeding config
    seeding = compute_seeding_config(usd_prices)
    budgets = seeding["budgets"]
    print(f"  Seeding config: wrap ZPH={seeding['wrapAmounts']['ZPH']} "
          f"ZSD={seeding['wrapAmounts']['ZSD']} "
          f"ZRS={seeding['wrapAmounts']['ZRS']} "
          f"ZYS={seeding['wrapAmounts']['ZYS']}")
    print(f"  Funding: ZPH={seeding['funding']['ZPH']} "
          f"ZSD={seeding['funding']['ZSD']} "
          f"ZRS={seeding['funding']['ZRS']} "
          f"ZYS={seeding['funding']['ZYS']}")

    # Patch foundry addresses.json (prices + budgets + seeding)
    print(f"\n  Patching {foundry_addr}:")
    patched = patch_addresses_json(foundry_addr, prices, seeding=seeding, budgets=budgets)
    if patched > 0:
        print(f"  Patched {patched} item(s) in foundry addresses.json")
    else:
        print("  All prices already correct")

    # Patch orch config/addresses.json if it exists
    if orch_addr.exists():
        print(f"\n  Patching {orch_addr}:")
        patched2 = patch_addresses_json(orch_addr, prices, seeding=seeding, budgets=budgets)
        if patched2 > 0:
            print(f"  Patched {patched2} item(s) in orch addresses.json")
    else:
        print(f"\n  SKIP: {orch_addr} not found (will be created by deploy-contracts.sh)")


if __name__ == "__main__":
    main()
