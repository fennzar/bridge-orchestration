# Engine Test Scope

Exhaustive test cases for the Zephyr Bridge Engine. Every strategy, every code path, every RR mode.

---

## Conventions

- **Slug format:** `CATEGORY-NN` (e.g., `PRE-01`, `ARB-03`)
- **Sub-tests:** `PARENT-NNx` (e.g., `ARB-03a`, `ARB-03b`)
- **Expected results** describe the _what_, not the _how_

---

## PRE: Prerequisites & State Building

Tests that validate the foundation everything else depends on. If these fail, nothing downstream is trustworthy.

### PRE-01: reserve-state-parsing

Parse raw daemon `get_reserve_info` into `ReserveState`.

- Feed raw atomic values (1e12 scale) through `mapReserveInfo()`
- Verify `reserveRatio` is decimal (e.g., `5.0` not `500`)
- Verify `reserveRatioMovingAverage` is decimal
- Verify `zephPriceUsd` is correctly derived from atomic `spot / 1e12`
- Verify all rate pairs have `spot`, `movingAverage`, `mint`, `redeem`
- Verify ZRS `spotUSD` is cross-multiplied (`zrsPerZeph * zephUsd`)
- Verify ZYS `spotUSD` is cross-multiplied (`zysPerZsd * zsdUsd`)

### PRE-02: reserve-policy-gates

Verify protocol policy gates match daemon behavior exactly.

#### PRE-02a: zsd-mintable-boundary

- RR = 4.0, RR_MA = 4.0 -> `policy.zsd.mintable = true`
- RR = 3.99, RR_MA = 4.0 -> `policy.zsd.mintable = false`
- RR = 4.0, RR_MA = 3.99 -> `policy.zsd.mintable = false`
- RR = 3.99, RR_MA = 3.99 -> `policy.zsd.mintable = false`
- RR = 8.0, RR_MA = 8.0 -> `policy.zsd.mintable = true` (no upper bound)

#### PRE-02b: zsd-redeemable

- Any RR value -> `policy.zsd.redeemable = true` (always)

#### PRE-02c: zrs-mintable-boundary

- RR = 4.0, RR_MA = 4.0 -> `policy.zrs.mintable = true`
- RR = 8.0, RR_MA = 8.0 -> `policy.zrs.mintable = true`
- RR = 8.01, RR_MA = 8.0 -> `policy.zrs.mintable = false` (upper bound)
- RR = 8.0, RR_MA = 8.01 -> `policy.zrs.mintable = false`
- RR = 3.99, RR_MA = 4.0 -> `policy.zrs.mintable = false` (lower bound)
- RR = 4.0, RR_MA = 3.99 -> `policy.zrs.mintable = false`

#### PRE-02d: zrs-redeemable-boundary

- RR = 4.0, RR_MA = 4.0 -> `policy.zrs.redeemable = true`
- RR = 3.99, RR_MA = 4.0 -> `policy.zrs.redeemable = false`
- RR = 4.0, RR_MA = 3.99 -> `policy.zrs.redeemable = false`

### PRE-03: rr-mode-determination

Verify `determineRRMode()` boundaries.

- RR = 4.0 -> `"normal"`
- RR = 3.99 -> `"defensive"`
- RR = 2.0 -> `"defensive"`
- RR = 1.99 -> `"crisis"`
- RR = 0 -> `"crisis"`
- RR = 100 -> `"normal"`

### PRE-04: spot-ma-spread-calculation

Verify `calculateSpotMaSpreadBps()`.

- spot = 0.80, ma = 0.75 -> positive spread (~667 bps)
- spot = 0.70, ma = 0.75 -> negative spread (~-667 bps)
- spot = 0.75, ma = 0.75 -> 0 bps
- spot = 0.75, ma = 0 -> 0 bps (division by zero guard)

### PRE-05: global-state-building

Verify `createNormalModeState()` factory produces valid state with all 4 pools, CEX market, and sane defaults.

- State has all 4 EVM pools keyed correctly
- State has CEX market for ZEPH_USDT
- Reserve data is internally consistent
- Pool prices are finite and positive

### PRE-06: state-for-rr-mode

Verify `createStateForRRMode()` for each mode.

- `"normal"` -> RR = 5.0, all policies open
- `"defensive"` -> RR = 3.0, ZSD mint blocked, ZRS mint+redeem blocked
- `"crisis"` -> RR = 1.5, same policy gates as defensive

### PRE-07: inventory-snapshot-building

Verify `createMockInventorySnapshot()` correctly maps asset IDs to base totals.

- WZEPH.e + ZEPH.n balances sum into ZEPH total
- USDT.e + USDT.x balances sum into USDT total
- Zero balances are handled without error

### PRE-08: asset-decimal-mapping

Verify asset decimal constants are correct across the codebase.

- USDT.e / USDT.x = 6 decimals
- ZEPH.x = 8 decimals (different from native!)
- All `.n` and `.e` variants of ZEPH/ZSD/ZRS/ZYS = 12 decimals
- ETH.e = 18 decimals

### PRE-09: engine-config-defaults

Verify `buildTestConfig()` and engine defaults.

- Default mode = `"devnet"`
- Default `manualApproval` = false
- Default `minProfitUsd` = 1.0
- Default `maxOperationsPerCycle` = 5
- Default `loopIntervalMs` = 30000

---

## ARB: Arbitrage Strategy

### ARB-E: Evaluate (Opportunity Detection)

#### ARB-E01: no-reserve-data

- Pass state with `zephyr.reserve = undefined`
- Expected: empty opportunities, warning "No reserve data available"

#### ARB-E02: no-evm-state

- Pass state with `evm = undefined`
- Expected: all 8 legs return `hasOpportunity: false` with "No market data" trigger

#### ARB-E03: no-cex-state

- Pass state with `cex = undefined`
- Expected: ZEPH legs still detect opportunities (native close available), ZSD/ZRS/ZYS legs unaffected

#### ARB-E04: all-prices-aligned

- Set all pool prices to match oracle/native prices exactly
- Expected: zero opportunities, all 8 legs show "aligned" with gap below threshold

#### ARB-E05: zeph-evm-discount

- Set WZEPH/WZSD pool price below oracle by >100 bps (WZEPH cheap on EVM)
- Expected: ZEPH evm_discount opportunity detected with correct gap, urgency, and PnL

#### ARB-E06: zeph-evm-premium

- Set WZEPH/WZSD pool price above oracle by >100 bps (WZEPH expensive on EVM)
- Expected: ZEPH evm_premium opportunity detected

#### ARB-E07: zsd-evm-discount

- Set WZSD/USDT pool price below $1.00 by >12 bps
- Expected: ZSD evm_discount opportunity detected

#### ARB-E08: zsd-evm-premium

- Set WZSD/USDT pool price above $1.00 by >12 bps
- Expected: ZSD evm_premium opportunity detected

#### ARB-E09: zrs-evm-discount

- Set WZRS/WZEPH pool price below native ZRS/ZEPH rate by >100 bps
- Expected: ZRS evm_discount opportunity detected

#### ARB-E10: zrs-evm-premium

- Set WZRS/WZEPH pool price above native ZRS/ZEPH rate by >100 bps
- Expected: ZRS evm_premium opportunity detected

#### ARB-E11: zys-evm-discount

- Set WZYS/WZSD pool price below native ZYS/ZSD rate by >30 bps
- Expected: ZYS evm_discount opportunity detected

#### ARB-E12: zys-evm-premium

- Set WZYS/WZSD pool price above native ZYS/ZSD rate by >30 bps
- Expected: ZYS evm_premium opportunity detected

#### ARB-E13: gap-below-threshold

- Set each asset pool price to gap just under its threshold (99 bps for ZEPH, 11 bps for ZSD, 29 bps for ZYS, 99 bps for ZRS)
- Expected: no opportunities detected for any asset

#### ARB-E14: gap-at-exact-threshold

- Set each asset pool price to gap exactly at threshold
- Expected: opportunity detected only if net PnL after fees is positive

#### ARB-E15: gap-above-threshold-but-unprofitable

- Set pool gap just above threshold but below breakeven after fees
- Expected: `hasOpportunity = false` because `netPnl <= 0`

#### ARB-E16: multiple-simultaneous-opportunities

- Set 3+ pools to have exploitable gaps simultaneously
- Expected: multiple opportunities returned in single evaluate() call

#### ARB-E17: ma-fallback-to-spot

- Set `reserve.rates.zeph.movingAverage = null`
- Expected: spot price used as fallback for MA, no crash

#### ARB-E18: defensive-mode-warnings

- Set RR = 3.0 (defensive)
- Expected: warning "RR in defensive mode" present

#### ARB-E19: crisis-mode-warnings

- Set RR = 1.5 (crisis)
- Expected: warning "RR in crisis mode" present

#### ARB-E20: large-spread-warning

- Set spot/MA spread > 500 bps
- Expected: warning about large spread present in evaluation

#### ARB-E21: metrics-gap-injection

- Create state where ZEPH pool has a measurable gap
- Expected: metrics object contains `ZEPH_gapBps` with correct value

#### ARB-E22: urgency-levels

- Create opportunities with PnL = $30, $60, $150
- Expected: urgency = `"low"`, `"medium"`, `"high"` respectively

---

### ARB-C: Close Path Availability

#### ARB-C01: zeph-discount-native-close-normal

- RR = 5.0 (normal), ZSD mintable
- Expected: ZEPH evm_discount native close available (ZEPH.n -> ZSD.n mint)

#### ARB-C02: zeph-discount-native-close-blocked

- RR = 3.0 (defensive), ZSD mint blocked
- Expected: ZEPH evm_discount native close unavailable

#### ARB-C03: zeph-discount-cex-fallback

- Native close blocked, CEX state present
- Expected: CEX close path used (ZEPH.x -> USDT.x trade)

#### ARB-C04: zeph-discount-no-close-path

- Native close blocked AND no CEX state
- Expected: `hasOpportunity = false`, trigger mentions RR mode

#### ARB-C05: zeph-premium-always-available

- Any RR mode (normal, defensive, crisis)
- Expected: ZEPH evm_premium native close always available (ZSD redeem is unconditional)

#### ARB-C06: zsd-discount-always-available

- Any RR mode
- Expected: ZSD evm_discount close always available (unwrap, no conversion)

#### ARB-C07: zsd-premium-normal

- RR = 5.0, ZSD mintable
- Expected: ZSD evm_premium native close available

#### ARB-C08: zsd-premium-blocked

- RR = 3.0, ZSD mint blocked
- Expected: ZSD evm_premium has no close path (no CEX fallback for ZSD)

#### ARB-C09: zrs-discount-normal

- RR = 5.0, ZRS redeemable
- Expected: ZRS evm_discount native close available

#### ARB-C10: zrs-discount-defensive

- RR = 3.0, ZRS redeem blocked
- Expected: ZRS evm_discount has no close path

#### ARB-C11: zrs-premium-normal

- RR = 5.0 (4 <= RR <= 8), ZRS mintable
- Expected: ZRS evm_premium native close available

#### ARB-C12: zrs-premium-high-rr

- RR = 9.0 (> 8x), ZRS mint blocked
- Expected: ZRS evm_premium has no close path

#### ARB-C13: zrs-premium-defensive

- RR = 3.0, ZRS mint blocked
- Expected: ZRS evm_premium has no close path

#### ARB-C14: zys-always-available

- Any RR mode (normal, defensive, crisis)
- Expected: ZYS evm_discount and evm_premium native close always available

---

### ARB-S: Spread Gate

#### ARB-S01: spread-under-300-bps

- Set spot/MA spread = 200 bps
- Expected: all arb legs pass spread check

#### ARB-S02: spread-at-500-bps-blanket-block

- Set abs(spot/MA spread) = 500 bps
- Expected: ALL legs blocked regardless of asset or direction

#### ARB-S03: spread-above-500-bps

- Set abs(spot/MA spread) = 600 bps
- Expected: all legs blocked

#### ARB-S04: zeph-discount-positive-spread-300

- ZEPH evm_discount with spot/MA spread = +350 bps (spot > MA)
- Expected: blocked ("positive spread hurts redemption rate")

#### ARB-S05: zeph-premium-negative-spread-300

- ZEPH evm_premium with spot/MA spread = -350 bps (spot < MA)
- Expected: blocked ("negative spread hurts mint rate")

#### ARB-S06: zeph-discount-negative-spread-ok

- ZEPH evm_discount with spot/MA spread = -350 bps
- Expected: passes (negative spread is fine for discount direction)

#### ARB-S07: zeph-premium-positive-spread-ok

- ZEPH evm_premium with spot/MA spread = +350 bps
- Expected: passes (positive spread is fine for premium direction)

#### ARB-S08: zrs-same-directional-rules

- ZRS evm_discount + positive 350 bps -> blocked
- ZRS evm_premium + negative 350 bps -> blocked
- ZRS evm_discount + negative 350 bps -> passes
- ZRS evm_premium + positive 350 bps -> passes

#### ARB-S09: zsd-immune-to-directional

- ZSD evm_discount with spread = +400 bps -> passes (under 500 blanket)
- ZSD evm_premium with spread = -400 bps -> passes

#### ARB-S10: zys-immune-to-directional

- ZYS evm_discount with spread = +400 bps -> passes
- ZYS evm_premium with spread = -400 bps -> passes

---

### ARB-A: Auto-Execution Gate (RR Mode)

#### ARB-A01: normal-mode-all-auto

- RR mode = normal, all 8 legs
- Expected: all 8 return `shouldAutoExecute = true`

#### ARB-A02: manual-approval-overrides

- config.manualApproval = true, any RR mode
- Expected: `shouldAutoExecute = false` for all legs

#### ARB-A03: min-profit-gate

- PnL = $0.50, config.minProfitUsd = 1.0
- Expected: `shouldAutoExecute = false`

#### ARB-A04: min-profit-passes

- PnL = $1.50, config.minProfitUsd = 1.0
- Expected: continues to spread/RR checks (not blocked by profit gate)

#### ARB-A05: defensive-zeph-low-profit

- Defensive mode, ZEPH arb, PnL = $15
- Expected: `shouldAutoExecute = false` (below $20 threshold)

#### ARB-A06: defensive-zeph-high-profit

- Defensive mode, ZEPH arb, PnL = $25
- Expected: `shouldAutoExecute = true`

#### ARB-A07: defensive-zsd-auto

- Defensive mode, ZSD arb, any positive PnL
- Expected: `shouldAutoExecute = true`

#### ARB-A08: defensive-zrs-blocked

- Defensive mode, ZRS arb, any PnL
- Expected: `shouldAutoExecute = false`

#### ARB-A09: defensive-zys-auto

- Defensive mode, ZYS arb, any positive PnL
- Expected: `shouldAutoExecute = true`

#### ARB-A10: crisis-all-blocked-except-zys-discount

- Crisis mode, all 8 legs
- Expected: only ZYS evm_discount returns `true`; all others return `false`

#### ARB-A11: crisis-zys-premium-blocked

- Crisis mode, ZYS evm_premium
- Expected: `shouldAutoExecute = false`

#### ARB-A12: unknown-rr-mode-blocked

- Pass `rrMode = undefined`
- Expected: `shouldAutoExecute = false`

---

### ARB-P: Plan Building

#### ARB-P01: basic-plan-structure

- Build plan for ZEPH evm_discount in normal mode
- Expected: plan has `id`, `strategy = "arb"`, `opportunity`, `steps`, `estimatedCost`, `estimatedDuration`, `reserveRatio`, `spotMaSpreadBps`

#### ARB-P02: native-close-selected

- Normal mode, native close available
- Expected: close steps use native operations (nativeMint/nativeRedeem)

#### ARB-P03: cex-close-fallback

- Defensive mode, ZEPH discount, native close blocked, CEX available
- Expected: close steps use CEX operations (tradeCEX)

#### ARB-P04: no-matching-leg

- Pass opportunity with invalid asset/direction combo
- Expected: `buildPlan()` returns null, logs warning

#### ARB-P05: no-reserve-data

- Pass state with no reserve
- Expected: plan built with `reserveRatio = 0`, `spotMaSpreadBps = 0`

#### ARB-P06: clip-sizing-zeph

- ZEPH at $0.75
- Expected: $500 clip = ~667 ZEPH (500 / 0.75), converted to atomic units

#### ARB-P07: clip-sizing-zsd

- ZSD at $1.00
- Expected: $1000 clip = 1000 ZSD

#### ARB-P08: clip-sizing-zrs

- ZRS at $0.75
- Expected: $250 clip = ~333 ZRS

#### ARB-P09: clip-sizing-zys

- ZYS at $1.10
- Expected: $500 clip = ~454 ZYS

#### ARB-P10: clip-sizing-unknown-asset

- Unknown asset with no price data
- Expected: falls back to $500 clip, price defaults to $1.00

#### ARB-P11: negative-pnl-cost-estimation

- Opportunity with expectedPnl = -5
- Expected: estimatedCost = 5 (abs of negative PnL)

#### ARB-P12: positive-pnl-cost-estimation

- Opportunity with expectedPnl = 50
- Expected: estimatedCost = 10 (flat default)

---

### ARB-F: Fee Estimation

#### ARB-F01: zsd-leg-fees

- ZSD leg with standard state
- Expected: EVM fee ~$0.30 (3 bps on $1000), bridge ~$10, native ~$1, gas ~$5, total ~$16

#### ARB-F02: zeph-leg-fees

- ZEPH leg
- Expected: EVM fee ~$3.00 (30 bps), bridge ~$10, gas ~$5, total ~$18+

#### ARB-F03: zrs-leg-fees

- ZRS leg
- Expected: native conversion fee ~$10 (100 bps), higher total

#### ARB-F04: cex-close-adds-fee

- ZEPH leg with CEX close
- Expected: additional $1 CEX fee component

#### ARB-F05: no-cex-close-no-fee

- ZSD leg (no CEX close)
- Expected: no CEX fee component in estimate

---

### ARB-M: Market Analysis

#### ARB-M01: price-map-building

- Provide full state with all pools and CEX
- Expected: `buildPricingFromState()` returns prices for all 4 assets, CEX price overrides ZEPH native price

#### ARB-M02: cex-price-override

- CEX mid-price = $0.80, native spot = $0.75
- Expected: ZEPH reference price uses CEX ($0.80), not native

#### ARB-M03: cex-unavailable-native-fallback

- No CEX state, native spot = $0.75
- Expected: ZEPH reference falls back to native spot

#### ARB-M04: gap-calculation-positive

- DEX price = $1.02, reference = $1.00
- Expected: gap = +200 bps

#### ARB-M05: gap-calculation-negative

- DEX price = $0.98, reference = $1.00
- Expected: gap = -200 bps

#### ARB-M06: gap-calculation-null-inputs

- DEX price = null or reference = 0
- Expected: gap = null (no crash)

#### ARB-M07: direction-resolution

- gap = +120 bps, threshold = 100 -> `"evm_premium"`
- gap = -120 bps, threshold = 100 -> `"evm_discount"`
- gap = +80 bps, threshold = 100 -> `"aligned"`
- gap = null -> `"aligned"`

#### ARB-M08: pool-price-lookup-direct

- Pool with base = WZSD.e, quote = USDT.e -> returns `pool.price`
- Expected: direct read of `price` field

#### ARB-M09: pool-price-lookup-inverse

- Pool with base = USDT.e, quote = WZSD.e -> returns `pool.priceInverse` (or 1/price)
- Expected: correct inversion

#### ARB-M10: pool-not-found

- Query for non-existent pool pair
- Expected: returns null

---

### ARB-X: Execution Steps Building

#### ARB-X01: evm-discount-bridge-insertion

- ZEPH evm_discount leg
- Expected: unwrap step automatically inserted between open (EVM swap) and close (native)

#### ARB-X02: evm-premium-no-bridge

- ZEPH evm_premium leg
- Expected: no automatic bridge step between open and close

#### ARB-X03: re-wrap-step

- Close step ends with `.n` asset
- Expected: wrap step appended at end to return to EVM

#### ARB-X04: output-chaining

- Multi-step execution
- Expected: each step's `amountOut` feeds as `amountIn` to next step

#### ARB-X05: swap-output-estimation

- amountIn = 1000 * 1e12, price = 0.75, feeBps = 3000 (0.3%), slippage = 50 bps
- Expected: correct deduction of fee and slippage from gross output

#### ARB-X06: swap-zero-input

- amountIn = 0
- Expected: amountOut = 0

#### ARB-X07: swap-zero-price

- price = 0
- Expected: amountOut = 0

#### ARB-X08: bridge-fee-default

- No bridge state provided
- Expected: unwrap fee defaults to 1%

#### ARB-X09: duration-estimation

- Plan with swap + unwrap + nativeMint + wrap
- Expected: sum of 30s + 20min + 2min + 20min

---

### ARB-COMBINED: Combined RR Level x Leg Matrix

These are integration-level tests combining protocol restrictions + engine gates.

#### ARB-COMBINED-01: rr-above-8x

- Set RR = 9.0
- Expected: 7 of 8 legs work (ZRS premium blocked by protocol), all auto-execute

#### ARB-COMBINED-02: rr-normal-all-work

- Set RR = 5.0
- Expected: all 8 legs work and auto-execute

#### ARB-COMBINED-03: rr-defensive-survivors

- Set RR = 3.0
- Expected: ZEPH premium (conditional), ZSD discount, ZYS discount, ZYS premium survive
- ZEPH discount dead unless CEX, ZSD premium dead, ZRS both dead

#### ARB-COMBINED-04: rr-crisis-minimal

- Set RR = 1.5
- Expected: only ZYS evm_discount auto-executes
- ZEPH premium / ZSD discount / ZYS premium are manual-only
- All others are dead (no close path)

---

## DISP: Dispatch Routing Verification

> These tests verify the engine's dispatch routing logic and factory configuration
> via API introspection (status, history, evaluate, plans). They confirm that
> operations map to the correct executor functions, but do **not** trigger or
> verify real arb trades. For real E2E execution tests, see the EXEC section below.

### DISP-P: Paper Dispatch Specs

#### DISP-P01: paper-evm-swap

- Paper mode, swapEVM step
- Expected: 0.3% slippage applied, fake txHash returned, no external calls

#### DISP-P02: paper-cex-trade

- Paper mode, tradeCEX step
- Expected: 0.1% slippage, 0.1% fee, fake orderId returned

#### DISP-P03: paper-native-mint

- Paper mode, nativeMint step
- Expected: 1:1 pass-through (or `expectedAmountOut` if set), fake txHash

#### DISP-P04: paper-native-redeem

- Paper mode, nativeRedeem step
- Expected: 1:1 pass-through, fake txHash

#### DISP-P05: paper-wrap

- Paper mode, wrap step
- Expected: 1:1 exact, no fee simulation

#### DISP-P06: paper-unwrap

- Paper mode, unwrap step
- Expected: 1:1 exact, no fee simulation

#### DISP-P07: paper-cex-deposit

- Paper mode, deposit step
- Expected: 1:1 pass-through, timing delay if simulateTiming enabled

#### DISP-P08: paper-cex-withdraw

- Paper mode, withdraw step
- Expected: 1:1, double delay for `.n` destination (withdraw + zephyrUnlock)

#### DISP-P09: paper-lp-mint

- Paper mode, lpMint step
- Expected: simulated success

#### DISP-P10: paper-lp-burn

- Paper mode, lpBurn step
- Expected: simulated success

#### DISP-P11: paper-lp-collect

- Paper mode, lpCollect step
- Expected: simulated $50 fee collection (50 * 1e6)

#### DISP-P12: paper-timing-simulation

- Paper mode with `simulateTiming = true`
- Expected: appropriate delays applied per operation type

#### DISP-P13: paper-no-timing

- Paper mode with `simulateTiming = false`
- Expected: zero delays

---

### DISP-L: Live/Devnet Dispatch Routing Specs

#### DISP-L01: evm-swap-missing-context

- Live mode, swapEVM step with `swapContext = undefined`
- Expected: error "EVM swap requires swapContext"

#### DISP-L02: evm-swap-success

- Live/devnet mode, valid swapContext
- Expected: `executors.evm.executeSwap()` called with correct params

#### DISP-L03: evm-swap-exception

- Live mode, executor throws
- Expected: `success: false`, error message captured

#### DISP-L04: native-mint-zsd

- step.to = "ZSD.n"
- Expected: `executors.zephyr.mintStable()` called

#### DISP-L05: native-mint-zrs

- step.to = "ZRS.n"
- Expected: `executors.zephyr.mintReserve()` called

#### DISP-L06: native-mint-zys

- step.to = "ZYS.n"
- Expected: `executors.zephyr.mintYield()` called

#### DISP-L07: native-mint-unknown-target

- step.to = "INVALID.n"
- Expected: error "Unknown mint target"

#### DISP-L08: native-redeem-zsd-to-zeph

- from = ZSD.n, to = ZEPH.n
- Expected: `executors.zephyr.redeemStable()` called

#### DISP-L09: native-redeem-zrs-to-zeph

- from = ZRS.n, to = ZEPH.n
- Expected: `executors.zephyr.redeemReserve()` called

#### DISP-L10: native-redeem-zys-to-zsd

- from = ZYS.n, to = ZSD.n
- Expected: `executors.zephyr.redeemYield()` called

#### DISP-L11: native-redeem-unknown-pair

- from = ZEPH.n, to = ZRS.n (reverse of mint, not a valid redeem pair)
- Expected: error "Unknown redeem pair"

#### DISP-L12: wrap-execution

- wrap step from ZEPH.n to WZEPH.e
- Expected: `executors.bridge.wrap()` called with asset="ZEPH"

#### DISP-L13: unwrap-execution

- unwrap step from WZEPH.e to ZEPH.n
- Expected: `executors.bridge.unwrap()` called, gets native address from executor

#### DISP-L14: cex-trade-zeph-buy

- from = USDT.x, to = ZEPH.x
- Expected: `getTradeSymbol()` returns "ZEPHUSDT", `getTradeSide()` returns "BUY"

#### DISP-L15: cex-trade-zeph-sell

- from = ZEPH.x, to = USDT.x
- Expected: symbol = "ZEPHUSDT", side = "SELL"

#### DISP-L16: cex-trade-unsupported-pair

- from = ZSD.x, to = USDT.x
- Expected: `getTradeSymbol()` throws (only ZEPH/USDT supported)

#### DISP-L17: cex-deposit-notification

- deposit step
- Expected: `executors.mexc.notifyDeposit()` called (no-op for CexWalletClient)

#### DISP-L18: cex-withdraw-to-native

- withdraw to `.n` address
- Expected: `getWithdrawDestination()` returns Zephyr address, double delay applied

#### DISP-L19: cex-withdraw-to-evm

- withdraw to `.e` address
- Expected: `getWithdrawDestination()` returns EVM address

#### DISP-L20: cex-withdraw-invalid-destination

- withdraw to invalid suffix
- Expected: `getWithdrawDestination()` throws

#### DISP-L21: lp-mint-missing-metadata

- lpMint with no tickLower/tickUpper/swapContext
- Expected: error "LP mint missing required metadata"

#### DISP-L22: lp-burn-missing-metadata

- lpBurn with no positionId/swapContext
- Expected: error "LP burn missing required metadata"

#### DISP-L23: lp-collect-missing-metadata

- lpCollect with no positionId/swapContext
- Expected: error "LP collect missing required metadata"

#### DISP-L24: unknown-operation

- step.op = "invalid"
- Expected: error "Unknown operation type: invalid"

---

### DISP-F: Factory Config Specs

#### DISP-F01: paper-mode-factory

- mode = "paper"
- Expected: `CexWalletClient` created (not MexcLiveClient)

#### DISP-F02: devnet-mode-factory

- mode = "devnet"
- Expected: `CexWalletClient` created

#### DISP-F03: live-mode-factory

- mode = "live", no MEXC_PAPER override
- Expected: `MexcLiveClient` created (requires API credentials)

#### DISP-F04: live-mode-paper-override

- mode = "live", MEXC_PAPER = true
- Expected: `CexWalletClient` created despite live mode

#### DISP-F05: missing-evm-key

- No EVM private key provided
- Expected: throws "EVM private key required"

---

## EXEC: Arb Execution (planned)

> **Real E2E execution tests.** These tests push pool prices past trigger thresholds,
> let the engine's auto-execution loop detect and execute the arb, then verify the
> trade completed via execution history (txHashes, step success) and balance changes.
>
> Unlike DISP tests (which verify routing via API introspection), EXEC tests verify
> the full pipeline: pool push → watcher sync → evaluate → plan → auto-execute → settle.
>
> **Requirements:**
> - Engine running in `--mode devnet` with `autoExecute=true`
> - Pool push amounts large enough to exceed trigger thresholds (100bps for ZEPH/ZRS, 12bps for ZSD, 30bps for ZYS)
> - Sufficient engine wallet inventory for the open leg
> - Sufficient deployer balance for pool manipulation
> - Fresh devnet state (token depletion from prior tests can cause BLOCKEDs)
>
> **Constraints:**
> - wZEPH-wZSD pool is thick ($50K/side) — need ~25K+ wZSD push for 100bps ZEPH premium
> - wZSD-USDT pool is thick ($500K/side) — may not be feasible for ZSD execution tests
> - wZRS-wZEPH pool is thinner — most reliable trigger for execution tests
> - Each test spends deployer tokens on pool pushes; `make dev-reset && make dev` between runs
>
> **Test pattern (all EXEC tests follow this):**
> 1. Record pre-execution balances (engine wallet + deployer)
> 2. Push pool past trigger threshold
> 3. Wait for watcher sync (~8s) + engine loop (~5s) + execution (~15s)
> 4. Query execution history for the expected trade
> 5. Verify: asset, direction, step ops, txHashes, success flags
> 6. Verify: balance changes match expected direction
> 7. Restore pool (reverse swap)

### EXEC-01: ZEPH arb execution

ZEPH uses a thick pool (wZEPH-wZSD, $50K/side) — needs ~25K+ push for 100bps. Only asset with CEX close path. Trigger: 100bps.

ZEPH premium native close (ZSD redeem) is never protocol-blocked — it works at every RR level. ZEPH discount native close (ZSD mint) requires RR >= 4x. When native close is blocked, CEX provides a fallback for both directions. In crisis the engine blocks all ZEPH auto-execution regardless.

**Current engine behavior:**

| RR Mode | evm_premium native | evm_premium CEX | evm_discount native | evm_discount CEX |
|---------|-------------------|-----------------|--------------------|--------------------|
| Normal (4x-8x) | auto | unnecessary | auto | unnecessary |
| Defensive (2x-4x) | auto if PnL >= $20 | available | dead (ZSD mint blocked) | auto (fallback) |
| Crisis (<2x) | manual only | manual only | dead | dead (engine blocks) |

> **INVESTIGATE: Can ZEPH arb ever truly be blocked?**
>
> The engine blocks ZEPH in crisis as a risk management choice, but the premium
> arb is always protocol-completable (ZSD redeem works at any RR). The crisis
> block may be overly conservative.
>
> For discount, the engine treats "ZSD mint blocked" as fatal for native close,
> falling back to CEX. But a multi-pool route could bypass native mint entirely:
> ```
> USDT → wZSD (swap on wZSD-USDT pool, no RR gate)
> wZSD → wZEPH (swap on wZEPH-wZSD pool, buying the discount)
> wZEPH → ZEPH (unwrap, always available)
> ZEPH → USDT (sell on CEX)
> ```
> This is two EVM swaps + unwrap + CEX trade — no native conversion needed.
> Viability depends on combined slippage across both pools still leaving profit.
> The wZSD-USDT pool ($500K/side) has deep liquidity, so slippage should be minimal.
>
> **Conclusion:** ZEPH may be arbitrageable at every RR level if multi-pool routing
> is implemented. Current single-pool + single-close-path logic is the limitation,
> not the protocol. Investigate after normal cases are working.

#### EXEC-01a: zeph-evm-premium-native-close

**Network state:** Normal RR (4x-8x), devnet at default oracle price ($1.50)

**Setup:**
- Engine set to manual approval mode (autoExecute=true, manualApproval=true)
  so plans are queued for approval instead of auto-executing
- Cooldown reduced to 1s (avoids engine skipping opportunities from prior runs)
- Test wallet funded with wZSD via bridge wrap flow (gov → bridge subaddress → claim)
- Test wallet pushes wZEPH-wZSD pool to premium (sells wZSD → buys wZEPH,
  making wZEPH expensive on EVM relative to oracle — >100bps gap)

**Preflight — Detection (pass/fail):**
- Wait for engine cycle (~12s: interval=5s + processing)
- Call evaluate API: does the engine detect an evm_premium opportunity for ZEPH?
- Verify gapBps exceeds the ZEPH threshold (100bps)
- Engine should NOT be spamming detections or looping — single clean detection

**Preflight — Planning (pass/fail):**
- Poll engine queue for a pending operation matching ZEPH/evm_premium
- Verify a plan ID was created and queued (not auto-executed)
- Verify plan structure: expected ops = [swapEVM, unwrap, nativeRedeem, wrap]
- Engine should have ONE queued plan — not duplicates or infinite re-queuing

**Execution — Manual approval:**
- Approve the specific operation by ID via queue API
- Wait for engine to pick up the approved plan and execute it (poll history, up to 90s)
- The engine's processApprovedQueue() runs each cycle and should execute the plan

**Trade flow (what the engine executes):**
- Open: swapEVM — sell overpriced wZEPH → buy wZSD on Uniswap V4
- Close (native path, 3 steps):
  - unwrap — burn wZSD on EVM → receive ZSD on Zephyr chain
  - nativeRedeem — convert ZSD → ZEPH (always available, no RR gate)
  - wrap — send ZEPH on Zephyr → claim wZEPH on EVM
- Net effect: engine captures the premium spread, ends up with ~same wZEPH balance

**Verification:**
- Execution record exists in history with success=true
- Record's plan shows asset=ZEPH, direction=evm_premium
- Step ops match [swapEVM, unwrap, nativeRedeem, wrap] (soft check)
- Engine's wZEPH balance approximately round-trips (within 10% tolerance)

**Note:** ZSD redeem (nativeRedeem) is always available at any RR — native close
is never protocol-blocked for evm_premium. This is the simplest execution path.

#### EXEC-01b: zeph-evm-discount-native-close

**Network state:** Normal RR (4x-8x), ZSD mintable

**Setup:**
- Engine in manual approval mode (autoExecute=true, manualApproval=true)
- Test wallet funded with wZEPH via bridge wrap flow
- Test wallet pushes wZEPH-wZSD pool to discount (sells wZEPH → buys wZSD,
  making wZEPH cheap on EVM relative to oracle — >100bps gap)

**Preflight — Detection:**
- Engine detects evm_discount opportunity for ZEPH
- Verify gapBps exceeds 100bps threshold

**Preflight — Planning:**
- Pending operation queued with expected ops
- Expected ops: [swapEVM, unwrap, nativeMint, wrap]

**Trade flow (what the engine executes):**
- Open: swapEVM — sell wZSD → buy underpriced wZEPH on Uniswap V4
- Close (native path, 3 steps):
  - unwrap — burn wZEPH on EVM → receive ZEPH on Zephyr chain
  - nativeMint — convert ZEPH → ZSD (requires RR >= 4x AND RR_MA >= 4x)
  - wrap — send ZSD on Zephyr → claim wZSD on EVM
- Net effect: engine captures the discount spread, ends with ~same wZSD balance

**Verification:**
- Execution record: success=true, asset=ZEPH, direction=evm_discount
- Step ops match [swapEVM, unwrap, nativeMint, wrap]
- Engine's wZSD balance approximately round-trips

**Note:** Unlike evm_premium (which uses nativeRedeem, always available), this path
uses nativeMint which requires normal RR. If RR drops below 4x, this path is dead
and the engine must fall back to CEX close (see EXEC-01d).

#### EXEC-01c: zeph-evm-premium-cex-close

**Network state:** Defensive RR (2x-4x)

**Setup:**
- Engine in manual approval mode
- Push wZEPH-wZSD pool to premium (>100bps)

**Key question:** When both native and CEX close paths are available, which
does the engine select? For evm_premium, native close uses nativeRedeem
(ZSD → ZEPH) which is always available at any RR. So native should be preferred.

**Preflight — Detection:**
- Engine detects evm_premium opportunity for ZEPH

**Preflight — Planning:**
- Verify the queued plan selects native close path, NOT CEX
- Expected ops: [swapEVM, unwrap, nativeRedeem, wrap] (same as EXEC-01a)

**Verification:**
- Close path is native (nativeRedeem), not CEX
- Tests the engine's close path selection logic — native preferred when available

**Note:** This test validates path selection, not execution mechanics. The trade
flow is identical to EXEC-01a. The interesting thing is confirming the engine
doesn't unnecessarily route through CEX when native is available.

#### EXEC-01d: zeph-evm-discount-cex-close

**Network state:** Defensive RR (2x-4x), ZSD mint blocked

**Setup:**
- Engine in manual approval mode
- Set oracle price to achieve defensive RR (2x-4x range)
- Push wZEPH-wZSD pool to discount (>100bps)

**Key context:** The discount native close needs nativeMint (ZEPH → ZSD), but
ZSD minting is blocked in defensive RR. The engine must fall back to CEX close.
This is the primary test for the CEX execution path — only ZEPH has CEX close.

**Preflight — Detection:**
- Engine detects evm_discount opportunity for ZEPH

**Preflight — Planning:**
- Verify plan uses CEX close path (native close unavailable)
- Expected ops: TBD — likely [swapEVM, unwrap, depositCEX, tradeCEX, withdrawCEX, wrap]
  or similar (need to verify actual CEX step naming from engine)

**Trade flow (what the engine executes):**
- Open: swapEVM — sell wZSD → buy underpriced wZEPH on Uniswap V4
- Close (CEX path):
  - unwrap — burn wZEPH on EVM → receive ZEPH on Zephyr chain
  - depositCEX — send ZEPH to CEX wallet (Zephyr transfer)
  - tradeCEX — sell ZEPH → buy USDT on CEX (accounting-only in devnet)
  - withdrawCEX — withdraw USDT from CEX to EVM wallet
  - wrap — TBD (may need to convert USDT → wZSD via pool swap)
- Net effect: engine captures discount spread via CEX routing

**Verification:**
- Execution record: success=true, CEX trade steps present
- CEX wallet balances reflect the trade (ZEPH deposited, USDT withdrawn)

**Note:** CEX trades are accounting-only in devnet (fake orderbook), but the
deposit/withdrawal steps are real wallet transfers. This is the most complex
execution path and the only test exercising the CEX close flow.

#### EXEC-01e: zeph-evm-premium-defensive-gate

**Network state:** Defensive RR (2x-4x)

**Setup:**
- Engine in manual approval mode
- Set oracle price to achieve defensive RR
- Push wZEPH-wZSD pool to premium

**Key context:** In defensive mode, the engine applies a PnL gate: ZEPH arbs
only auto-execute if estimated PnL >= $20. This test verifies that gate.

**Test flow:**
1. Push pool to create a marginal opportunity (just above 100bps threshold
   but PnL below $20 gate) — engine should detect but NOT auto-execute
2. Push pool harder to create a strong opportunity (PnL >= $20) — engine
   should auto-execute

**Verification:**
- Marginal opportunity: detected, plan built, but execution blocked by PnL gate
- Strong opportunity: auto-executes through native close path

**Note:** TBD — exact PnL threshold and how to engineer marginal vs strong
opportunities needs investigation. May need to calibrate swap amounts carefully.

#### EXEC-01f: zeph-crisis-manual-only

**Network state:** Crisis RR (<2x)

**Setup:**
- Engine in auto mode (autoExecute=true, manualApproval=false)
- Set oracle price to achieve crisis RR (<2x)
- Push wZEPH-wZSD pool to premium (>100bps)

**Key context:** In crisis mode, the engine blocks ALL ZEPH auto-execution
regardless of close path availability. Even though ZSD redeem (nativeRedeem)
works at any RR, the engine refuses to auto-execute as a risk management choice.
Manual approval is required.

**Preflight — Detection:**
- Engine detects evm_premium opportunity for ZEPH (detection still works)

**Preflight — Planning:**
- Engine builds a plan but does NOT auto-execute
- Plan should be queued or logged but not in execution history

**Verification:**
- No new execution record appears in history (auto-execute blocked)
- Opportunity is visible in evaluate API
- TBD: If manually approved, execution should complete successfully

**Note:** This tests the engine's risk management stance: crisis = no auto ZEPH
trades. The protocol doesn't block the trade, the engine does. See the design
note above about whether this is overly conservative.

### EXEC-02: ZSD arb execution

ZSD uses a very thick pool (wZSD-USDT, $500K/side). Low trigger threshold
(12bps) but extremely hard to move the pool price. No CEX close path for ZSD.

**Pool challenge:** The wZSD-USDT pool has $500K per side. Moving it 12bps
requires ~$12K of swap capital. Moving it further requires proportionally more.
This makes ZSD execution tests expensive in terms of capital requirements.

#### EXEC-02a: zsd-evm-discount-unwrap

**Network state:** Normal RR (4x-8x)

**Setup:**
- Engine in manual approval mode
- Test wallet funded with USDT
- Push wZSD-USDT pool to discount (sell USDT → buy wZSD, making wZSD cheap)
- Need >12bps gap — requires ~$12K USDT swap on $500K/side pool

**Trade flow (what the engine executes):**
- Open: swapEVM — sell USDT → buy underpriced wZSD on Uniswap V4
- Close: unwrap — burn wZSD on EVM → receive ZSD on Zephyr chain
  (always available, no RR gate, no native conversion needed)
- Net effect: engine ends up with ZSD on Zephyr, needs to get back to EVM somehow

**Verification:**
- Execution record: success=true, asset=ZSD, direction=evm_discount
- Step ops match [swapEVM, unwrap]

**Note:** This is the simplest possible close path (just unwrap, no native
conversion). Good smoke test if the pool can actually be moved past threshold.
TBD whether the pool is too thick to reliably trigger — may need spec-verified
fallback approach.

#### EXEC-02b: zsd-evm-premium-native-mint

**Network state:** Normal RR (4x-8x), ZSD mintable

**Setup:**
- Engine in manual approval mode
- Test wallet funded with wZSD
- Push wZSD-USDT pool to premium (sell wZSD → buy USDT, making wZSD expensive)

**Trade flow (what the engine executes):**
- Open: swapEVM — sell overpriced wZSD → buy USDT on Uniswap V4
- Close:
  - nativeMint — convert ZEPH → ZSD on Zephyr chain (requires RR >= 4x)
  - wrap — send ZSD on Zephyr → claim wZSD on EVM
- Net effect: engine captures premium spread, replenishes wZSD via native mint

**Verification:**
- Execution record: success=true, asset=ZSD, direction=evm_premium
- Step ops match [swapEVM, nativeMint, wrap]

**Note:** Requires RR >= 4x for ZSD mint. TBD whether pool is too thick to
reliably move past 12bps threshold.

#### EXEC-02c: zsd-premium-blocked-defensive

**Network state:** Defensive RR (2x-4x), ZSD mint blocked

**Setup:**
- Set oracle price to achieve defensive RR
- Push wZSD-USDT pool to premium (>12bps)

**Expected outcome:** No close path available — ZSD has no CEX fallback and
nativeMint is blocked in defensive mode. Engine should detect the opportunity
but have no executable plan.

**Verification:**
- Opportunity detected in evaluate API
- No execution record — engine correctly identifies no viable close path
- TBD: Does the engine log a "no close path" message or just skip silently?

**Note:** ZSD is the most constrained asset — thick pool + no CEX fallback
means it's only tradeable in normal RR. This test confirms the engine correctly
handles the dead-end case.

### EXEC-03: ZYS arb execution

ZYS uses wZYS-wZSD pool. Trigger threshold: 30bps. ZYS is unique because
ZYS mint and redeem have NO RR gates — they work at every RR level. This means
ZYS native close is always available, and ZYS is the only asset that can
auto-execute in crisis mode.

#### EXEC-03a: zys-evm-premium-native-mint

**Network state:** Normal RR (4x-8x)

**Setup:**
- Engine in manual approval mode
- Test wallet funded with wZSD
- Push wZYS-wZSD pool to premium (sell wZSD → buy wZYS, making wZYS expensive)
- Need >30bps gap

**Trade flow (what the engine executes):**
- Open: swapEVM — sell overpriced wZYS → buy wZSD on Uniswap V4
- Close (native path, 3 steps):
  - unwrap — burn wZSD on EVM → receive ZSD on Zephyr chain
  - nativeMint — convert ZSD → ZYS (always available, no RR gate)
  - wrap — send ZYS on Zephyr → claim wZYS on EVM
- Net effect: engine captures premium spread, ends with ~same wZYS balance

**Verification:**
- Execution record: success=true, asset=ZYS, direction=evm_premium
- Step ops match [swapEVM, unwrap, nativeMint, wrap]
- Engine's wZYS balance approximately round-trips

**Note:** ZYS mint is always available regardless of RR — no protocol gate.

#### EXEC-03b: zys-evm-discount-native-redeem

**Network state:** Normal RR (4x-8x)

**Setup:**
- Engine in manual approval mode
- Test wallet funded with wZYS (TBD: or wZSD, depending on push direction)
- Push wZYS-wZSD pool to discount (sell wZYS → buy wZSD, making wZYS cheap)
- Need >30bps gap

**Trade flow (what the engine executes):**
- Open: swapEVM — sell wZSD → buy underpriced wZYS on Uniswap V4
- Close (native path, 3 steps):
  - unwrap — burn wZYS on EVM → receive ZYS on Zephyr chain
  - nativeRedeem — convert ZYS → ZSD (always available, no RR gate)
  - wrap — send ZSD on Zephyr → claim wZSD on EVM
- Net effect: engine captures discount spread, ends with ~same wZSD balance

**Verification:**
- Execution record: success=true, asset=ZYS, direction=evm_discount
- Step ops match [swapEVM, unwrap, nativeRedeem, wrap]
- Engine's wZSD balance approximately round-trips

**Note:** ZYS redeem is always available regardless of RR — no protocol gate.

#### EXEC-03c: zys-auto-in-crisis

**Network state:** Crisis RR (<2x)

**Setup:**
- Engine in auto mode (autoExecute=true, manualApproval=false)
- Set oracle price to achieve crisis RR (<2x)
- Push wZYS-wZSD pool to discount (>30bps)

**Key context:** ZYS evm_discount is the ONLY arb leg across all assets that
auto-executes in crisis mode. This is because:
1. ZYS redeem has no RR gate (always available)
2. The engine's risk policy explicitly allows ZYS discount in crisis

**Verification:**
- Execution completes WITHOUT manual approval (auto-executed)
- This is unique — all other assets are blocked in crisis
- Execution record: success=true, asset=ZYS, direction=evm_discount

**Note:** This is a critical behavioral test. If it fails (execution blocked),
either the engine's risk policy changed or the RR mode detection is wrong.

### EXEC-04: ZRS arb execution

ZRS uses the thinnest pool (wZRS-wZEPH, ~$30K/side) — most reliable trigger
for execution tests. Trigger threshold: 100bps. Small swaps move the pool
significantly, making these tests the most practical to run.

**Recommendation:** Start with EXEC-04a for initial E2E validation. The thin
pool means reliable, repeatable price manipulation with modest capital.

#### EXEC-04a: zrs-evm-premium-native-close

**Network state:** Normal RR (4x-8x)

**Setup:**
- Engine in manual approval mode
- Test wallet funded with wZEPH
- Push wZRS-wZEPH pool to premium (sell wZEPH → buy wZRS, making wZRS expensive)
- ~13K wZEPH swap should exceed 100bps on the thin pool

**Preflight — Detection:**
- Engine detects evm_premium opportunity for ZRS
- Verify gapBps exceeds 100bps threshold

**Preflight — Planning:**
- Pending operation queued with expected ops
- Expected ops: [swapEVM, unwrap, nativeMint, wrap]

**Trade flow (what the engine executes):**
- Open: swapEVM — sell overpriced wZRS → buy wZEPH on Uniswap V4
- Close (native path, 3 steps):
  - unwrap — burn wZEPH on EVM → receive ZEPH on Zephyr chain
  - nativeMint — convert ZEPH → ZRS (requires RR >= 4x)
  - wrap — send ZRS on Zephyr → claim wZRS on EVM
- Net effect: engine captures premium spread, ends with ~same wZRS balance

**Verification:**
- Execution record: success=true, asset=ZRS, direction=evm_premium
- Step ops match [swapEVM, unwrap, nativeMint, wrap]
- Engine's wZRS balance approximately round-trips

**Note:** This is the recommended first E2E test to get working — thin pool
makes it reliable and fast. Use this to validate the full execution pipeline
before attempting thicker pools.

#### EXEC-04b: zrs-evm-discount-native-close

**Network state:** Normal RR (4x-8x)

**Setup:**
- Engine in manual approval mode
- Test wallet funded with wZRS
- Push wZRS-wZEPH pool to discount (sell wZRS → buy wZEPH, making wZRS cheap)
- ~8K wZRS swap should exceed 100bps

**Trade flow (what the engine executes):**
- Open: swapEVM — sell wZEPH → buy underpriced wZRS on Uniswap V4
- Close (native path, 3 steps):
  - unwrap — burn wZRS on EVM → receive ZRS on Zephyr chain
  - nativeRedeem — convert ZRS → ZEPH (requires RR >= 4x for ZRS redeem)
  - wrap — send ZEPH on Zephyr → claim wZEPH on EVM
- Net effect: engine captures discount spread, ends with ~same wZEPH balance

**Verification:**
- Execution record: success=true, asset=ZRS, direction=evm_discount
- Step ops match [swapEVM, unwrap, nativeRedeem, wrap]
- Engine's wZEPH balance approximately round-trips

#### EXEC-04c: zrs-blocked-in-defensive

**Network state:** Defensive RR (2x-4x)

**Setup:**
- Engine in auto mode (autoExecute=true, manualApproval=false)
- Set oracle price to achieve defensive RR
- Push wZRS-wZEPH pool past 100bps threshold

**Expected outcome:** Engine detects the opportunity but does NOT auto-execute.
ZRS native close requires nativeMint/nativeRedeem which need RR >= 4x — blocked
in defensive mode. No CEX fallback for ZRS.

**Verification:**
- Opportunity detected in evaluate API
- No new execution record in history
- TBD: Does the engine log "close path blocked" or queue with blocked status?

#### EXEC-04d: zrs-blocked-in-crisis

**Network state:** Crisis RR (<2x)

**Setup:**
- Engine in auto mode
- Set oracle price to achieve crisis RR
- Push wZRS-wZEPH pool past threshold

**Expected outcome:** Same as EXEC-04c but more restrictive. ZRS is fully
blocked in crisis — no native close, no CEX fallback.

**Verification:**
- Opportunity detected but no execution
- Engine correctly identifies no viable execution path

### EXEC-05: Cross-cutting execution tests

These tests verify engine behavior that spans across assets — loop autonomy,
balance accounting, and the manual approval flow itself.

#### EXEC-05a: engine-loop-autonomous

**Purpose:** Verify the engine loop detects and executes without any manual API
trigger — pure autonomous operation.

**Setup:**
- Normal RR, autoExecute=true, manualApproval=false
- Engine-run process running with arb strategy
- Push ZRS pool past threshold (reliable trigger, thin pool)

**Test flow:**
- Do NOT call any execute/approve API
- Wait for engine loop to detect opportunity and auto-execute (2-3 cycles, ~10-15s)
- The engine's main loop should: detect → plan → shouldAutoExecute → executePlan

**Verification:**
- New execution record appears in history without any API intervention
- Execution was triggered by the engine loop, not by test code
- success=true, correct asset/direction

**Note:** This is the "happy path" test for the engine running unattended.

#### EXEC-05b: balance-round-trip

**Purpose:** After a successful arb, verify token balances are consistent and
the engine didn't leak funds.

**Setup:**
- Normal RR, use ZRS premium arb (EXEC-04a pattern — most reliable)

**Test flow:**
1. Record all engine wallet balances before pool push:
   - EVM: wZEPH, wZSD, wZRS, wZYS, USDT, ETH
   - TBD: Native Zephyr balances if accessible
2. Execute a full arb cycle (push → detect → approve → execute)
3. Record balances after execution completes

**Verification:**
- Net balance change is positive (profit captured) or non-negative after fees
- No tokens leaked — total across venues conserved minus gas/fees
- ETH balance decreased by gas cost (reasonable amount)
- Primary arb token (wZRS) approximately round-trips

**Note:** TBD — exact tolerance thresholds for "approximately round-trips" need
calibration. Gas costs, slippage, and bridge fees all contribute to variance.

#### EXEC-05c: manual-approval-flow

**Purpose:** Verify the full manual approval lifecycle — opportunities queue
when autoExecute=false, and execute only after explicit approval.

**Setup:**
- autoExecute=false (engine evaluates but never executes)
- Push ZRS pool past threshold

**Test flow:**
1. Wait for engine cycle — verify opportunity detected (evaluate API)
2. Verify: plan built but NOT in execution history (no auto-execute)
3. Check queue: pending operation exists
4. Approve via queue API (POST with action=approve, operationId=xxx)
5. Wait for engine to pick up approved operation (next cycle)
6. Verify: execution completes after approval

**Verification:**
- Phase 1: opportunity visible, no execution record
- Phase 2: after approval, execution record appears with success=true
- Queue operation transitions: pending → approved → (engine picks up) → executed

**Note:** This is essentially what EXEC-01a does, but focused on the approval
lifecycle itself rather than the trade mechanics. Could be merged with EXEC-01a
or kept separate for clarity.

---

## CEX: CEX Wallet Client

### CEX-01: get-balances

- CexWalletClient.getBalances()
- Expected: returns ZEPH and USDT balances from wallet RPC + EVM respectively

### CEX-02: get-balances-rpc-failure

- Zephyr wallet RPC unreachable
- Expected: ZEPH defaults to `{ total: 0, unlocked: 0 }`, no throw

### CEX-03: get-balances-evm-failure

- USDT contract read fails
- Expected: USDT defaults to 0, no throw

### CEX-04: market-order-accounting

- CexWalletClient.marketOrder() for ZEPH BUY
- Expected: returns success, uses mid-price from orderbook, calculates 0.10% fee, no real fund movement

### CEX-05: get-mid-price-fallback

- Orderbook unreachable
- Expected: `getMidPrice()` falls back to $0.50

### CEX-06: deposit-address-zeph

- getDepositAddress("ZEPH")
- Expected: returns Zephyr wallet address from RPC

### CEX-07: deposit-address-usdt

- getDepositAddress("USDT")
- Expected: returns EVM CEX_ADDRESS

### CEX-08: deposit-address-unsupported

- getDepositAddress("ZSD")
- Expected: throws "CEX deposit not supported"

### CEX-09: withdraw-zeph

- requestWithdraw for ZEPH
- Expected: real Zephyr wallet transfer executed, returns txHash

### CEX-10: withdraw-usdt

- requestWithdraw for USDT
- Expected: real ERC-20 transfer executed, returns txHash

### CEX-11: withdraw-unsupported-asset

- requestWithdraw for ZRS
- Expected: returns `success: false`

### CEX-12: withdraw-rpc-failure

- Zephyr RPC fails during ZEPH withdraw
- Expected: returns `success: false` with error message (caught)

### CEX-13: singleton-mode-lock

- First call `getCexWalletClient("paper")`, second call `getCexWalletClient("devnet")`
- Expected: both return same instance, mode is "paper" (first call wins)

---

## REB: Rebalancer Strategy

### REB-E: Evaluate

#### REB-E01: no-reserve-data

- State with undefined reserve
- Expected: empty opportunities, warning present

#### REB-E02: balanced-allocation

- ZEPH distributed 30/50/20 (exactly on target)
- Expected: no opportunity for ZEPH

#### REB-E03: small-deviation-under-threshold

- ZEPH EVM at 35%, native at 50%, CEX at 15% (5 pp deviation)
- Expected: no opportunity (below 10 pp threshold)

#### REB-E04: deviation-at-threshold

- ZEPH EVM at 40%, native at 50%, CEX at 10% (10 pp deviation)
- Expected: opportunity detected, from EVM to CEX

#### REB-E05: large-deviation

- ZEPH EVM at 80%, native at 15%, CEX at 5% (50 pp deviation)
- Expected: opportunity with high urgency, movement capped at 25% of total

#### REB-E06: zero-total-balance

- Asset with zero balance across all venues
- Expected: no opportunity, trigger = "No {asset} balance"

#### REB-E07: multiple-assets-drifted

- ZEPH and ZSD both significantly drifted
- Expected: separate opportunity for each asset

#### REB-E08: urgency-levels

- Deviation 15 pp -> low
- Deviation 30 pp -> medium
- Deviation 45 pp -> high

#### REB-E09: negative-pnl

- Any rebalance opportunity
- Expected: `expectedPnl` is negative (rebalancing costs money)

#### REB-E10: metrics-per-asset

- Evaluate with valid state
- Expected: metrics contain `{asset}_evmPct`, `{asset}_nativePct`, `{asset}_cexPct` for each asset

---

### REB-P: Plan Building

#### REB-P01: evm-to-native

- Rebalance ZEPH from EVM to native
- Expected: single `unwrap` step

#### REB-P02: native-to-evm

- Rebalance ZEPH from native to EVM
- Expected: single `wrap` step

#### REB-P03: evm-to-cex

- Rebalance ZEPH from EVM to CEX
- Expected: two steps: `unwrap` then `deposit`

#### REB-P04: native-to-cex

- Rebalance ZEPH from native to CEX
- Expected: single `deposit` step

#### REB-P05: cex-to-native

- Rebalance ZEPH from CEX to native
- Expected: single `withdraw` step

#### REB-P06: cex-to-evm

- Rebalance ZEPH from CEX to EVM
- Expected: two steps: `withdraw` then `wrap`

#### REB-P07: same-venue-evm-swap

- Rebalance within EVM (e.g., USDT -> WZSD)
- Expected: single `swapEVM` step

#### REB-P08: same-venue-native-unsupported

- Rebalance within native venue
- Expected: logs warning, returns null (not supported)

#### REB-P09: missing-context

- Missing fromVenue, toVenue, or amount in opportunity
- Expected: returns null, logs warning

#### REB-P10: usdt-decimal-handling

- USDT rebalance
- Expected: amount converted with 1e6 (6 decimals), not 1e12

#### REB-P11: zeph-decimal-handling

- ZEPH rebalance
- Expected: amount converted with 1e12 (12 decimals)

#### REB-P12: cost-estimation-evm-to-native

- EVM -> native route
- Expected: cost = amount * 0.01 + $5

#### REB-P13: cost-estimation-native-to-evm

- Native -> EVM route
- Expected: cost = $5

#### REB-P14: cost-estimation-involving-cex

- Any route involving CEX
- Expected: additional $2 withdrawal fee

#### REB-P15: duration-estimation

- EVM <-> native -> 20 min
- Involving CEX -> 40 min

---

### REB-A: Auto-Execution

#### REB-A01: normal-mode-auto

- Normal RR mode, cost <= $50
- Expected: `shouldAutoExecute = true`

#### REB-A02: normal-mode-high-cost

- Normal RR mode, cost = $60
- Expected: `shouldAutoExecute = false`

#### REB-A03: defensive-blocked

- Defensive RR mode
- Expected: `shouldAutoExecute = false`

#### REB-A04: crisis-blocked

- Crisis RR mode
- Expected: `shouldAutoExecute = false`

#### REB-A05: manual-approval-override

- config.manualApproval = true, any RR mode
- Expected: `shouldAutoExecute = false`

---

## PEG: Peg Keeper Strategy

### PEG-E: Evaluate

#### PEG-E01: no-reserve-data

- State with undefined reserve
- Expected: empty opportunities, warning present

#### PEG-E02: no-zsd-pool

- State with no WZSD/USDT pool
- Expected: empty opportunities, warning "Cannot determine ZSD price from EVM pools"

#### PEG-E03: zsd-on-peg

- WZSD/USDT pool price = 1.0000 exactly
- Expected: no opportunity (0 bps deviation)

#### PEG-E04: zsd-premium-normal-above-threshold

- Pool price = 1.0035 (35 bps above peg), normal mode
- Expected: opportunity detected, direction = "zsd_premium"

#### PEG-E05: zsd-discount-normal-above-threshold

- Pool price = 0.9960 (40 bps below peg), normal mode
- Expected: opportunity detected, direction = "zsd_discount"

#### PEG-E06: zsd-premium-normal-below-threshold

- Pool price = 1.0020 (20 bps), normal mode (threshold = 30 bps)
- Expected: no opportunity

#### PEG-E07: zsd-deviation-defensive-threshold

- Pool price = 1.0080 (80 bps), defensive mode (threshold = 100 bps)
- Expected: no opportunity (80 < 100)

#### PEG-E08: zsd-deviation-defensive-above-threshold

- Pool price = 1.0120 (120 bps), defensive mode
- Expected: opportunity detected

#### PEG-E09: zsd-deviation-crisis-threshold

- Pool price = 0.9750 (250 bps below), crisis mode (threshold = 300 bps)
- Expected: no opportunity (250 < 300)

#### PEG-E10: zsd-deviation-crisis-above-threshold

- Pool price = 0.9650 (350 bps below), crisis mode
- Expected: opportunity detected, direction = "zsd_discount"

#### PEG-E11: defensive-mode-warning

- Defensive RR mode
- Expected: warning "RR in defensive mode - widened peg tolerance"

#### PEG-E12: crisis-mode-warning

- Crisis RR mode
- Expected: warning about crisis mode present

#### PEG-E13: urgency-critical

- Deviation >= critical threshold for current RR mode
- Expected: urgency = "critical"

#### PEG-E14: urgency-high

- Deviation >= urgent threshold but < critical
- Expected: urgency = "high"

#### PEG-E15: urgency-medium

- Deviation >= 2x min threshold but < urgent
- Expected: urgency = "medium"

#### PEG-E16: urgency-low

- Deviation >= min but < 2x min
- Expected: urgency = "low"

---

### PEG-C: Clip Sizing

#### PEG-C01: small-deviation

- Deviation < 100 bps
- Expected: clip = $500

#### PEG-C02: moderate-deviation

- Deviation >= 100 bps and < 200 bps
- Expected: clip = $1000

#### PEG-C03: large-deviation

- Deviation >= 200 bps
- Expected: clip = $2000

---

### PEG-P: Plan Building

#### PEG-P01: zsd-premium-sell

- Direction = "zsd_premium"
- Expected: swapEVM step WZSD.e -> USDT.e

#### PEG-P02: zsd-premium-with-wrap

- Direction = "zsd_premium", native ZSD balance > EVM ZSD balance and > clip
- Expected: wrap step (ZSD.n -> WZSD.e) THEN swapEVM step

#### PEG-P03: zsd-premium-without-wrap

- Direction = "zsd_premium", EVM ZSD balance >= native
- Expected: no wrap step, just swapEVM

#### PEG-P04: zsd-discount-buy

- Direction = "zsd_discount"
- Expected: single swapEVM step USDT.e -> WZSD.e (no unwrap step)

#### PEG-P05: missing-context

- Missing direction or clipSizeUsd
- Expected: returns null

#### PEG-P06: swap-context-found

- WZSD/USDT pool present in state
- Expected: swapContext populated with pool address, fee, tickSpacing

#### PEG-P07: no-matching-pool

- State with no WZSD/USDT pool
- Expected: swapContext = undefined in step

#### PEG-P08: duration-with-wrap

- Plan includes a wrap step
- Expected: duration includes additional 20 min bridge time

#### PEG-P09: profit-estimation

- 50 bps deviation, $500 clip
- Expected: gross = $2.50, fees ~$2.15, net ~$0.35

---

### PEG-A: Auto-Execution

#### PEG-A01: normal-profitable

- Normal mode, positive PnL
- Expected: `shouldAutoExecute = true`

#### PEG-A02: normal-unprofitable

- Normal mode, negative PnL
- Expected: `shouldAutoExecute = false`

#### PEG-A03: defensive-above-1pct

- Defensive mode, deviation > 100 bps, positive PnL
- Expected: `shouldAutoExecute = true`

#### PEG-A04: defensive-below-1pct

- Defensive mode, deviation = 80 bps
- Expected: `shouldAutoExecute = false`

#### PEG-A05: crisis-discount-above-5pct

- Crisis mode, zsd_discount direction, deviation > 500 bps
- Expected: `shouldAutoExecute = true`

#### PEG-A06: crisis-discount-below-5pct

- Crisis mode, zsd_discount, deviation = 400 bps
- Expected: `shouldAutoExecute = false`

#### PEG-A07: crisis-premium-blocked

- Crisis mode, zsd_premium direction (selling ZSD in crisis)
- Expected: `shouldAutoExecute = false`

#### PEG-A08: manual-approval-override

- config.manualApproval = true
- Expected: `shouldAutoExecute = false`

---

## LP: LP Manager Strategy

### LP-E: Evaluate

#### LP-E01: no-reserve-data

- State with undefined reserve
- Expected: empty opportunities, warning present

#### LP-E02: no-positions

- No LP positions in database
- Expected: empty opportunities, metrics show 0 positions

#### LP-E03: position-in-range-healthy

- Position in range, fees < $50, range within 10% drift
- Expected: no opportunity for this position

#### LP-E04: position-out-of-range

- Position where currentTick is outside [tickLower, tickUpper)
- Expected: opportunity with action = "reposition", urgency = "high"

#### LP-E05: position-high-fees

- Position with accumulated fees > $50
- Expected: opportunity with action = "collect_fees", urgency = "low"

#### LP-E06: position-range-drift

- Position in range but range drifts >10% from RR-mode recommended range
- Expected: opportunity with action = "adjust_range", urgency = "medium"

#### LP-E07: multiple-positions-analyzed

- 3 positions: one healthy, one out of range, one with high fees
- Expected: 2 opportunities (out-of-range + fees), healthy skipped

#### LP-E08: action-priority-ordering

- Position that is both out-of-range AND has high fees
- Expected: "reposition" wins (checked first, higher priority)

#### LP-E09: metrics-calculation

- 3 positions with known values
- Expected: metrics contain correct `totalPositions`, `inRangePositions`, `totalValueUsd`, `totalFeesUsd`

#### LP-E10: out-of-range-warning

- 2 positions out of range
- Expected: warning "2 positions out of range"

#### LP-E11: non-normal-rr-warning

- RR in defensive mode
- Expected: warning "Consider adjusting LP ranges for defensive mode"

#### LP-E12: db-failure-graceful

- Database query throws
- Expected: empty positions returned, no crash

#### LP-E13: missing-evm-wallet

- No EVM_WALLET_ADDRESS env
- Expected: empty positions, logs warning

---

### LP-R: Range Recommendations

#### LP-R01: zsd-normal-range

- ZSD pool, normal RR mode
- Expected: recommended range $0.98 - $1.02

#### LP-R02: zsd-defensive-range

- ZSD pool, defensive RR mode
- Expected: $0.90 - $1.05

#### LP-R03: zsd-crisis-range

- ZSD pool, crisis RR mode
- Expected: $0.50 - $1.10

#### LP-R04: zeph-normal-range

- ZEPH pool at mid-price $0.75, normal mode
- Expected: $0.60 - $0.90 (0.75 * 0.80 to 0.75 * 1.20)

#### LP-R05: zeph-defensive-range

- ZEPH pool at mid-price $0.75, defensive mode
- Expected: $0.525 - $0.975 (0.75 * 0.70 to 0.75 * 1.30)

#### LP-R06: zeph-crisis-range

- ZEPH pool at mid-price $0.75, crisis mode
- Expected: $0.375 - $1.125 (0.75 * 0.50 to 0.75 * 1.50)

#### LP-R07: pool-asset-detection-zsd

- Pool tokens: WZSD.e and USDT.e
- Expected: `getPoolAsset()` returns "ZSD", uses ZSD range configs

#### LP-R08: pool-asset-detection-zeph

- Pool tokens: WZEPH.e and WZSD.e
- Expected: `getPoolAsset()` returns "ZSD" (ZSD token checked first!) — uses ZSD configs, NOT ZEPH

#### LP-R09: pool-asset-detection-zrs

- Pool tokens: WZRS.e and WZEPH.e
- Expected: `getPoolAsset()` returns "ZEPH" (ZEPH checked before ZRS) — uses ZEPH configs

#### LP-R10: range-drift-detection

- Current range: $0.95 - $1.05, recommended: $0.98 - $1.02
- Expected: `shouldAdjustRange()` returns true if drift > 10%

#### LP-R11: range-drift-within-tolerance

- Current range: $0.975 - $1.025, recommended: $0.98 - $1.02
- Expected: `shouldAdjustRange()` returns false

---

### LP-P: Plan Building

#### LP-P01: collect-fees-plan

- action = "collect_fees", valid positionId
- Expected: single `lpCollect` step

#### LP-P02: reposition-plan

- action = "reposition", valid position + recommended range
- Expected: `lpBurn` step then `lpMint` step with new tick bounds

#### LP-P03: adjust-range-plan

- action = "adjust_range"
- Expected: same as reposition (lpBurn + lpMint)

#### LP-P04: add-liquidity-plan

- action = "add_liquidity"
- Expected: single `lpMint` step

#### LP-P05: remove-liquidity-plan

- action = "remove_liquidity"
- Expected: single `lpBurn` step

#### LP-P06: missing-action-or-pool

- action = undefined or poolId = undefined
- Expected: returns null

#### LP-P07: tick-conversion

- Recommended range $0.98 - $1.02
- Expected: ticks calculated as `floor(log(price) / log(1.0001))`

#### LP-P08: swap-context-from-pool

- Valid pool with address
- Expected: swapContext has correct poolAddress, fee (feeBps * 100), tickSpacing

#### LP-P09: no-pool-found

- poolId doesn't match any pool in state
- Expected: null returned or steps without swapContext

#### LP-P10: all-steps-zero-amount

- Any LP plan
- Expected: all steps have `amountIn = 0n` (amounts determined at execution time)

---

### LP-A: Auto-Execution

#### LP-A01: fee-collection-auto

- action = "collect_fees", feesEarned > $10
- Expected: `shouldAutoExecute = true`

#### LP-A02: fee-collection-low-fees

- action = "collect_fees", feesEarned = $8
- Expected: `shouldAutoExecute = false`

#### LP-A03: reposition-always-manual

- action = "reposition", any conditions
- Expected: `shouldAutoExecute = false`

#### LP-A04: adjust-range-always-manual

- action = "adjust_range"
- Expected: `shouldAutoExecute = false`

#### LP-A05: add-liquidity-always-manual

- action = "add_liquidity"
- Expected: `shouldAutoExecute = false`

#### LP-A06: remove-liquidity-always-manual

- action = "remove_liquidity"
- Expected: `shouldAutoExecute = false`

#### LP-A07: manual-approval-override

- config.manualApproval = true, any action
- Expected: `shouldAutoExecute = false`

---

### LP-V: Position Valuation

#### LP-V01: usdt-valued-at-1

- Position with USDT token
- Expected: valued at $1.00 per unit

#### LP-V02: wzsd-valued-at-1

- Position with WZSD token
- Expected: valued at $1.00 per unit

#### LP-V03: wzeph-from-reserve

- Position with WZEPH token, zephPriceUsd = 0.75
- Expected: valued at $0.75 per unit

#### LP-V04: wzrs-from-reserve

- Position with WZRS, rates.zrs.spotUSD = 1.50
- Expected: valued at $1.50 per unit

#### LP-V05: wzys-default-to-1

- Position with WZYS, rates.zys.spotUSD = undefined
- Expected: valued at $1.00 (default fallback)

#### LP-V06: unknown-token-zero

- Position with unknown token
- Expected: valued at $0.00

---

## ENG: Engine Loop & Orchestration

### ENG-01: cycle-with-auto-execute-off

- `autoExecute = false` in DB settings
- Expected: strategies evaluated, metrics recorded, but NO plans built or executed

### ENG-02: cycle-with-auto-execute-on

- `autoExecute = true`, opportunities exist
- Expected: strategies evaluated, plans built, auto-executable ones executed

### ENG-03: stale-evm-data

- EVM state older than 120 seconds
- Expected: cycle skipped with "stale state" warning

### ENG-04: stale-cex-data

- CEX state older than 60 seconds
- Expected: cycle skipped

### ENG-05: missing-reserve-data

- `state.zephyr.reserve = undefined`
- Expected: cycle skipped (state not fresh)

### ENG-06: cooldown-enforcement

- Execute ZEPH evm_discount, then same opportunity appears next cycle
- Expected: second attempt blocked by cooldown (default 60s)

### ENG-07: max-operations-per-cycle

- 7 opportunities available, maxOperationsPerCycle = 5
- Expected: only 5 plans built/executed, remaining skipped

### ENG-08: manual-approval-queuing

- manualApproval = true, opportunity exists
- Expected: plan written to `operationQueue` table with status = "pending"

### ENG-09: approved-queue-processing

- Previously queued operation approved (status = "approved" in DB)
- Expected: picked up and executed in next cycle

### ENG-10: execution-engine-null-graceful

- Execution engine failed to initialize (e.g., missing EVM key)
- Expected: engine runs but all plans are "logged only", not executed

### ENG-11: cycle-error-recovery

- Strategy evaluate() throws
- Expected: error logged, cycle completes, next cycle runs normally

### ENG-12: inventory-sync

- Successful cycle with valid inventory
- Expected: `syncInventoryToDb()` called, DB updated

### ENG-13: inventory-sync-failure

- `syncInventoryToDb()` throws
- Expected: error logged, engine continues (not fatal)

---

## RISK: Risk Management

### RISK-01: circuit-breaker-disabled

- Risk limits disabled (default for devnet)
- Expected: `canExecute()` always returns `{ allowed: true }`

### RISK-02: circuit-breaker-consecutive-failures

- 3 consecutive execution failures
- Expected: circuit opens, subsequent `canExecute()` returns false

### RISK-03: circuit-breaker-cumulative-loss

- Cumulative loss exceeds $500 (default maxDailyLossUsd)
- Expected: circuit opens

### RISK-04: circuit-breaker-success-resets-failures

- 2 failures, then 1 success
- Expected: consecutive failure counter resets to 0

### RISK-05: circuit-breaker-negative-pnl-accumulates

- Successful execution with PnL = -$50
- Expected: adds to cumulativeLossUsd, may trip threshold

### RISK-06: blocked-execution-recorded

- Circuit breaker blocks execution
- Expected: `executionHistory` record created with `blocked: true` and reason

### RISK-07: operation-size-estimation

- Plan with expectedPnl = $10
- Expected: estimated size = $100 (PnL * 10)

### RISK-08: asset-exposure-calculation

- ZEPH total = $5000, portfolio total = $10000
- Expected: exposure = 50%

---

## INV: Inventory System

### INV-01: evm-balance-mapping

- Snapshot with EVM token balances
- Expected: each token mapped to correct AssetId (USDT.e, WZSD.e, WZEPH.e, WZRS.e, WZYS.e)

### INV-02: native-balance-unlocked-only

- Zephyr wallet with locked and unlocked balances
- Expected: only unlocked balances used (not total)

### INV-03: cex-balance-primary

- CEX wallet snapshot with status = "ok"
- Expected: real CEX balances used (ZEPH.x, USDT.x)

### INV-04: cex-balance-paper-fallback

- CEX wallet status != "ok", paper mexc available
- Expected: paper balance store used as fallback

### INV-05: asset-totals-aggregation

- WZEPH.e = 1000, ZEPH.n = 2000, ZEPH.x = 500
- Expected: ZEPH total = 3500

### INV-06: zero-balance-handling

- Asset with 0 balance on all venues
- Expected: included in totals as 0, no error

### INV-07: non-finite-value-skipped

- Balance snapshot with NaN or Infinity value
- Expected: skipped silently, not included in totals

---

## BRIDGE: Bridge Runtime

### BRIDGE-01: wrap-enabled-check

- Valid ZEPH.n -> WZEPH.e pair with bridge state loaded
- Expected: `wrapRuntime.enabled()` returns true

### BRIDGE-02: wrap-disabled-no-state

- Bridge state undefined
- Expected: `wrapRuntime.enabled()` returns false

### BRIDGE-03: wrap-disabled-wrong-pair

- Invalid pair (e.g., USDT.e -> WZSD.e)
- Expected: `wrapRuntime.enabled()` returns false

### BRIDGE-04: unwrap-enabled-check

- Valid WZEPH.e -> ZEPH.n pair
- Expected: `unwrapRuntime.enabled()` returns true

### BRIDGE-05: wrap-context-min-amount

- Bridge state with `wrap.minAmount = 100`
- Expected: context has `minAmountFrom` set correctly

### BRIDGE-06: unwrap-context-bridge-fee

- Bridge state with `unwrap.bridgeFee = 0.01` (1%)
- Expected: context has `flatFeeTo` set

### BRIDGE-07: all-four-pairs

- Test wrap/unwrap for ZEPH, ZSD, ZRS, ZYS
- Expected: all 4 pairs found and enabled

### BRIDGE-08: duration-fixed

- `wrapRuntime.durationMs()` and `unwrapRuntime.durationMs()`
- Expected: both return 1,200,000 ms (20 min)

---

## TIMING: Execution Timing

### TIMING-01: instant-mode

- EXECUTION_TIMING != "realistic"
- Expected: all delays = 0

### TIMING-02: realistic-delays

- EXECUTION_TIMING = "realistic"
- Expected delays:
  - mexcDepositZeph: 40 min
  - mexcDepositUsdt: 5 min
  - mexcWithdraw: 2 min
  - zephyrUnlock: 20 min
  - bridgeConfirmations: 20 min
  - evmConfirmation: 12 sec
  - cexTrade: 500 ms

---

## EDGE: Edge Cases & Known Issues

### EDGE-01: bigint-precision-loss

- Paper mode swapEVM with amountIn > 2^53
- Expected: document precision loss from `Number(step.amountIn)`

### EDGE-02: zrs-premium-close-routing

- ZRS evm_premium close uses nativeRedeem label for ZEPH.n -> ZRS.n
- Expected: verify this dispatches correctly (or hits "Unknown redeem pair" error in dispatch)

### EDGE-03: venue-mapping-inconsistency

- `wrap` maps to "native" in strategy but "evm" in dispatch mapping
- Expected: document where venue is used and if this causes issues

### EDGE-04: cex-trade-fee-decimal-mismatch

- Paper mode fee = `amountIn * 0.001` (12 decimal base)
- Live mode fee = `result.fee * 1e6` (6 decimal)
- Expected: document inconsistency

### EDGE-05: rebalancer-min-usd-unused

- `minRebalanceUsd = 100` is defined but never checked
- Expected: tiny rebalances (< $100) still trigger if deviation > 10 pp

### EDGE-06: rebalancer-multi-hop-no-fee-deduction

- evm -> cex route: unwrap step + deposit step both use same amountIn
- Expected: no intermediate fee deduction between steps (potential overcommitment)

### EDGE-07: pegkeeper-no-unwrap-on-discount

- ZSD discount buy: purchased WZSD stays on EVM
- Expected: no automatic unwrap step; may cause allocation drift

### EDGE-08: pegkeeper-wrap-same-amount

- ZSD premium with wrap: both wrap and swap use same amount
- Expected: no fee deduction between wrap and swap

### EDGE-09: lp-pool-asset-priority

- WZEPH/WZSD pool: getPoolAsset() returns "ZSD" (not "ZEPH")
- Expected: ZSD range configs applied, not ZEPH

### EDGE-10: lp-all-steps-zero-amount

- All LP plan steps have amountIn = 0n
- Expected: execution layer must determine amounts (not from plan)

### EDGE-11: live-mode-cex-withdraw-unimplemented

- MexcLiveClient.requestWithdraw() throws "not yet implemented"
- Expected: any live mode plan requiring CEX withdrawal will fail at execution

### EDGE-12: live-mode-cex-deposit-address-unimplemented

- MexcLiveClient.getDepositAddress() throws "not yet implemented"
- Expected: any live mode plan requiring deposit address lookup will fail

### EDGE-13: engine-settings-table-missing

- engineSettings table doesn't exist in DB
- Expected: defaults to autoExecute = false, no crash

### EDGE-14: stale-zephyr-data-not-checked

- Zephyr staleness threshold (5 min) defined but never validated in isStateFresh()
- Expected: Zephyr data can be arbitrarily stale without triggering freshness check

### EDGE-15: execution-engine-returns-null

- `executePlan()` always returns null regardless of success/failure
- Expected: callers don't use return value, success determined from DB records

### EDGE-16: circuit-breaker-no-auto-reset

- Circuit breaker has no automatic daily reset timer
- Expected: once tripped, stays open until manual reset or process restart

---

## Summary

| Category | Count | Description |
|----------|-------|-------------|
| PRE | 9 (+6 sub) | Prerequisites & state building |
| ARB-E | 22 | Arb evaluate (opportunity detection) |
| ARB-C | 14 | Arb close path availability |
| ARB-S | 10 | Arb spread gate |
| ARB-A | 12 | Arb auto-execution gate |
| ARB-P | 12 | Arb plan building |
| ARB-F | 5 | Arb fee estimation |
| ARB-M | 10 | Arb market analysis |
| ARB-X | 9 | Arb execution step building |
| ARB-COMBINED | 4 | Arb combined RR x leg matrix |
| DISP-P | 13 | Execution dispatch (paper) |
| DISP-L | 24 | Execution dispatch (live/devnet) |
| DISP-F | 5 | Execution factory |
| CEX | 13 | CEX wallet client |
| REB-E | 10 | Rebalancer evaluate |
| REB-P | 15 | Rebalancer plan building |
| REB-A | 5 | Rebalancer auto-execution |
| PEG-E | 16 | Peg keeper evaluate |
| PEG-C | 3 | Peg keeper clip sizing |
| PEG-P | 9 | Peg keeper plan building |
| PEG-A | 8 | Peg keeper auto-execution |
| LP-E | 13 | LP manager evaluate |
| LP-R | 11 | LP range recommendations |
| LP-P | 10 | LP plan building |
| LP-A | 7 | LP auto-execution |
| LP-V | 6 | LP position valuation |
| ENG | 13 | Engine loop & orchestration |
| RISK | 8 | Risk management |
| INV | 7 | Inventory system |
| BRIDGE | 8 | Bridge runtime |
| TIMING | 2 | Execution timing |
| EDGE | 16 | Edge cases & known issues |
| **TOTAL** | **~337** | |
