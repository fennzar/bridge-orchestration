# Implementation Coverage — Source of Truth

Verified implementation status and test coverage for all bridge and engine components.

**Reference Doc:** [bridge-testnet-v2-update.md](./bridge-testnet-v2-update.md) (published, do not edit)

---

## Legend

| Symbol | Meaning |
|--------|---------|
| ✅ | Complete — fully implemented |
| ⏳ | Partial — exists but incomplete |
| 🔨 | Scaffold — interface/framework only |
| ❌ | Missing — not implemented |
| ⚠️ | Bug — broken or non-functional |

**Test Status:** ✓ tested | ○ untested

---

## Zephyr Bridge (v1)

| Component | Impl | Test | Scenario | Location | Notes |
|-----------|------|------|----------|----------|-------|
| Wrap pipeline | ✅ | ✓ | B13 | `packages/bridge/src/claims/` | listener→ingest→sign→watcher |
| Unwrap pipeline | ✅ | ✓ | B14 | `packages/bridge/src/unwraps/` | prepare→burn→relay with recovery |
| Multi-asset (ZEPH/ZSD/ZRS/ZYS) | ✅ | ○ | B18,B24 | `packages/zephyr/src/assets.ts` | Token list works; B24 tests ZRS/ZYS flows |
| EIP-712 voucher signing | ✅ | ✓ | B11 | `claims/signer.ts:93-109` | Domain, verifyingContract, deadline |
| Pre-signed commit-before-burn | ✅ | ✓ | B12 | `unwraps/ingest.ts` | Prepare + nonce=txHash |
| Redis/Prisma state | ✅ | — | — | `packages/db/src/` | Prisma-backed SystemState |
| SSE real-time streams | ✅ | ✓ | B19 | `apps/api/src/routes/claims.ts` | PostgreSQL LISTEN/NOTIFY |
| Operator admin console | ✅ | ✓ | B15,16 | `apps/web/app/admin/` | Watchers, API tester |
| Recovery/reconcile endpoints | ✅ | ✓ | B15 | `unwraps/recovery.ts` | `/admin/unwraps/*` |
| Uniswap V4 pool discovery | ⚠️ | ○ | B23 | `apps/watcher-uniswap/` | **BUG:** 0 events on fresh deploy |
| Uniswap V4 swap/LP UI | ✅ | ○ | B25 | `apps/web/app/swap/`, `lps/` | Playwright E2E scenario |
| Multi-pool routing | ⏳ | ○ | B23 | `uniswap/v4/api.ts` | Pool selection works; routing partial |
| LP management | ✅ | ○ | B26 | `uniswap/v4/positions.ts` | Playwright E2E scenario |
| Wallet UX | ✅ | ○ | B27 | `apps/web/app/details/` | Playwright E2E scenario |
| Multi-environment configs | ✅ | — | — | `packages/config/src/` | local/sepolia/mainnet |

### Additional Bridge Components (Found in Scan)

| Component | Impl | Test | Scenario | Location | Notes |
|-----------|------|------|----------|----------|-------|
| Burn payload encoding | ✅ | ✓ | B12 | `packages/bridge/src/unwraps/payload.ts` | Version, txHash, fingerprint, dest |
| Fee system | ✅ | ✓ | B14 | `packages/bridge/src/unwraps/amount.ts` | Per-asset fees, atomic units |
| Distributed locks | ✅ | — | — | `packages/db/src/stores/locks.ts` | Redis-based locking |
| PostgreSQL pub/sub | ✅ | ✓ | B19 | `packages/db/src/pubsub.ts` | LISTEN/NOTIFY for SSE |
| Token supply cache | ✅ | ✓ | B20 | `packages/db/src/stores/tokenSupply.ts` | Wrapped token supply tracking |
| Uniswap activity watcher | ✅ | ○ | B23 | `apps/api/src/uniswap/v4/activityWatcher.ts` | Swap event tracking |
| Uniswap positions watcher | ✅ | ○ | B26 | `apps/api/src/uniswap/v4/positionsWatcher.ts` | LP position tracking |
| TVL scheduler | ✅ | ○ | B23 | `apps/api/src/uniswap/v4/tvlScheduler.ts` | TVL updates |
| EVM watcher daemon | ✅ | ✓ | B13,14 | `apps/watcher-evm/src/` | Mint/Burn event monitoring |
| Zephyr faucet | ✅ | ○ | — | `apps/api/src/zephyr/faucet.ts` | Testnet ZEPH distribution |
| EVM faucet | ✅ | ○ | — | `apps/api/src/routes/faucet.ts` | Testnet ERC20 minting |
| Debug endpoints | ✅ | ○ | — | `apps/api/src/routes/debug/` | Dev-only utilities |

---

## Bridge Engine

| Component | Impl | Test | Scenario | Location | Notes |
|-----------|------|------|----------|----------|-------|
| Layered architecture | ✅ | — | — | `src/domain/`, `services/`, `infra/` | Clean separation |
| GlobalState builder | ✅ | ✓ | FS11 | `state/state.builder.ts` | 31 lines |
| Runtime allow/deny | ✅ | ✓ | FS12 | `runtime/*.ts` | 5 runtime files |
| Uniswap V4 quoter | ✅ | ✓ | FS15 | `evm/uniswapV4/quoter.ts` | 205 lines |
| Path evaluation | ✅ | ○ | FS16 | `pathing/evaluator.ts` | 684 lines |
| Arbitrage planner | ✅ | ✓ | FS13 | `arbitrage/planner.ts` | 869 lines |
| Clip sizing/calibration | ✅ | ○ | FS21 | `arbitrage/clip.ts` | 1176 lines |
| Strategy framework | ✅ | — | — | `strategies/types.ts` | 130 lines |
| ArbitrageStrategy | ✅ | ✓ | FS13 | `strategies/arbitrage.ts` | 679 lines |
| RebalancerStrategy | ✅ | ○ | FS22 | `strategies/rebalancer.ts` | 475 lines (full impl, not scaffold) |
| PegKeeperStrategy | ⏳ | ○ | FS23 | `strategies/pegkeeper.ts` | Framework only; buildPlan() incomplete |
| LPManagerStrategy | ⏳ | ○ | FS24 | `strategies/lpmanager.ts` | Framework only; buildPlan() incomplete |
| ExecutionEngine | ✅ | ○ | FS25 | `execution/engine.ts` | 693 lines |
| EvmExecutor | ✅ | ○ | FS26 | `evm/executor.ts` | 819 lines; LP ops stubbed for live |
| BridgeExecutor | ✅ | ○ | FS26 | `bridge/executor.ts` | 326 lines |
| IMexcClient | ✅ | — | — | `mexc/client.ts` | 150 lines (interface) |
| Paper exchange | ✅ | ✓ | FS14 | `papercex/service.ts` | Deposit/trade/reset work |
| Operation queue | 🔨 | ○ | FS27 | Implicit in plan stages | No explicit queue structure |
| Execution history | ⏳ | ○ | FS27 | Prisma schema | Schema exists; persistence partial |
| MEXC watcher | ✅ | ✓ | FS18 | `apps/watchers/src/mexc.ts` | Market data present |
| EVM pool watcher | ✅ | ✓ | FS18 | `evm/uniswapV4/watcher.ws.ts` | WebSocket + snapshots |
| Zephyr reserve watcher | ✅ | ✓ | FS18 | `domain/zephyr/reserve.ts` | Reserve info + rates |
| DB persistence | ✅ | — | — | `infra/prisma/schema.prisma` | Full schema |
| Engine CLI | ✅ | ✓ | FS17 | `apps/engine/src/cli.ts` | status/evaluate/run |
| Dashboard | ✅ | ✓ | FS19 | `apps/web/` | 14/14 pages HTTP 200 |

### Additional Engine Components (Found in Scan)

| Component | Impl | Test | Scenario | Location | Notes |
|-----------|------|------|----------|----------|-------|
| Risk controls / limits | ✅ | ○ | FS28 | `domain/risk/limits.ts` | Risk configuration exists |
| Circuit breakers | ✅ | ○ | FS28 | `domain/risk/circuitBreaker.ts` | Circuit breaker pattern impl |
| Inventory graph | ✅ | ○ | FS16 | `domain/inventory/graph.ts` | Asset connectivity for pathfinding |
| Multiple quoters | ✅ | ○ | FS29 | `domain/quoting/*.ts` | 6 quoters: onchain, state, zephyr, cex, bridge, networkEffect |
| Zephyr wallet client | ✅ | — | — | `services/zephyr/wallet.ts` | Native wallet operations |
| MEXC REST/WS clients | ✅ | — | — | `services/mexc/rest.ts`, `ws.ts` | Live market data |
| Paper ledger | ✅ | ✓ | FS14 | `domain/paper.ts` | Paper trading simulation |
| Position manager | ✅ | ○ | FS24 | `services/evm/positionManager.ts` | LP position management |

### Not Yet Implemented (Engine)

| Component | Status | Notes |
|-----------|--------|-------|
| Multi-hop routing | ❌ | Pending (single-hop only) |
| Settlement automation | ❌ | Pending |
| Live MEXC client integration | ⏳ | Code exists but not battle-tested |

---

## Summary

| Category | ✅ Complete | ⏳ Partial | 🔨 Scaffold | ⚠️ Bug | ❌ Missing |
|----------|-------------|------------|-------------|--------|------------|
| Bridge v1 (core) | 12 | 1 | 0 | 1 | 0 |
| Bridge v1 (additional) | 10 | 2 | 0 | 0 | 0 |
| Engine (core) | 20 | 3 | 1 | 0 | 0 |
| Engine (additional) | 8 | 0 | 0 | 0 | 2 |
| **Total** | **50** | **6** | **1** | **1** | **2** |

**Test Scenarios:** B11-B27 (17 bridge), FS11-FS30 (20 engine) = 37 total

---

## Known Issues & TODOs

| Location | Issue | Priority |
|----------|-------|----------|
| Pool discovery | Scanner finds 0 Initialize events on fresh Anvil | High |
| `engine.ts:228` | Pool context not passed to execution step | Medium |
| `arbitrage.ts:206` | All steps use same clip; should track pipeline output | Medium |
| `executor.ts:450-782` | LP ops (mint/burn/collect) stubbed for live mode | Low |
| `rebalancer.ts:277` | Missing same-venue internal swap logic | Low |

---

## Corrections from Original Doc

The published `bridge-testnet-v2-update.md` has some inaccuracies. This is the corrected status:

| Component | Original Says | Actual Status |
|-----------|---------------|---------------|
| RebalancerStrategy | ✅ scaffold | ✅ complete (475 lines) |
| PegKeeperStrategy | ✅ scaffold | ⏳ partial (framework only) |
| LPManagerStrategy | ✅ scaffold | ⏳ partial (framework only) |
| Operation queue | ✅ | 🔨 scaffold (implicit only) |
| Execution history | ✅ | ⏳ partial (schema, no persistence) |
| Multi-pool routing | ✅ | ⏳ partial |
| Pool discovery | ✅ | ⚠️ bug (0 events) |

---

## Test Scenario Reference

### Bridge (B11-B27)

| # | Name | What It Tests |
|---|------|---------------|
| B11 | EIP-712 Voucher Signing | Domain fields, signature, claim |
| B12 | Pre-signed Unwrap Payload | Prepare endpoint, burn with nonce |
| B13 | Claim State Machine | Full wrap E2E |
| B14 | Unwrap State Machine | Full unwrap E2E |
| B15 | Recovery & Reconcile | Admin recovery endpoints |
| B16 | Operator Watcher | Watchers, outgoing, prepared |
| B17 | Account Backup/Restore | Backup/restore flow |
| B18 | Multi-Asset | Token listing |
| B19 | Wallet Status | Status endpoints, SSE |
| B20 | Details Summary | Summary endpoint |
| B21 | Address Validation | Zephyr address validation |
| B22 | Draft Cancel | Cancel unwrap draft |
| B23 | Pool Discovery & Scanning | Initialize events, pool scanner |
| B24 | Multi-Asset Wrap Flow | ZRS/ZYS wrap/unwrap E2E |
| B25 | Swap UI E2E | Playwright swap flow |
| B26 | LP Management UI E2E | Playwright add/remove liquidity |
| B27 | Wallet UX E2E | Playwright balance/history display |

### Full-Stack (FS11-FS30)

| # | Name | What It Tests |
|---|------|---------------|
| FS11 | GlobalState Builder | `/api/state` |
| FS12 | Runtime Allow/Deny | `/api/runtime` |
| FS13 | Arbitrage Pipeline | `/api/arbitrage/*` |
| FS14 | Paper Exchange | Deposit/trade/reset |
| FS15 | Quoter System | `/api/quoters` |
| FS16 | Inventory & Pathing | `/api/inventory/*` |
| FS17 | Engine CLI | `pnpm engine` commands |
| FS18 | Watcher Health | Data from all watchers |
| FS19 | Dashboard Pages | 14/14 routes |
| FS20 | Pool Actions | `/api/pools/actions` |
| FS21 | Clip Sizing & Calibration | Clip estimates, calibration |
| FS22 | RebalancerStrategy | Inventory rebalancing |
| FS23 | PegKeeperStrategy | ZSD peg maintenance |
| FS24 | LPManagerStrategy | LP position management |
| FS25 | ExecutionEngine Paper Mode | Paper trading execution |
| FS26 | Strategy Execution E2E | Full arb execution flow |
| FS27 | Operation Queue & History | Queue/history persistence |
| FS28 | Risk Controls & Circuit Breakers | Risk limits, circuit breaker pattern |
| FS29 | Multiple Quoters System | All 6 quoters (swap, native, CEX, bridge) |
| FS30 | Faucets (EVM & Zephyr) | Testnet token distribution |

---

## Next Actions

1. **Fix pool discovery** — Debug Initialize event scanning on fresh Anvil
2. **Complete PegKeeperStrategy** — Implement `buildPlan()`
3. **Complete LPManagerStrategy** — Implement `buildPlan()`
4. **Playwright E2E** — Swap UI, LP UI, Wallet UX
5. **Execution tests** — Run `engine run --mode paper` with real arb
