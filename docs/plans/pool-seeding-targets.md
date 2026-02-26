# Pool Seeding & Inventory Targets for Bridge Engine

Target ending state for devnet pools, wallets, and engine inventory after `make dev-setup`.

---

## Asset Prices (Correct Economics $1.50 ZEPH example:)

Oracle raw values (atomic / 1e12): 
- zeph spot=1.50
- zsd=0.6667 zeph ($1)
- zrs=0.5116 zeph ($0.76)
- zys=1.0130 ZSD ($1.031)

Zeph price needs to be able to be set to whatever we want.
The target is ~10k usd worth of coins in the engine inventory in all venues

---

## Oracle Price Model

Zephyr uses 12 decimal places (1 ZEPH = 10^12 atomic units). All oracle prices are stored in atomic units; divide by 10^12 to get the human-readable value.

The daemon's `get_reserve_info` RPC returns a `pr` (pricing report) object:

| Field | Unit | Meaning | Example (atomic) | Human |
|-------|------|---------|-------------------|-------|
| `spot` | USD | ZEPH price in USD | 1,500,000,000,000 | $1.50 |
| `stable` | ZEPH | ZSD price in ZEPH | 666,700,000,000 | 0.6667 ZEPH |
| `reserve` | ZEPH | ZRS price in ZEPH | 511,600,000,000 | 0.5116 ZEPH |
| `yield_price` | ZSD | ZYS price in ZSD | 1,013,000,000,000 | 1.0130 ZSD |

**USD price derivation** (implemented in `scripts/patch-pool-prices.py`):

```
ZEPH_USD = spot / 1e12
ZSD_USD  = (stable / 1e12) * ZEPH_USD
ZRS_USD  = (reserve / 1e12) * ZEPH_USD
ZYS_USD  = (yield_price / 1e12) * ZSD_USD
```

There is no display factor. `spot / 1e12` IS the USD price directly.

### Default Prices

| Stage | ZEPH Price | Set By |
|-------|-----------|--------|
| `make dev-init` | **$2.00** | `DEFAULT_SPOT` in `devnet-init/init.sh` + fake oracle default in `server.js` |
| `make dev-setup` | **$1.50** | `dev-setup.sh` calls `/set-price` at start |

The oracle price can be changed at any time via `make set-price PRICE=<usd>`. All seeding amounts are computed dynamically from whatever the oracle reports at the time `dev-setup` runs.

---

## Pool Pricing

All pool prices are expressed as **quote-per-base** (matching `pricing.price` in `addresses.json`). Computed dynamically by `patch-pool-prices.py` from daemon oracle prices.

| Pool | Base | Quote | Price Formula | Example @ $1.50 |
|------|------|-------|---------------|------------------|
| USDT-USDC | USDT | USDC | Fixed | 1.0000 |
| wZSD-USDT | wZSD | USDT | `ZSD_USD / 1.00` | 1.0000 |
| wZEPH-wZSD | wZEPH | wZSD | `ZEPH_USD / ZSD_USD` | 1.5000 |
| wZYS-wZSD | wZYS | wZSD | `ZYS_USD / ZSD_USD` | 1.0130 |
| wZRS-wZEPH | wZRS | wZEPH | `ZRS_USD / ZEPH_USD` | 0.5116 |

---

## Pool Liquidity Budgets

Budget is per side in USD. Token amounts are computed dynamically from oracle USD prices.

| Pool | Budget/Side | Base Amount | Quote Amount | Funded By |
|------|-------------|-------------|--------------|-----------|
| USDT-USDC | $500K | 500,000 USDT | 500,000 USDC | Anvil deployer (not engine) |
| wZSD-USDT | $50K | `$50K / ZSD_USD` wZSD | 50,000 USDT | Engine |
| wZEPH-wZSD | $50K | `$50K / ZEPH_USD` wZEPH | `$50K / ZSD_USD` wZSD | Engine |
| wZYS-wZSD | $30K | `$30K / ZYS_USD` wZYS | `$30K / ZSD_USD` wZSD | Engine |
| wZRS-wZEPH | $30K | `$30K / ZRS_USD` wZRS | `$30K / ZEPH_USD` wZEPH | Engine |

---

## Engine Inventory

Target: **$10K USD** per asset per venue.

| Venue | Asset | Amount | USD |
|-------|-------|--------|-----|
| Zephyr (.n) | ZPH | `$10K / ZEPH_USD` | $10,000 |
| Zephyr (.n) | ZSD | `$10K / ZSD_USD` | $10,000 |
| Zephyr (.n) | ZRS | `$10K / ZRS_USD` | $10,000 |
| Zephyr (.n) | ZYS | `$10K / ZYS_USD` | $10,000 |
| EVM (.e) | wZEPH | `$10K / ZEPH_USD` | $10,000 |
| EVM (.e) | wZSD | `$10K / ZSD_USD` | $10,000 |
| EVM (.e) | wZRS | `$10K / ZRS_USD` | $10,000 |
| EVM (.e) | wZYS | `$10K / ZYS_USD` | $10,000 |
| EVM (.e) | USDT | 10,000 | $10,000 |
| EVM (.e) | USDC | 10,000 | $10,000 |
| EVM (.e) | ETH | 10 | Gas |
| CEX (.x) | ZPH | `$10K / ZEPH_USD` | $10,000 |
| CEX (.x) | USDT | 10,000 | $10,000 |

Total: ~$130K (13 positions x $10K).

---

## Funding Flow

All Zephyr amounts below are dynamic. `$V` = `$10K / ASSET_USD` for each asset. Margin = 5,000 tokens per native asset (tx fee buffer).

### Gov -> Engine Zephyr Wallet

| Asset | Wrap | Native Inv | CEX | Margin | Total |
|-------|------|------------|-----|--------|-------|
| ZPH | LP base + LP quote | $V | $V | 5,000 | wrap + 2$V + 5K |
| ZSD | LP quotes | $V | -- | 5,000 | wrap + $V + 5K |
| ZRS | LP base | $V | -- | 5,000 | wrap + $V + 5K |
| ZYS | LP base | $V | -- | 5,000 | wrap + $V + 5K |

Wrap amounts (LP needs + EVM inventory):
```
wrap_zeph = ($50K + $30K + $10K) / ZEPH_USD    # wZEPH-wZSD base + wZRS-wZEPH quote + EVM inv
wrap_zsd  = ($50K + $50K + $30K + $10K) / ZSD_USD  # LP quote contributions + EVM inv
wrap_zrs  = ($30K + $10K) / ZRS_USD             # wZRS-wZEPH base + EVM inv
wrap_zys  = ($30K + $10K) / ZYS_USD             # wZYS-wZSD base + EVM inv
```

### Engine Wraps Through Bridge

Each wrap sends native asset to bridge subaddress, claims wrapped ERC-20 on EVM. Wrapped tokens are split between LP seeding and EVM inventory.

### Engine -> CEX Transfers

| Route | Asset | Amount | Purpose |
|-------|-------|--------|---------|
| Zephyr transfer | ZPH | `$10K / ZEPH_USD` | CEX ZEPH inventory |
| EVM transfer | USDT | 10,000 | CEX USDT inventory |

### Anvil Deployer Mints

| Token | To | Amount | Purpose |
|-------|-----|--------|---------|
| USDT | Engine | 60,000 | 50K wZSD-USDT LP quote + 10K inventory |
| USDC | Engine | 10,000 | Inventory |
| USDT | Deployer LP | 500,000 | USDT-USDC pool (direct, not engine) |
| USDC | Deployer LP | 500,000 | USDT-USDC pool (direct, not engine) |
| ETH | Engine | 10 | Gas |
| ETH | CEX | 10 | Gas |

Note: CEX USDT ($10K) comes from the engine's own EVM inventory transfer, not from deployer.

---

## Post-Setup Wallet Balances

### Engine Zephyr Wallet

| Asset | Balance | Composition |
|-------|---------|-------------|
| ZPH | inv + margin | `$10K/ZEPH_USD` + 5K |
| ZSD | inv + margin | `$10K/ZSD_USD` + 5K |
| ZRS | inv + margin | `$10K/ZRS_USD` + 5K |
| ZYS | inv + margin | `$10K/ZYS_USD` + 5K |

### Engine EVM Wallet

| Token | Balance | Notes |
|-------|---------|-------|
| wZEPH | `$10K / ZEPH_USD` | Inventory |
| wZSD | `$10K / ZSD_USD` | Inventory |
| wZRS | `$10K / ZRS_USD` | Inventory |
| wZYS | `$10K / ZYS_USD` | Inventory |
| USDT | 10,000 | After CEX transfer |
| USDC | 10,000 | Inventory |
| ETH | ~10 | Gas |

### CEX Wallets

| Wallet | Asset | Balance | Source |
|--------|-------|---------|--------|
| Zephyr (48772) | ZPH | `$10K / ZEPH_USD` | Engine Zephyr transfer |
| EVM | USDT | 10,000 | Engine EVM transfer |
| EVM | ETH | 10 | Anvil deployer |

---

## Implementation Files

| File | Role |
|------|------|
| `scripts/patch-pool-prices.py` | Queries daemon, computes pool prices + seeding config, writes to `addresses.json` |
| `scripts/deploy-contracts.sh` | Deploys EVM contracts, seeds USDT-USDC pool from deployer |
| `scripts/seed-via-engine.sh` | Orchestrates gov funding, wraps, LP seeding, CEX transfers |
| `scripts/seed-liquidity.py` | Gov -> engine native asset transfers |
| `config/addresses.json` | Carries pool plans, budgets, and `seeding` section (written by `patch-pool-prices.py`) |
| `docker/fake-oracle/server.js` | Oracle price API; default $2.00 on container start |
| `docker/devnet-init/init.sh` | Sets oracle to $2.00 during `dev-init` |
| `scripts/dev-setup.sh` | Sets oracle to $1.50 at start of `dev-setup`, then runs full pipeline |
