# Zephyr Bridge Engine Reference

An arbitrage and liquidity management bot for the Zephyr Protocol. Monitors price discrepancies across three venues (EVM/Uniswap V4, native Zephyr chain, CEX/MEXC), executes profitable trades with risk controls, and manages liquidity positions.

**Repo:** `zephyr-bridge-engine/`

---

## Execution Modes

| Operation | paper | devnet | live |
|-----------|-------|--------|------|
| EVM swap | Simulated | Real (local Anvil) | Real |
| LP mint/burn/collect | Simulated | Real (local Anvil) | Real |
| Native mint/redeem | Simulated | Real (local daemon) | Real |
| Wrap/unwrap | Simulated | Real (local bridge) | Real |
| CEX trade | Simulated | CexWalletClient (accounting-only) | MexcLiveClient (real API) |
| CEX deposit/withdraw | Simulated | Real (local wallets) | Real (MEXC API) |
| Balance reads | Real | Real | Real |

CLI: `pnpm engine:run --mode devnet --strategies arb --interval 5000`

---

## Strategies

| # | Strategy | ID | File | Purpose |
|---|----------|----|------|---------|
| 1 | Arbitrage | `arb` | `src/domain/strategies/arbitrage.ts` | Cross-venue price discrepancy trading across 8 routes |
| 2 | Rebalancer | `rebalance` | `src/domain/strategies/rebalancer.ts` | Maintains target asset allocation across venues |
| 3 | Peg Keeper | `peg` | `src/domain/strategies/pegkeeper.ts` | Monitors ZSD $1.00 peg on EVM pools |
| 4 | LP Manager | `lp` | `src/domain/strategies/lpmanager.ts` | Manages Uniswap V4 liquidity positions |

All strategies implement the same interface:
- `evaluate()` — returns opportunities
- `buildPlan()` — converts to executable steps
- `shouldAutoExecute()` — determines if manual approval is needed

Registered in `STRATEGY_REGISTRY`, selected via CLI `--strategies arb,peg`.

---

## 1. Arbitrage Strategy

The largest strategy (~27 supporting files: 23 in `src/domain/arbitrage/` + 4 in `src/domain/strategies/arbitrage*.ts`).

### 8 Arb Legs (4 assets x 2 directions)

| # | Asset | Direction | Open (EVM swap) | Close Native | Close CEX | Trigger |
|---|-------|-----------|------------------|-------------|-----------|---------|
| 1 | ZEPH | evm_discount | WZSD.e -> WZEPH.e | ZEPH.n -> ZSD.n (mint) | ZEPH.x -> USDT.x | 100 bps |
| 2 | ZEPH | evm_premium | WZEPH.e -> WZSD.e | ZSD.n -> ZEPH.n (redeem) | USDT.x -> ZEPH.x | 100 bps |
| 3 | ZSD | evm_discount | USDT.e -> WZSD.e | WZSD.e -> ZSD.n (unwrap) | -- | 12 bps |
| 4 | ZSD | evm_premium | WZSD.e -> USDT.e | ZEPH.n -> ZSD.n (mint) | -- | 12 bps |
| 5 | ZRS | evm_discount | WZEPH.e -> WZRS.e | ZRS.n -> ZEPH.n (redeem) | -- | 100 bps |
| 6 | ZRS | evm_premium | WZRS.e -> WZEPH.e | ZEPH.n -> ZRS.n (mint) | -- | 100 bps |
| 7 | ZYS | evm_discount | WZSD.e -> WZYS.e | ZYS.n -> ZSD.n (redeem) | -- | 30 bps |
| 8 | ZYS | evm_premium | WZYS.e -> WZSD.e | ZSD.n -> ZYS.n (mint) | -- | 30 bps |

- Only ZEPH has CEX close paths (ZSD, ZRS, ZYS are native-only)
- ZSD close is trivial: evm_discount just unwraps (always works), evm_premium needs ZSD minting (RR-gated)
- Gap must exceed trigger threshold AND net P&L must be positive after fees

### Fee Estimates (on $1000 clip)

| Component | ZSD legs | ZEPH/ZRS/ZYS legs |
|-----------|----------|-------------------|
| EVM swap | $0.30 (3 bps) | $3.00 (30 bps) |
| Bridge | $10 | $10 |
| Native conversion | $1 (ZSD/ZYS) / $10 (ZRS) | varies |
| CEX (ZEPH only) | -- | $1 |
| Gas | ~$5 | ~$5 |
| **Total** | **~$16** | **~$19-28** |

### Default Clip Sizes (from `DEFAULT_CLIP_USD`)

| Asset | Clip Size |
|-------|-----------|
| ZEPH | $500 |
| ZSD | $1,000 |
| ZRS | $250 |
| ZYS | $500 |

### Spot/MA Spread Gate

The engine checks the spread between spot price and moving average before auto-executing:

| Condition | Result |
|-----------|--------|
| Any asset: abs(spread) > 500 bps | **Block all** (manual approval required) |
| ZEPH/ZRS evm_discount + spread > +300 bps | **Block** (hurts redemption) |
| ZEPH/ZRS evm_premium + spread < -300 bps | **Block** (hurts minting) |
| ZSD/ZYS | Unaffected by spread |

Constants: `SPREAD_BLOCK_BPS = 500`, `SPREAD_WARNING_BPS = 300` (in `arbitrage.approval.ts`)

### RR Mode Auto-Execution Gate

Per-asset rules in `shouldAutoExecuteForRRMode()`:

| Asset | Normal (>=4x) | Defensive (2x-4x) | Crisis (<2x) |
|-------|---------------|-------------------|---------------|
| ZEPH | auto | auto if PnL >= $20 | blocked |
| ZSD | auto | auto | blocked |
| ZRS | auto | blocked | blocked |
| ZYS | auto | auto | auto (evm_discount only) |

---

## 2. Rebalancer Strategy

Maintains target asset allocation across venues.

### Target Allocations

| Asset | EVM | Native | CEX |
|-------|-----|--------|-----|
| ZEPH | 30% | 50% | 20% |
| ZSD | 60% | 30% | 10% |
| ZRS | 40% | 60% | 0% |
| ZYS | 50% | 50% | 0% |
| USDT | 70% | 0% | 30% |

### Venue Transitions (6 paths)

1. EVM -> Native (unwrap)
2. Native -> EVM (wrap)
3. EVM -> CEX (unwrap + deposit)
4. Native -> CEX (deposit)
5. CEX -> Native (withdraw)
6. CEX -> EVM (withdraw + wrap)

### Parameters

- **Trigger:** deviation > 10 percentage points from target
- **Max movement:** 25% of venue balance per cycle
- **Auto-execution:** Normal RR mode only

---

## 3. Peg Keeper Strategy

Monitors ZSD $1.00 peg on the USDT-WZSD EVM pool.

### Thresholds by RR Mode

| RR Mode | Min Trigger | Base Clip | Max Clip (>200 bps) |
|---------|-------------|-----------|---------------------|
| Normal | 30 bps | $500 | $2,000 |
| Defensive | 100 bps | $500 | $2,000 |
| Crisis | 300 bps | $500 | $2,000 |

**Directions:** `zsd_premium` (sell WZSD for USDT), `zsd_discount` (buy WZSD with USDT)

---

## 4. LP Manager Strategy

Manages Uniswap V4 liquidity positions. Tracks active positions in Postgres via Prisma.

### Actions

`collect_fees`, `reposition`, `adjust_range`, `add_liquidity`, `remove_liquidity`

### ZSD Range Recommendations by RR Mode

| Mode | Lower | Upper |
|------|-------|-------|
| Normal | $0.98 | $1.02 |
| Defensive | $0.90 | $1.05 |
| Crisis | $0.50 | $1.10 |

- Recommends repositioning if existing range drifts >10% from RR-mode recommendation
- No automatic tightening/widening of existing positions
- **Fee collection:** opportunity triggers at >$50 accumulated fees, auto-approved when >$10 (always true since threshold is $50+)
- Only fee collection auto-executes; all other actions require manual approval

---

## Protocol-Level Restrictions

Hard constraints from the Zephyr daemon, mirrored in `src/domain/zephyr/reserve.ts:150-160`.

### Reserve Ratio (RR) Modes

| Mode | RR Range | Characteristics |
|------|----------|----------------|
| Normal | >= 4x (400%) | All operations open |
| Defensive | 2x - 4x (200-400%) | ZSD/ZRS minting restricted |
| Crisis | < 2x (200%) | Most minting/redeeming blocked |

### ZSD Policy

| Operation | Condition | Gate |
|-----------|-----------|------|
| Mint (ZEPH -> ZSD) | RR >= 4x AND RR_MA >= 4x | `policy.zsd.mintable` |
| Redeem (ZSD -> ZEPH) | Always | `true` |

### ZRS Policy

| Operation | Condition | Gate |
|-----------|-----------|------|
| Mint (ZEPH -> ZRS) | 4x <= RR <= 8x AND 4x <= RR_MA <= 8x | `policy.zrs.mintable` |
| Redeem (ZRS -> ZEPH) | RR >= 4x AND RR_MA >= 4x | `policy.zrs.redeemable` |

### ZYS Policy

| Operation | Condition | Gate |
|-----------|-----------|------|
| Mint (ZSD -> ZYS) | Always | No gate |
| Redeem (ZYS -> ZSD) | Always | No gate |

### Impact on Arb Close Paths

From `isNativeCloseAvailable()` in `arbitrage.analysis.ts`:

| Leg | Close Operation | Required Policy | Blocked When |
|-----|-----------------|-----------------|--------------|
| ZEPH evm_discount | ZSD mint | `zsd.mintable` | RR < 4x or RR_MA < 4x |
| ZEPH evm_premium | ZSD redeem | always true | Never |
| ZSD evm_discount | Unwrap | no gate | Never |
| ZSD evm_premium | ZSD mint | `zsd.mintable` | RR < 4x or RR_MA < 4x |
| ZRS evm_discount | ZRS redeem | `zrs.redeemable` | RR < 4x or RR_MA < 4x |
| ZRS evm_premium | ZRS mint | `zrs.mintable` | RR < 4x or RR_MA < 4x OR RR > 8x or RR_MA > 8x |
| ZYS evm_discount | ZYS redeem | no gate | Never |
| ZYS evm_premium | ZYS mint | no gate | Never |

---

## Combined: What Works at Each RR Level

Crossing protocol restrictions with engine auto-execution gates.

### RR >= 8x (very high collateral)

| Leg | Protocol | Engine | Net |
|-----|----------|--------|-----|
| ZEPH discount (mint ZSD) | mint open | auto | **works** |
| ZEPH premium (redeem ZSD) | always | auto | **works** |
| ZSD discount (unwrap) | always | auto | **works** |
| ZSD premium (mint ZSD) | mint open | auto | **works** |
| ZRS discount (redeem ZRS) | redeem open | auto | **works** |
| ZRS premium (mint ZRS) | **BLOCKED** (RR > 8x) | -- | **no close path** |
| ZYS discount (redeem ZYS) | always | auto | **works** |
| ZYS premium (mint ZYS) | always | auto | **works** |

7 of 8 legs work. ZRS premium has no close path.

### 4x <= RR < 8x (normal)

**All 8 legs work. All auto-execute.** This is the optimal operating range.

### 2x <= RR < 4x (defensive)

| Leg | Protocol | Engine | Net |
|-----|----------|--------|-----|
| ZEPH discount | no close (ZSD mint blocked) | -- | **dead** (unless CEX close) |
| ZEPH premium | redeem works | auto if PnL >= $20 | **conditional** |
| ZSD discount | unwrap works | auto | **works** |
| ZSD premium | no close (ZSD mint blocked) | -- | **dead** |
| ZRS discount | no close (ZRS redeem blocked) | -- | **dead** |
| ZRS premium | no close (ZRS mint blocked) | engine blocks ZRS anyway | **dead** |
| ZYS discount | redeem works | auto | **works** |
| ZYS premium | mint works | auto | **works** |

4 of 8 legs survive. ZEPH discount could use CEX close if available.

### RR < 2x (crisis)

| Leg | Protocol | Engine | Net |
|-----|----------|--------|-----|
| ZEPH discount | no close (ZSD mint blocked) | engine blocks | **dead** |
| ZEPH premium | redeem works | engine blocks | **manual only** |
| ZSD discount | unwrap works | engine blocks | **manual only** |
| ZSD premium | no close | engine blocks | **dead** |
| ZRS discount | no close | engine blocks | **dead** |
| ZRS premium | no close | engine blocks | **dead** |
| ZYS discount | redeem works | auto | **works** |
| ZYS premium | mint works | engine blocks | **manual only** |

Only ZYS evm_discount auto-executes. A few others require manual approval.

---

## LP Management Challenges

### Standard Pools

- **WZSD/USDT** — Stable rail into Zephyr ecosystem. Straightforward peg management.
- **WZEPH/WZSD** — Floating market. Below 400% RR, can't mint any ZSD.n to replenish.

### Difficult Pools

**WZYS/WZSD** — Growth stable (yield-bearing stable from ZSD yield):
- ZYS has a native price that only goes up slowly in ZSD terms (1.00 ZSD -> 1.80 ZSD over ~14 months)
- Can only get ZYS by ZSD -> ZYS conversion, so ZSD supply can be gated below 400% RR
- Pegging this pool is tricky due to the constantly appreciating native price

**WZRS/WZEPH** — Reserve share, heavily restricted:
- **400-800% RR:** Easy — no restrictions, can freely mint and redeem to peg LP price to native price. Arb pathing through native wallet and bridge wrap/unwraps.
- **RR > 800%:** ZRS shortage risk — can't mint new ZRS. Price on LP needs to be intentionally expensive because supply can't be replenished until RR drops below 800%.
- **RR < 400%:** ZRS not redeemable. Must buy at steeper and steeper discount as risk increases, waiting for RR recovery.
- Near the 400% and 800% boundaries: institute leeway with loose restrictions, then increase pool fee or position liquidity to sell at increasing premium / buy at increasing discount as supply gets scarce.

---

## Inventory System

### Architecture

- `src/domain/inventory/balances.ts` — Core snapshot builder
- `src/domain/inventory/valuations.ts` — USD valuations
- `InventorySnapshot` contains `balances` (per-asset-per-venue) and `totals` (per-base-asset aggregates)

### Asset IDs by Venue

| Asset | EVM | Native | CEX |
|-------|-----|--------|-----|
| ZEPH | WZEPH.e | ZEPH.n | ZEPH.x |
| ZSD | WZSD.e | ZSD.n | -- |
| ZRS | WZRS.e | ZRS.n | -- |
| ZYS | WZYS.e | ZYS.n | -- |
| USDT | USDT.e | -- | USDT.x |

### Balance Sources

- **EVM:** On-chain ERC-20 `balanceOf()` calls
- **Native:** Zephyr wallet RPC `get_balance` (requires `all_assets: true`)
- **CEX:** CexWalletClient snapshot (devnet) or MEXC API (live)

---

## Engine Loop

```
┌─────────────────────────────────────────────────┐
│  Engine Loop (every --interval ms, default 5s)  │
├─────────────────────────────────────────────────┤
│ 1. Refresh state (Zephyr chain, EVM pools, CEX) │
│ 2. For each enabled strategy:                   │
│    a. evaluate() → opportunities                │
│    b. For each opportunity:                      │
│       i.  buildPlan() → steps                   │
│       ii. shouldAutoExecute() → auto/manual     │
│       iii. If auto: execute steps sequentially   │
│       iv. If manual: queue for dashboard         │
│ 3. Record results to Postgres                   │
│ 4. Sleep until next interval                    │
└─────────────────────────────────────────────────┘
```

---

## Key Files

| File | Purpose |
|------|---------|
| `apps/engine/src/cli.ts` | CLI entry point, parses `--mode`, `--strategies`, `--interval` |
| `apps/engine/src/engine.ts` | Main `BridgeEngine` class, orchestrates the loop |
| `apps/engine/src/engine.execution.ts` | Plan execution with risk checks |
| `src/domain/execution/types.ts` | Core `ExecutionMode` type (`paper \| devnet \| live`) |
| `src/domain/execution/execution.dispatch.ts` | Routes steps to venue handlers |
| `src/domain/execution/factory.ts` | Creates venue executors based on mode |
| `src/domain/strategies/types.ts` | `Strategy` interface, `EngineConfig`, `RRMode` |
| `src/domain/strategies/arbitrage.ts` | Arb strategy: evaluate + buildPlan |
| `src/domain/strategies/arbitrage.analysis.ts` | Leg analysis, close path availability |
| `src/domain/strategies/arbitrage.approval.ts` | Spread + RR auto-execution gates |
| `src/domain/arbitrage/routing.ts` | `ARB_DEFS` — 8 leg definitions |
| `src/domain/arbitrage/constants.ts` | Fee rates, trigger thresholds, clip sizes |
| `src/domain/zephyr/reserve.ts` | Reserve state parsing, policy gates |
| `src/domain/inventory/balances.ts` | Inventory snapshot builder |
| `src/services/cex/client.ts` | CexWalletClient (devnet CEX) |
| `src/services/mexc/live.ts` | MexcLiveClient (production CEX) |

---

## Devnet Testing

### Setup

```bash
# In bridge-orchestration:
make dev-init && make dev-setup && make dev
# Engine starts via Procfile.dev with: --mode devnet --strategies arb --interval 5000
```

### Manipulating Pool Prices

To trigger arb opportunities, manipulate Uniswap V4 pool prices using cast swaps against Anvil. See `scripts/patch-pool-prices.py` for programmatic manipulation.

### Testing RR Modes

```bash
make set-scenario SCENARIO=normal      # RR ~500%
make set-scenario SCENARIO=defensive   # RR ~300%
make set-scenario SCENARIO=crisis      # RR ~150%
make set-scenario SCENARIO=high-rr     # RR ~900%
```

Or set exact oracle prices:
```bash
make set-price PRICE=0.50   # Lower ZEPH price -> lower RR
make set-price PRICE=2.00   # Higher ZEPH price -> higher RR
```

### Test Matrix Summary

Every intersection of {8 arb legs} x {4 RR levels (>8x, 4-8x, 2-4x, <2x)} x {spread conditions} x {inventory states} is a distinct test scenario. The combined matrices above show which legs are available at each level.
