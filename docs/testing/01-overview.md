# Zephyr Bridge Test Scenarios

Master test document organized by level: Infrastructure, Component Smoke, Component Features, Full Stack E2E.

**Target:** Automated execution with explicit expected states and pass/fail criteria.

**Automated runners:**
- **T1-T5:** `./scripts/run-tests.py` (unified Python runner; `make precheck` / `make test-infra` / etc.)
- **Edge:** `./scripts/run-l5-tests.py` (`make test-edge` / `make test-edge-execute`)

---

## Test Levels

| Level | Purpose | Reset Required | Approx Time | Details |
|-------|---------|----------------|-------------|---------|
| **L1: Infrastructure** | Verify services running, connectivity | No | ~2 min | Below |
| **L2: Component Smoke** | Basic functionality per component | No | ~5 min | Below |
| **L3: Component Features** | Detailed feature testing | Per group | ~15 min | [03-bridge-scenarios.md](./03-bridge-scenarios.md), [04-full-stack-scenarios.md](./04-full-stack-scenarios.md) |
| **L4: Full Stack E2E** | Cross-system flows, strategies | Yes, per scenario | ~30+ min | [05-devnet-scenarios.md](./05-devnet-scenarios.md), [06-engine-strategies.md](./06-engine-strategies.md), [L4 Reference](#l4-reference) below |
| **L5: Edge/Chaos Scope** | Security, race, failure, stress, privacy edge cases | Per scenario | Incremental | [00-edge-case-scope.md](./00-edge-case-scope.md), [08-edge-framework.md](./08-edge-framework.md) |

---

## Checkpoint Reference State

After `make dev-init` or `make dev-reset`:

```yaml
chain:
  height: ~273
  oracle_price_usd: 1.50
  reserve_ratio: 7.01  # 701% - Normal mode

wallets:
  gov:
    ZPH: 871649.99
    ZRS: 1765346.97
    ZSD: 149774.99
    ZYS: 74679.35
  miner:
    ZPH: ~2600  # varies with mining
  test:
    ZPH: 0
    ZRS: 0
    ZSD: 0
    ZYS: 0

protocol:
  total_zrs: 1765346.97
  total_zsd: 224926.12
  total_zys: 74679.35

rr_mode: normal  # >400% = normal, 200-400% = defensive, <200% = crisis
```

---

# L1: Infrastructure Tests

Verify all services are running and reachable. No reset required.

## INFRA-01: Docker Services

**Purpose:** Verify Docker infrastructure is running.

```bash
docker compose ps --format json | jq -r '.[].State'
redis-cli ping
psql -h localhost -U zephyr -d zephyrbridge_dev -c "SELECT 1"
curl -s http://127.0.0.1:8545 -X POST -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"eth_blockNumber","id":1}' | jq -r '.result'
```

**Expected:**
| Service | Check | Expected |
|---------|-------|----------|
| Redis | `redis-cli ping` | `PONG` |
| PostgreSQL | `SELECT 1` | `1` |
| Anvil | `eth_blockNumber` | hex number (not null) |

---

## INFRA-02: DEVNET Services

**Purpose:** Verify DEVNET-specific services (when running in DEVNET mode).

**Ports:** DEVNET ports (mainnet-fork ports are DEPRECATED):
- Node 1 RPC: `$DEVNET_NODE1_RPC` (default 47767)
- Node 2 RPC: `$DEVNET_NODE2_RPC` (default 47867)

```bash
NODE1_RPC="${DEVNET_NODE1_RPC:-47767}"
NODE2_RPC="${DEVNET_NODE2_RPC:-47867}"

curl -s http://127.0.0.1:5555/status | jq '.spot'
curl -s http://127.0.0.1:5556/status | jq '.oraclePriceUsd'
curl -s "http://127.0.0.1:${NODE1_RPC}/json_rpc" -d '{"jsonrpc":"2.0","id":"0","method":"get_info"}' | jq '.result.height'
curl -s "http://127.0.0.1:${NODE2_RPC}/json_rpc" -d '{"jsonrpc":"2.0","id":"0","method":"get_info"}' | jq '.result.height'
```

**Expected:**
| Service | Port | Check | Pass Criteria |
|---------|------|-------|---------------|
| Fake Oracle | 5555 | `jq '.spot'` | `1500000000000` ($1.50) |
| Fake Orderbook | 5556 | `jq '.oraclePriceUsd'` | `1.5` |
| Node 1 | `$DEVNET_NODE1_RPC` | `jq '.result.height'` | `> 0` |
| Node 2 | `$DEVNET_NODE2_RPC` | `jq '.result.height'` | `> 0` |

---

## INFRA-03: Wallet RPCs

**Purpose:** Verify all wallet RPC services respond.

**DEVNET Wallet Ports:**
| Wallet | Port | Purpose |
|--------|------|---------|
| Gov | 48769 | Main funds, conversions |
| Miner | 48767 | Mining rewards |
| Test | 48768 | User-initiated transactions |
| Bridge | 48770 | Bridge operator |
| Engine | 48771 | Engine operator |

```bash
GOV_RPC=48769; MINER_RPC=48767; TEST_RPC=48768; BRIDGE_RPC=48770; ENGINE_RPC=48771

for port in $GOV_RPC $MINER_RPC $TEST_RPC $BRIDGE_RPC $ENGINE_RPC; do
  RESULT=$(curl -s "http://127.0.0.1:$port/json_rpc" \
    -d '{"jsonrpc":"2.0","id":"0","method":"get_version"}' | jq -r '.result.version')
  echo "Port $port: $RESULT"
done
```

**Pass Criteria:**
| Wallet | Port | Pass |
|--------|------|------|
| Gov | 48769 | Non-empty version number |
| Miner | 48767 | Non-empty version number |
| Test | 48768 | Non-empty version number |
| Bridge | 48770 | Non-empty version number |
| Engine | 48771 | Non-empty version number |

---

## INFRA-04: Application Services

**Purpose:** Verify Bridge and Engine web services respond.

```bash
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:7050/api/health
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:7051/api/health
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:7000/api/health
```

**Expected:**
| Service | Port | Endpoint | Expected |
|---------|------|----------|----------|
| Bridge Web | 7050 | `/api/health` | HTTP 200 |
| Bridge API | 7051 | `/api/health` | HTTP 200 |
| Engine | 7000 | `/api/health` | HTTP 200 |

---

# L2: Component Smoke Tests

Basic functionality verification per component. No reset required.

## SMOKE-01: Zephyr Chain Health

**Purpose:** Verify Zephyr chain is operational with valid state.

```bash
RESERVE_INFO=$(curl -s http://127.0.0.1:47767/json_rpc \
  -d '{"jsonrpc":"2.0","id":"0","method":"get_reserve_info"}')
echo "$RESERVE_INFO" | jq '{
  height: .result.height,
  reserve_ratio: .result.reserve_ratio,
  num_reserves: (.result.num_reserves | tonumber / 1e12),
  num_stables: (.result.num_stables | tonumber / 1e12)
}'
```

**Expected:**
| Field | Expected |
|-------|----------|
| `height` | > 200 |
| `reserve_ratio` | "7.01" (plus/minus 0.5) at checkpoint |
| `num_reserves` | ~1,765,346 ZRS |
| `num_stables` | ~224,926 ZSD |

---

## SMOKE-02: Wallet Balances

**Purpose:** Verify gov wallet has expected asset balances.

```bash
curl -s http://127.0.0.1:48769/json_rpc \
  -d '{"jsonrpc":"2.0","id":"0","method":"get_balance","params":{"account_index":0,"all_assets":true}}' \
  | jq '.result.balances[] | {asset: .asset_type, balance: (.balance | tonumber / 1e12)}'
```

**Expected (at checkpoint):**
| Asset | Balance | Tolerance |
|-------|---------|-----------|
| ZPH | 871,649.99 | plus/minus 1000 |
| ZRS | 1,765,346.97 | plus/minus 100 |
| ZSD | 149,774.99 | plus/minus 100 |
| ZYS | 74,679.35 | plus/minus 100 |

---

## SMOKE-03: EVM Contracts

**Purpose:** Verify EVM contracts are deployed and readable.

```bash
ADDRESSES=$(cat $ROOT/zephyr-eth-foundry/.forge-snapshots/addresses.json)
WZEPH=$(echo "$ADDRESSES" | jq -r '.wZEPH')
cast call $WZEPH "totalSupply()(uint256)" --rpc-url http://127.0.0.1:8545
```

**Expected:**
| Contract | Check | Expected |
|----------|-------|----------|
| wZEPH | `totalSupply()` | >= 0 (not reverted) |
| wZSD | `totalSupply()` | >= 0 |
| wZRS | `totalSupply()` | >= 0 |
| wZYS | `totalSupply()` | >= 0 |
| PoolManager | exists | address not 0x0 |

---

## SMOKE-04: Oracle Price Control

**Purpose:** Verify oracle price can be changed (DEVNET only).

```bash
BEFORE=$(curl -s http://127.0.0.1:5555/status | jq '.spot')
make set-price PRICE=2.00
sleep 5
AFTER=$(curl -s http://127.0.0.1:5555/status | jq '.spot')
make set-price PRICE=1.50
```

**Expected:**
| Step | Expected |
|------|----------|
| Before | `spot: 1500000000000` |
| After | `spot: 2000000000000` |
| Orderbook tracking | `oraclePriceUsd: 2.0` |

---

## SMOKE-05: Bridge API Endpoints

**Purpose:** Verify Bridge API core endpoints respond.

```bash
curl -s http://127.0.0.1:7051/health | jq '.status'
curl -s http://127.0.0.1:7051/status | jq '.api'
curl -s http://127.0.0.1:7051/bridge/tokens | jq '.tokens[0].symbol'
```

**Expected:**
| Endpoint | Expected |
|----------|----------|
| `/health` | `status: "ok"` |
| `/status` | `api: "running"` |
| `/bridge/tokens` | Array with WZEPH, WZSD, WZRS, WZYS |

---

## SMOKE-06: Engine State

**Purpose:** Verify Engine has loaded state correctly.

```bash
curl -s http://127.0.0.1:7000/api/state | jq '{
  hasZephyr: (.state.zephyr != null),
  hasCex: (.state.cex != null),
  hasEvm: (.state.evm != null),
  reserveRatio: .state.zephyr.reserve.reserveRatio
}'
```

**Expected:**
| Field | Expected |
|-------|----------|
| `hasZephyr` | true |
| `hasCex` | true |
| `hasEvm` | true |
| `reserveRatio` | ~7.01 at checkpoint |

---

# L3: Component Feature Tests

Detailed testing of specific features, organized by component.

See these docs for full L3 test scenarios:

- **[03-bridge-scenarios.md](./03-bridge-scenarios.md)** - Wrap/unwrap flows (API + UI), mining, wallet balance checks
- **[04-full-stack-scenarios.md](./04-full-stack-scenarios.md)** - DEX swaps, LP management, engine setup, admin endpoints, faucets, SSE streams

### L3 Test IDs

| ID | Component | What It Tests |
|----|-----------|---------------|
| BRIDGE-01 to BRIDGE-08 | Bridge | Wallet creation, funding, wrap/unwrap (API + Playwright), multi-asset |
| ENGINE-01 to ENGINE-06 | Engine | State builder, runtime mode, paper exchange, arb detection, inventory, quoter |
| SWAP-01 | Swap UI | Basic swap interface |
| LP-01, LP-02 | LP | Pool discovery, position management |

---

# L4: Full Stack E2E Tests

Cross-system flows testing the complete bridge engine operation.

**IMPORTANT:** Each L4 test should start with `make dev-reset`

See these docs for full L4 test scenarios:

- **[05-devnet-scenarios.md](./05-devnet-scenarios.md)** - RR mode transitions, oracle control
- **L4 strategy tests** are defined below in the [L4 Reference](#l4-reference) section

### L4 Test Summary

| Category | Tests | Notes |
|----------|-------|-------|
| ARB-01 to ARB-06 | 21 variations | Arbitrage across wZEPH, wZSD, wZRS, wZYS with RR constraints |
| REBAL-01 to REBAL-03 | 3 tests | Post-arb inventory restoration, CEX balancing, cross-venue transfer |
| LP-01 to LP-04 | 4 tests | wZEPH/USDT range, wZSD/USDT peg, wZRS RR-aware, wZYS yield-tracking |
| FULL-01 to FULL-04 | 4 tests | Complete arb cycle, RR transition mid-op, multi-asset, crisis mode |

**Total L4 Tests: 32 test scenarios**

---

# L5: Edge/Chaos Scope

The edge-case catalog tracks all 146 scoped tests (138 catalog + 8 SEED) and maps each test to a primary testing doc.

**Source of truth:** [00-edge-case-scope.md](./00-edge-case-scope.md)

**Framework guide:** [08-edge-framework.md](./08-edge-framework.md)

### L5 Scope Snapshot

| Total | SCOPED-READY | SCOPED-EXPAND | SCOPED-TBC |
|-------|--------------|---------------|------------|
| 146 | 116 | 27 | 3 |

`SCOPED-TBC` items are intentionally included now for visibility; they need extra runbook-level guidance before execution steps are finalized.

---

# L4 Reference

## Reserve Ratio (RR) Modes

| RR Range | Mode | Key Restrictions |
|----------|------|------------------|
| > 800% | Normal (High RR) | ZRS mint blocked (protocol wants to reduce reserves) |
| 400-800% | Normal | All operations available |
| 100-400% | Defensive | ZSD mint blocked, ZRS mint/redeem blocked |
| < 100% | Crisis | ZSD mint blocked, ZRS blocked, ZSD redeem has haircut |

## RR Gates by Asset

| RR Range | ZSD Mint | ZSD Redeem | ZRS Mint | ZRS Redeem | ZYS |
|----------|----------|------------|----------|------------|-----|
| < 100% | Blocked | Haircut | Blocked | Blocked | OK |
| 100-400% | Blocked | OK | Blocked | Blocked | OK |
| 400-800% | OK | OK | OK | OK | OK |
| > 800% | OK | OK | Blocked | OK | OK |

**Key Insights:**
- **ZSD:** Mint requires RR >= 400%. Redeem always works (haircut below 100%).
- **ZRS:** Only fully available in 400-800% range. Most restrictive asset.
- **ZYS:** Always available (no RR gating). The "safe haven" for arb.
- **wZEPH:** No RR restrictions (free float).

## Setting Up RR Levels

```bash
# Normal high (700%)
make set-price PRICE=1.50

# Threshold testing (450% - just above ZRS gate)
make set-price PRICE=0.95

# Defensive (350%)
make set-price PRICE=0.75

# Crisis (150%)
make set-price PRICE=0.35
```

## Verifying RR Gates

```bash
curl -s http://127.0.0.1:47767/json_rpc \
  -d '{"jsonrpc":"2.0","id":"0","method":"get_reserve_info"}' | jq '{
    rr: .result.reserve_ratio,
    zrs_mint: (if (.result.reserve_ratio | tonumber) < 8 then "allowed" else "blocked" end),
    zrs_redeem: (if (.result.reserve_ratio | tonumber) > 4 then "allowed" else "blocked" end)
  }'
```

## Inventory Locations

| Venue | Assets Held | Purpose |
|-------|-------------|---------|
| **Native Wallet** | ZPH, ZSD, ZRS, ZYS | Source for wrapping, conversions |
| **EVM Wallet** | wZEPH, wZSD, wZRS, wZYS, USDT | DEX trading, LP positions |
| **CEX (Paper)** | ZEPH, USDT | Closing arb legs, hedging |
| **LP Positions** | Various pairs | Fee generation, market making |

## Price Relationships

| Asset | Peg Target | Notes |
|-------|------------|-------|
| wZEPH | CEX ZEPH price | Free float |
| wZSD | $1.00 | Stablecoin |
| wZRS | Native ZRS rate | RR-dependent |
| wZYS | Yield price | Growth only |

---

# Test Execution Order

## Recommended Sequence

```
1. L1: Infrastructure (no reset)
   INFRA-01 -> INFRA-04

2. L2: Smoke Tests (no reset)
   SMOKE-01 -> SMOKE-06

3. L3: Component Features (reset once at start)
   make dev-reset
   BRIDGE-01 -> BRIDGE-08
   ENGINE-01 -> ENGINE-06
   SWAP-01, LP-01, LP-02

4. L4: Full Stack E2E (reset before each)
   make dev-reset && ARB-01
   make dev-reset && ARB-02
   ... etc
```

## Reset Strategy

| Test Level | Reset Before | Reset After |
|------------|--------------|-------------|
| L1 | No | No |
| L2 | No | No |
| L3 | Once at start | No |
| L4 | Before each test | Optional |

---

# Reporting Format

```markdown
# Test Run: [DATE]

## Environment
- Chain Mode: DEVNET
- Checkpoint Height: 273
- Oracle Price: $1.50
- Reserve Ratio: 7.01

## Summary
| Level | Total | Pass | Fail | Skip |
|-------|-------|------|------|------|
| L1 | 4 | 4 | 0 | 0 |
| L2 | 6 | 6 | 0 | 0 |
| L3 | 14 | 12 | 2 | 0 |
| L4 | 10 | 8 | 1 | 1 |

## Failed Tests
### [TEST-ID]: [Name]
- Expected: ...
- Actual: ...
- Error: ...
```

---

# Related Documents

- **[03-bridge-scenarios.md](./03-bridge-scenarios.md)** - Bridge wrap/unwrap test flows
- **[04-full-stack-scenarios.md](./04-full-stack-scenarios.md)** - DEX, engine, admin, faucets
- **[05-devnet-scenarios.md](./05-devnet-scenarios.md)** - DEVNET mode, RR transitions
- **[06-engine-strategies.md](./06-engine-strategies.md)** - Strategy-specific evaluation tests
- **[00-edge-case-scope.md](./00-edge-case-scope.md)** - Full edge/chaos test scope with TBC markers
- **[08-edge-framework.md](./08-edge-framework.md)** - L5 execution framework and browser lane workflow
- **[02-infra-checklist.md](./02-infra-checklist.md)** - Quick infra verification
- **[zephyr-tips.md](../reference/zephyr-tips.md)** - Wallet ops, conversions, gotchas
- **[implementation-coverage.md](../reference/implementation-coverage.md)** - Component implementation status
