# Zephyr EVM Bridge: Technical Development Update

> December 2025

Technical status update on the Zephyr EVM Bridge infrastructure covering testnet v1 (live), v2 development, and the Bridge Engine.

---

## A Note on Testnet v2 & Launch

We want to take a moment to level with the community about where we are and what's been happening behind the scenes.

**The scope grew. Significantly.**

What started as MVP evolved into building an entire cross-chain operations infrastructure. The bridge itself — wrapping and unwrapping tokens — is the visible tip. Underneath, we've built so much more, and that effort is more hidden than the front end stuff that can visually be seen:

- A complete listener and event-processing pipeline for both chains
- A deterministic, idempotent transaction system with pre-signed commits
- An operator console with recovery tooling for edge cases
- Full Uniswap V4 integration with pool discovery, LP management, and multi-pool routing
- And now, an entirely separate **Bridge Engine** for market operations

Each of these systems seems to require more and more depth than initially hoped, although it was predictable. We were able to move so fast in the beginning, honestly the most fun I've had with software devleopment and it is a shame that I can't be pushing cool updates on the daily anymore!

**We've been in move-fast-and-break-things mode.**

This project has evolved rapidly as we've discovered what works, what doesn't, and what needs to be rebuilt. Some early decisions have become technical debt. For every new piece of the bridge puzzle, I've taken extra time to "do things right" test different approaches and infrastructure etc.

- For the main bridge, we have pushed the backend and architeture we ran with beyond its limits :D
- The UI was functional but needed a proper design system — the redesign branch is a ground-up rework
- The Engine started as an "arb bot" and became something much larger — it's now a full market operations system

We're not shipping v2 until it's solid. That means taking the time to:
- Consolidate the WIP branches properly
- Address the technical debt we've accumulated
- Battle-test the Engine in paper mode before it touches real operations

But we are in a really good place as it stands, it does feel that the v2 launch is juuuuuust around the corner. So close I can taste it! And I've very excited.

**Thank you for your patience.**

We know it's been a while since v1 launched. The delay isn't lack of progress — it's that the scope of what we're building has expanded to match the ambition of the protocol. Zephyr isn't just another stablecoin. The bridge infrastructure needs to reflect that.

What follows is a deep technical breakdown of everything we've built and everything in progress. We want you to see the full picture of what's coming.

---

## Table of Contents

1. [Testnet v1 — What's Live](#testnet-v1--whats-live)
2. [Wrap Pipeline Implementation](#wrap-pipeline-implementation)
3. [Unwrap Pipeline Implementation](#unwrap-pipeline-implementation)
4. [Background Workers](#background-workers)
5. [Testnet v2 — In Development](#testnet-v2--in-development)
6. [Testnet v3 — Planned](#testnet-v3--planned)
7. [Introducing the Bridge Engine](#introducing-the-bridge-engine)
8. [Market Dynamics Awareness](#market-dynamics-awareness)
9. [Bridge Engine Architecture](#bridge-engine-architecture)
10. [Engine Strategy System](#engine-strategy-system)
11. [Engine Execution Layer](#engine-execution-layer)
12. [Data Collection & Persistence](#data-collection--persistence)
13. [Implementation Status Matrix](#implementation-status-matrix)

---

## Testnet v1 — What's Live

Deployed on Ethereum Sepolia. Core bridge operations for all four assets (ZEPH, ZSD, ZRS, ZYS).

### Stack
- Next.js 
- Viem for EVM chain interaction
- Reown AppKit (WalletConnect) for wallet connection
- Redis for state management and pub/sub
- Zephyr wallet RPC (json_rpc) for native chain operations

### Deployed Components
- Wrap flow: Zephyr listener → Claims ingest → EIP-712 signer → Claim event watcher
- Unwrap flow: Prepare endpoint → Burn event watcher → Unwrap ingest → Relay
- Operator console with Redis explorer, API tester, watcher controls
- Recovery endpoints for reconciling stuck transactions
- SSE streams for real-time claim/unwrap status updates
- Faucets for test asset distribution (EVM and Zephyr)

### Uniswap V4 Integration
- Pool discovery from PoolManager `Initialize` logs
- Slot0 fetching via StateView contract
- On-chain quoter for swap quotes with multi-pool routing (liquidity-prioritized)
- Multi-pool support per token pair with automatic best-path selection
- Activity feed with swap/mint/burn events
- Position tracking with range bounds
- Background watchers for positions and activity
- LP management UI with multi-pool management per ticker
- Wallet UX with balance and history display per connected wallet

---

## Wrap Pipeline Implementation

### Listener Layer (`lib/zephyr/listener.ts`)

Polls Zephyr wallet RPC for incoming transfers:

- Configurable poll interval (default 120s, env: `ZEPH_POLL_MS`)
- Scans from `ZEPHYR_LAST_WALLET_HEIGHT` with lookback window for reorg tolerance
- Processes both mempool (`pool`) and confirmed (`in`) transfers
- Writes raw transfers to `zephyr:incoming` hash
- Falls back to polling if `--block-notify` is stale (>5 min)
- Supports external notify hooks: `ingestWalletTxNotify()` and `ingestBlockNotify()`

### Ingest Layer (`lib/claims/ingest.ts`)

Converts Zephyr transfers to claim records:

- **Claim ID derivation**: `toBytes32Hex(zephTxId)` — deterministic, idempotent
- **Decimal conversion**: Zephyr uses 12 decimals, converts to token decimals (12-18)
- **Address resolution**: Looks up `bridge:accounts` hash for EVM destination
- **On-chain verification**: Checks `usedZephyrTx(token, id)` to detect already-claimed
- **Status progression**: `pending → queued → ready` based on confirmations
- **Auto-signing**: Triggers `signClaim()` when status reaches `ready`

### Signer Layer (`lib/claims/signer.ts`)

Generates EIP-712 vouchers:

- **Lock mechanism**: Redis `SET NX` with 15s TTL on `claims:sign:lock:<id>`
- **Final on-chain check**: Re-verifies `usedZephyrTx` before signing
- **Domain**: `{ name: "ZephyrClaims", version: "1", chainId, verifyingContract: token }`
- **Message types**: `to (address), amount (uint256), zephyrTxHash (bytes32), deadline (uint256)`
- **TTL**: Configurable via `VOUCHER_TTL_SECS` (default 86400)
- **Status update**: `ready → claimable` with signature and deadline stored

### Event Watcher (`lib/claims/eventWatcher.ts`)

Monitors EVM for `MintedFromZephyr` events:

- Watches all wrapped token contracts in parallel
- Backfills from `claims:lastEventBlock` on startup
- Uses WebSocket transport with HTTP fallback
- Updates claim records: backfills `evmTxHash`, sets status to `claimed`
- Refreshes wrapped token supply cache on mint

### Claim Status State Machine

```
pending   → No EVM address mapping found
queued    → In block, waiting for confirmations  
ready     → Confirmations met, awaiting signature
claimable → Signature generated, user can claim
claimed   → MintedFromZephyr event detected
expired   → Deadline passed without claim
```

---

## Unwrap Pipeline Implementation

### Prepare Endpoint (`/api/unwraps/prepare`)

Pre-signs Zephyr transfer before EVM burn:

1. Validates destination address via `validateZephyrAddress()`
2. Computes amounts: `computeOutgoingAmounts()` with bridge fee (env: `ZEPH_TRANSFER_FEE`)
3. Calls wallet RPC `transfer` with `do_not_relay: true, get_tx_metadata: true`
4. Stores in `zephyr:prepared` and `zephyr:outgoing` hashes
5. Computes wallet fingerprint: `keccak256(primaryAddress.toLowerCase())`
6. Returns encoded burn payload and commit hash

### Burn Payload Encoding (`lib/unwraps/payload.ts`)

ABI-encoded payload for `burnWithData`:

```
version (uint8)          — Currently 1
txHash (bytes32)         — Pre-signed Zephyr tx hash
walletFingerprint (bytes32) — Identifies expected signing wallet
destination (bytes)      — Zephyr destination address (variable length)
```

Decoder handles legacy (raw destination bytes) and structured (version 1) payloads.

### Burn Event Watcher (`lib/unwraps/eventWatcher.ts`)

Monitors wrapped token contracts for `Burned` events:

- Event signature: `Burned(address indexed from, uint256 amount, bytes zephDestination, bytes32 indexed nonce)`
- Decodes payload to extract commit hash and wallet fingerprint
- Creates unwrap record with ID: `<evmTxHash>:<logIndex>`
- Persists to `unwraps:records` hash
- Triggers `ingestEvmBurn()` for relay processing

### Ingest & Relay (`lib/unwraps/ingest.ts`)

Matches burns to prepared drafts and relays:

1. **Draft lookup**: Matches `preparedZephTxHashHex` to `zephyr:outgoing` entry
2. **Hydration check**: If wallet already broadcast, hydrate from `getTransferByTxid()`
3. **Lock acquisition**: Redis `SET NX` with 120s TTL on `unwrap:send:lock:<id>`
4. **Metadata verification**: Confirms `txMetadata` exists on outgoing draft
5. **Relay**: Calls `relayZephyrTransfer(metadata)` → wallet RPC `relay_tx`
6. **Hash verification**: Confirms relayed hash matches commit
7. **Status updates**: `pending → sending → sent`, marks outgoing as `sent`, prepared as `relayed`

### Wallet Confirmation

Zephyr listener polls outgoing transfers and:
- Matches by tx hash to unwrap records
- Updates `zephBlockHeight`, `zephConfirmations`
- Sets status to `confirmed`
- Marks failed if not found after grace period (env: `ZEPH_OUT_NOT_FOUND_FAIL_MS`)

### Unwrap Status State Machine

```
pending    → Burn detected, awaiting relay
sending    → Lock acquired, calling relay_tx
sent       → Zephyr tx broadcast
confirmed  → Wallet confirms outgoing transfer
failed     → Error during relay or tx not found
```

### Reconcile Status

Tracks payload verification state:
- `false` — Legacy payload without commit
- `partial` — Commit present but draft not matched
- `true` — Commit matched and verified

---

## Background Workers

Initialized via `lib/bootstrap.ts` on server startup. Each watcher runs as a singleton and gracefully shuts down on SIGINT/SIGTERM.

**Zephyr Listener**
Polls the Zephyr wallet RPC for incoming and outgoing transfers. Incoming transfers trigger claim ingestion; outgoing transfers confirm unwrap settlements. Maintains wallet height cursor for reorg tolerance.

**Claim Event Watcher**
Monitors wrapped token contracts for `MintedFromZephyr` events. Backfills missed events on startup, updates claim records to `claimed` status, and refreshes supply cache.

**Unwrap Event Watcher**
Monitors wrapped token contracts for `Burned` events. Decodes burn payloads to extract commit hashes and wallet fingerprints, creates unwrap records, and triggers relay processing.

**Uniswap V4 Positions Watcher**
Polls LP positions for tracked pools. Tracks position ranges, liquidity amounts, and fee accrual for the operator's positions.

**Uniswap V4 Activity Watcher**
Watches for swap and liquidity events on Uniswap V4 pools. Maintains activity feed for UI display and TVL calculations.

---

## Testnet v2 — In Development

### UI Redesign (`redesign` branch)

~29 commits ahead of master. Major changes:

**New Flow System**
- Card-based flow with staged progression
- Shared flow primitives across wrap/unwrap
- `wrap-new/` and `unwrap-new/` pages with redesigned UX

**Design System**
- Typography standardization
- Color palette with CSS variables
- Component library in `design-system/`
- Consistent spacing and layout primitives

**Animations**
- Staggered reveal animations on page load
- Flow card transitions
- LogoSpinner component for loading states

**Admin Improvements**
- Redesigned admin console
- Details page v2
- LPs page v2

### Database Migration (`prisma-migration` branch)

1 commit ahead of master. Experimental:

- Migrates core state from Redis hashes to PostgreSQL tables
- Uses Prisma ORM for type-safe queries
- Preserves existing API contracts
- Enables richer querying and analytics
- Under evaluation for v2 or future release

---

## Testnet v3 — Planned

### Zephyr Lite Integration

Zephyr Lite is a browser extension wallet for the Zephyr network. The bridge infrastructure includes integration scaffolding:

- **zephyr-lite-client**: TypeScript client library for wallet communication
- **zephyr-lite-react**: React components including `ZephyrHeroButton` for wallet connection
- **Connection provider**: `ZephyrConnectionProvider` wraps the app for wallet state management
- **Wrap flow integration**: Native Zephyr address selection from connected Lite wallet
- **Unwrap flow integration**: Destination address picker from Lite accounts

Current state: Feature-flagged via `NEXT_PUBLIC_ENABLE_ZEPHYR_LITE`. Extension under development, integration scaffolding in place. Target: Testnet v3.

---

## Introducing the Bridge Engine

The Zephyr Bridge handles the mechanical wrapping and unwrapping of tokens — moving assets between the Zephyr network and EVM chains. But a bridge alone doesn't ensure a healthy market.

**The Bridge Engine** is the operational layer that keeps the cross-chain ecosystem aligned. It's the system responsible for:

- **Price alignment**: Detecting and correcting price discrepancies between EVM pools, the native protocol, and centralized exchanges
- **Peg maintenance**: Ensuring WZSD trades close to $1.00 on EVM, intervening when it deviates
- **Inventory rebalancing**: Moving liquidity between venues as market conditions shift
- **LP operations**: Managing liquidity positions, collecting fees, adjusting ranges

The bridge *connects* the networks. The engine *harmonizes* them.

Without the engine, wrapped assets on EVM could trade at arbitrary premiums or discounts with no corrective force. The engine monitors all venues continuously, identifies opportunities where intervention would improve market health, and executes operations to restore alignment.

It's built as a strategy-based system where different strategies handle different market dynamics:
- **Arbitrage Strategy**: Closes price gaps between venues
- **Peg Keeper Strategy**: Maintains stablecoin peg on EVM pools
- **Rebalancer Strategy**: Redistributes inventory across venues
- **LP Manager Strategy**: Manages LP positions and fee collection

The engine is RR-aware, meaning it adapts its behavior based on the protocol's reserve ratio state. It understands that during low RR conditions, certain native operations are blocked, and adjusts strategies accordingly.

---

## Market Dynamics Awareness

The engine operates with awareness of Zephyr's unique protocol mechanics.

### Reserve Ratio Gates

The Reserve Ratio (RR) controls which native operations are available:

| RR Range | ZSD Mint | ZSD Redeem | ZRS Mint | ZRS Redeem | ZYS |
|----------|----------|------------|----------|------------|-----|
| < 100% | ❌ | ⚠️ haircut | ❌ | ❌ | ✅ |
| 100-400% | ❌ | ✅ | ❌ | ❌ | ✅ |
| 400-800% | ✅ | ✅ | ✅ | ✅ | ✅ |
| > 800% | ✅ | ✅ | ❌ | ✅ | ✅ |

**Key implications:**
- ZRS has the narrowest operating window (400-800%). Outside this range, native ZRS operations are blocked, making WZRS on EVM harder to arbitrage against native.
- ZSD redemption always works, but takes a haircut below 100% RR.
- ZYS operations are always available (ZSD ↔ ZYS unrestricted).
- EVM markets are unrestricted — they trade existing supply without minting/redeeming.

### Dual Pricing Protection

The protocol uses dual pricing (spot vs moving average) to protect against oracle manipulation:

```
Mint rate  = MAX(spot, MA)  → User pays more
Redeem rate = MIN(spot, MA) → User receives less
```

The engine factors this spread into profitability calculations. After price pumps, MA lags spot, creating an effective cost for redemptions that must be accounted for.

### Feedback Loop Awareness

Every action affects the system being measured:
- Our trades impact CEX/EVM prices
- Price changes update the oracle (per block)
- Oracle changes affect RR
- RR changes affect available operations

The engine re-checks conditions between operation steps, especially for large operations that could push RR across thresholds.

### Strategy Mode Adaptation

Strategies adapt based on RR level:

| Mode | RR | Behavior |
|------|-----|----------|
| Normal | ≥ 400% | Full operations available. Standard thresholds. |
| Defensive | 200-400% | Wider tolerances, avoid ZRS, factor in spot/MA spread. |
| Crisis | < 200% | Conservative. Only buy ZSD at significant discount. Wait for recovery. |

---

## Bridge Engine Architecture

Separate project (`zephyr-bridge-engine`). Not deployed in v1. Strategy-based market operations system.

### Layer Structure

```
┌────────────────────────────────────────────────────────────────────┐
│                          APPLICATIONS                               │
│  apps/watchers/     — Data collection CLI (MEXC, EVM, Zephyr)      │
│  apps/engine/       — Strategy loop CLI                             │
│  apps/web/          — Dashboard (queue, history, paper exchange)    │
└────────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────────┐
│                           SERVICES                                  │
│  mexc/       — REST, WebSocket, paper/live client abstraction       │
│  evm/        — Viem, Uniswap V4 quoter, swap executor               │
│  zephyr/     — RPC client, wallet operations                        │
│  bridge/     — Wrap/unwrap executor (coordinates with zephyr-bridge)│
│  papercex/   — Database-backed paper exchange with real Zephyr RPC  │
│  arbitrage/  — Service facade for plan building                     │
└────────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────────┐
│                            DOMAIN                                   │
│  state/      — GlobalState types and builders                       │
│  runtime/    — Allow/deny logic per operation                       │
│  quoting/    — On-chain and offline quoters                         │
│  pathing/    — Asset graph, path finding, evaluation                │
│  arbitrage/  — Planner, clip sizing, calibration                    │
│  inventory/  — Balance sync, allocation tracking                    │
│  execution/  — Engine types, timing config                          │
│  strategies/ — Strategy interface + implementations                 │
│  watcher/    — Base Watcher class                                   │
└────────────────────────────────────────────────────────────────────┘
┌────────────────────────────────────────────────────────────────────┐
│                             INFRA                                   │
│  Prisma (PostgreSQL)                                                │
│  - Pools, Tokens, PoolStateSnapshots, SwapEvents                    │
│  - MarketSnapshot, ReserveSnapshot (time-series)                    │
│  - OperationQueue, ExecutionHistory                                 │
│  - InventoryBalance, LPPosition                                     │
│  - PaperExchange* (accounts, subaddresses, trades)                  │
└────────────────────────────────────────────────────────────────────┘
```

### GlobalState

Unified venue snapshot consumed by runtimes, quoters, and strategies:

```
GlobalState {
  zephyr: ZephyrState {
    height: number
    reserve: ReserveState {
      zephPriceUsd: number
      reserveRatio: number
      reserveRatioMovingAverage: number
      rates: {
        zeph: { spot, movingAverage }
        zsd: { spot, movingAverage, mint, redeem, spotUSD }
        zrs: { spot, movingAverage, mint, redeem, spotUSD }
        zys: { spot, movingAverage, mint, redeem, spotUSD }
      }
      policy: {
        zsd: { mintable, redeemable }
        zrs: { mintable, redeemable }
        zys: { mintable, redeemable }
      }
    }
    feesBps: { convertZSD: 10, convertZRS: 100, convertZYS: 10 }
    durations: { unlockBlocks: 10, estUnlockTimeMs: ~20min }
  }
  bridge?: BridgeState { wrapFee, unwrapFee, confirmations }
  evm?: EvmState { pools, gasPrice, watcherHealth }
  cex?: CexState { markets, fees, durations }
}
```

### Runtime Layer

Stateless adapters answering "Can we perform this operation now?"

**Interface:**
```
OperationRuntime<Context> {
  id: OpType
  enabled(from, to, state): boolean
  buildContext(from, to, state): Context | null
  durationMs?(from, to, state): number
}
```

**Implementations:**
- `nativeMintRuntime` — Checks RR gates for ZSD/ZRS minting
- `nativeRedeemRuntime` — Checks RR gates for ZRS redemption
- `swapEvmRuntime` — Validates pool exists, has liquidity, data is fresh
- `wrapRuntime` / `unwrapRuntime` — Bridge availability checks
- `tradeCexRuntime` — Market freshness, depth availability
- `depositRuntime` / `withdrawRuntime` — CEX status checks

**RR Policy Gates:**
| RR Range | ZSD Mint | ZSD Redeem | ZRS Mint | ZRS Redeem | ZYS |
|----------|----------|------------|----------|------------|-----|
| < 100% | ❌ | ⚠️ haircut | ❌ | ❌ | ✅ |
| 100-400% | ❌ | ✅ | ❌ | ❌ | ✅ |
| 400-800% | ✅ | ✅ | ✅ | ✅ | ✅ |
| > 800% | ✅ | ✅ | ❌ | ✅ | ✅ |

**Dual Pricing:**
- Mint rate: `max(spot, movingAverage)` — user pays more
- Redeem rate: `min(spot, movingAverage)` — user receives less

### Quoting System

**On-Chain Swap Quoter** (`quoting.onchain.swap.ts`):
- Queries Uniswap V4 quoter contract
- Uses `debug_traceCall` for balance delta extraction
- Calculates price impact from pre/post sqrtPriceX96
- Returns `amountOut`, `estGasWei`, `priceImpactBps`, `poolImpact`

**Native Quoter** (`quoting.zephyr.ts`):
- Uses runtime context for rate and fee
- Calculates: `grossOut = amountIn * rate`, `netOut = grossOut - (grossOut * feeBps / 10000)`
- Returns `amountOut`, `feePaid`, `policy` status

**CEX Quoter** (`quoting.cex.ts`):
- Walks order book to simulate fill
- Deducts taker fee
- Returns `amountOut`, `feePaid`, `averageFillPrice`, `depthLevelsUsed`

### Inventory Graph

Defines asset connectivity across venues:

```
ASSET_STEPS = {
  "ZEPH.n": [
    { from: "ZEPH.n", to: "WZEPH.e", op: "wrap", venue: "evm" },
    { from: "ZEPH.n", to: "ZEPH.x", op: "deposit", venue: "cex" },
    { from: "ZEPH.n", to: "ZSD.n", op: "nativeMint", venue: "native" },
    { from: "ZEPH.n", to: "ZRS.n", op: "nativeMint", venue: "native" },
  ],
  "WZSD.e": [
    { from: "WZSD.e", to: "USDT.e", op: "swapEVM", venue: "evm" },
    { from: "WZSD.e", to: "WZEPH.e", op: "swapEVM", venue: "evm" },
    { from: "WZSD.e", to: "WZYS.e", op: "swapEVM", venue: "evm" },
    { from: "WZSD.e", to: "ZSD.n", op: "unwrap", venue: "native" },
  ],
  // ... all 12 assets
}
```

**Path Finding:** DFS with cycle detection, returns paths sorted by hop count.

**Path Evaluation:**
1. For each step: check `runtime.enabled()`, get quote via `invokeQuoter()`
2. Track: `amountIn`, `amountOut`, `feeBps`, `gasWei`, `allowed`
3. Score: `allowed`, `disallowedSteps`, `inventoryStatus`, `hopCount`, `totalCostUsd`, `totalFeeBps`

---

## Engine Strategy System

### Strategy Interface

```
Strategy {
  id: string
  name: string
  
  evaluate(state: GlobalState, inventory: InventorySnapshot): StrategyEvaluation
  buildPlan(opportunity, state, inventory): OperationPlan | null
  shouldAutoExecute(plan, config): boolean
}
```

### RR-Aware Mode Selection

```
RRMode = determineRRMode(reserveRatio):
  >= 4.0  → "normal"
  >= 2.0  → "defensive" 
  < 2.0   → "crisis"
```

Strategies adapt behavior based on RR mode (thresholds, auto-execute rules, blocked operations).

### Implemented Strategies

**ArbitrageStrategy**
- Detects price gaps using `analyzeArbMarkets()`
- Builds from `ARB_DEFS` (8 definitions: 2 directions × 4 assets)
- RR-aware auto-execute (blocks ZRS in defensive mode)
- Spot/MA spread guards

**PegKeeperStrategy**
- Monitors WZSD/USDT pool price
- Thresholds: 30bps normal, 100bps defensive
- Crisis mode: only buy ZSD at discount
- Scaffold implemented, `buildPlan()` in progress

**RebalancerStrategy**
- Target allocations per venue (e.g., 30% EVM, 50% Native, 20% CEX)
- Triggers when deviation exceeds 10%
- Generates wrap/unwrap/deposit/withdraw steps
- Scaffold implemented

**LPManagerStrategy**
- Monitors LP position ranges
- Triggers when price exits range
- Fee collection logic
- Scaffold implemented

### Arbitrage Definitions

```
ARB_DEFS = [
  {
    asset: "ZEPH",
    direction: "evm_discount",
    open: [{ from: "WZSD.e", to: "WZEPH.e", op: ["swapEVM"] }],
    close: {
      native: [{ from: "ZEPH.n", to: "ZSD.n", op: ["nativeMint"] }],
      cex: [{ from: "ZEPH.x", to: "USDT.x", op: ["tradeCEX"] }],
    },
  },
  {
    asset: "ZEPH",
    direction: "evm_premium",
    open: [{ from: "WZEPH.e", to: "WZSD.e", op: ["swapEVM"] }],
    close: {
      native: [{ from: "ZSD.n", to: "ZEPH.n", op: ["nativeRedeem"] }],
      cex: [{ from: "USDT.x", to: "ZEPH.x", op: ["tradeCEX"] }],
    },
  },
  // + 6 more for ZSD, ZRS, ZYS
]
```

### Clip Sizing

**Heuristic estimation:**
- Uses 10% of pool capacity as max clip
- Fallback to $500 minimum

**Two-venue calibration:**
- Binary search for optimal size that:
  1. Moves EVM price to match reference (native or CEX)
  2. Maximizes net USD profit after fees/gas

---

## Engine Execution Layer

### BridgeEngine Loop

```
1. buildGlobalState()
2. Check freshness (skip if stale)
3. loadInventorySnapshot()
4. For each strategy:
   a. strategy.evaluate(state, inventory) → opportunities
   b. For each opportunity:
      - strategy.buildPlan() → plan
      - If manualApproval: queue to OperationQueue
      - Else if shouldAutoExecute(): execute
5. processApprovedQueue()
6. syncInventoryToDb()
7. Sleep → repeat
```

### ExecutionEngine

Dispatches to venue-specific executors:

```
ExecutionEngine
    │
    ├── EvmExecutor
    │   • swapEVM (Uniswap V4 router)
    │   • unwrap (burn tx)
    │   • claim (mint voucher)
    │
    ├── BridgeExecutor
    │   • wrap (coordinate with zephyr-bridge)
    │   • unwrap (coordinate with zephyr-bridge)
    │
    └── IMexcClient
        ├── MexcLiveClient (real API)
        └── MexcPaperCexBridgeClient (database + real Zephyr wallet)
            • tradeCEX
            • deposit
            • withdraw
```

### Timing Configuration

Realistic delays for paper mode testing:

| Operation | Duration |
|-----------|----------|
| EVM swap | 15s |
| CEX trade | 2s |
| Bridge wrap | 20 min |
| Bridge unwrap | 20 min |
| MEXC deposit (ZEPH) | 40 min (20 conf) |
| MEXC deposit (USDT) | 5 min |
| MEXC withdraw | 5 min |
| Zephyr unlock | 20 min |

### Paper Exchange

Database-backed CEX simulation:
- Real Zephyr wallet RPC (regtest) for deposits/withdrawals
- Real subaddress creation
- PostgreSQL persistence (accounts, trades, withdrawals)
- Web UI at `/exchange`

---

## Data Collection & Persistence

### Watchers

| Watcher | Source | Output | Cadence |
|---------|--------|--------|---------|
| MEXC | WebSocket (protobuf) | `MarketSnapshot` table | Real-time |
| EVM Pools | HTTP/WS | `Pool`, `PoolStateSnapshot` tables | Event-driven |
| Zephyr Reserve | HTTP polling | `ReserveSnapshot` table | Configurable |

### Database Models (Prisma)

**Time-series:**
- `MarketSnapshot` — CEX bid/ask/depth
- `ReserveSnapshot` — RR, rates, policy flags

**Operation tracking:**
- `OperationQueue` — Pending/approved operations
- `ExecutionHistory` — Completed executions with step results

**State:**
- `InventoryBalance` — Holdings per asset/venue
- `LPPosition` — LP position tracking

---

## Implementation Status Matrix

### Zephyr Bridge (v1 Live)

| Component | Status |
|-----------|--------|
| Wrap pipeline (listener → ingest → signer → watcher) | ✅ |
| Unwrap pipeline (prepare → burn watcher → ingest → relay) | ✅ |
| Multi-asset support (ZEPH, ZSD, ZRS, ZYS) | ✅ |
| EIP-712 voucher signing | ✅ |
| Pre-signed commit-before-burn | ✅ |
| Redis state management | ✅ |
| SSE real-time streams | ✅ |
| Operator admin console | ✅ |
| Recovery/reconcile endpoints | ✅ |
| Uniswap V4 pool discovery | ✅ |
| Uniswap V4 swap/LP UI | ✅ |
| Multi-pool routing (liquidity-prioritized) | ✅ |
| LP management (multi-pool per ticker) | ✅ |
| Wallet UX (balance, history display) | ✅ |
| Multi-environment configs | ✅ |

### Zephyr Bridge (v2 Development)

| Component | Branch | Status |
|-----------|--------|--------|
| UI redesign / flow cards | `redesign` | ⏳ 29 commits |
| Design system | `redesign` | ⏳ |
| PostgreSQL migration | `prisma-migration` | 🔬 Experimental |

### Zephyr Bridge (v3 Planned)

| Component | Status |
|-----------|--------|
| Zephyr Lite extension wallet | 🔬 In development |
| Wrap/unwrap Lite integration | ⏳ Scaffolded |

### Bridge Engine

| Component | Status |
|-----------|--------|
| Layered architecture | ✅ |
| GlobalState builder | ✅ |
| Runtime allow/deny logic | ✅ |
| On-chain Uniswap V4 quoter | ✅ |
| Path evaluation | ✅ |
| Arbitrage planner | ✅ |
| Clip sizing/calibration | ✅ |
| Strategy framework | ✅ |
| ArbitrageStrategy | ✅ |
| RebalancerStrategy | ✅ scaffold |
| PegKeeperStrategy | ✅ scaffold |
| LPManagerStrategy | ✅ scaffold |
| ExecutionEngine | ✅ |
| EvmExecutor | ✅ |
| BridgeExecutor | ✅ |
| IMexcClient abstraction | ✅ |
| Paper exchange | ✅ |
| Operation queue | ✅ |
| Execution history | ✅ |
| MEXC watcher | ✅ |
| EVM pool watcher | ✅ |
| Zephyr reserve watcher | ✅ |
| DB persistence | ✅ |
| Engine CLI | ✅ |
| Dashboard | ✅ |
| Risk controls | ❌ Pending |
| Circuit breakers | ❌ Pending |
| Multi-hop routing | ❌ Pending |
| Settlement automation | ❌ Pending |
| Live MEXC client | ❌ Pending |

---

## Next Steps

**Testnet v2:**
- Merge redesign branch (UI overhaul)
- Evaluate prisma-migration for inclusion

**Testnet v3:**
- Complete Zephyr Lite extension development
- Enable Lite integration in bridge UI

**Engine:**
- Complete E2E paper mode testing
- Implement risk controls and circuit breakers
- Strategy `buildPlan()` completion for non-arb strategies
- Settlement automation

**Production:**
- Monitoring and alerting infrastructure
- Load testing
- Mainnet deployment preparation

---
