# DEVNET Test Scenarios

Test scenarios specific to DEVNET mode, enabling controllable oracle prices and RR mode testing.

> **Edge-case scope:** This doc is the primary target for `ZB-RR` and `ZB-LOAD` scenarios in [00-edge-case-scope.md](./00-edge-case-scope.md).
>
> **Runner:** Use `make test-l5` (or `./scripts/run-l5-tests.py`) for L5 planning/lint.
>
> **TBC note:** Any scenario marked `SCOPED-TBC` in the scope catalog still needs command-level runbook guidance before execution.

## Overview

DEVNET mode provides:
- **Controllable Oracle**: Set any ZEPH/USD price via `make set-price`
- **Fake Orderbook**: MEXC-compatible API tracking oracle price
- **Fresh Chain**: No mainnet state, fast startup (~5 min first time)
- **Fast Reset**: Return to known state in ~30 seconds
- **RR Mode Testing**: Trigger defensive/crisis modes on demand

## Starting DEVNET

**First time (full init):**
```bash
# Build DEVNET binaries (if not done)
make build

# Start DEVNET stack - takes ~5-6 min, creates checkpoint automatically
make dev-init
```

**Between tests (recommended):**
```bash
# Light reset - pops blocks to checkpoint, rescans wallets (~30 sec)
make dev-reset
```

**When to use which:**

| Situation | Command | Time |
|-----------|---------|------|
| First time starting DEVNET | `make dev-init` | ~5-6 min |
| DEVNET already initialized, need fresh state | `make dev-reset` | ~30 sec |
| Running multiple test scenarios | `make dev-reset` between each | ~30 sec |
| Something went wrong, need clean slate | `make dev-init` | ~5-6 min |

**Best practice:** Use `make dev-reset` for most testing. It's faster and provides consistent, repeatable state.

---

## Init Process Walkthrough

When you run `make dev-init`, here's what happens:

### Stage 1: Infrastructure Startup

| Step | What Happens | Result |
|------|--------------|--------|
| Clean slate | Stops any existing DEVNET, wipes `/tmp/zephyr-devnet` | Fresh start |
| Fake Oracle | Starts with spot price $1.50 | `http://127.0.0.1:5555` |
| Node 1 | Starts with `--fixed-difficulty 1` (instant mining) | RPC on port 47767 |
| Node 2 | Starts, peers with Node 1 | RPC on port 47867 |
| Wallet RPCs | Gov (48769), Miner (48767), Test (48768) | All connected to Node 1 |

### Stage 2: Wallet Setup

| Wallet | How Created | Purpose |
|--------|-------------|---------|
| **Gov** | Restored from deterministic keys | Holds governance premine |
| **Miner** | Fresh wallet | Receives mining rewards |
| **Test** | Fresh wallet | Available for testing |

### Stage 3: Mining to Unlock Premine

Mining starts → blocks mined → governance premine unlocks at height 60+

At height 70, Gov wallet has **~1,921,650 ZPH** unlocked (the governance premine).

### Stage 4: Asset Minting

The init mints all Zephyr asset types to create a realistic protocol state:

**Phase 1: ZRS Minting** (Reserve tokens)
- 3 rounds × 300,000 ZPH each = 900,000 ZPH → ZRS
- 12-block wait between rounds for outputs to unlock

**Phase 2: ZSD Minting** (Stablecoin)
- 20-block wait for ZPH change outputs to fully unlock
- 3 rounds × 50,000 ZPH each = 150,000 ZPH → ~225,000 ZSD
- 12-block wait between rounds

**Phase 3: ZYS Minting** (Yield tokens)
- 20-block wait for ZSD outputs to unlock
- 3 rounds × 25,000 ZSD each = 75,000 ZSD → ZYS
- 12-block wait between rounds
- 15-block final wait for all outputs to unlock

### Post-Init State (Checkpoint)

After init completes (~5-6 min), a checkpoint is automatically saved with this state:

**Network:**
| Component | Status |
|-----------|--------|
| Nodes | 2 synchronized, mining active |
| Oracle | $1.50 spot price |
| Reserve Ratio | ~700% (normal mode) |
| Chain Height | ~270 blocks |

**Gov Wallet Balances (All Unlocked):**
| Asset | Amount | Purpose |
|-------|--------|---------|
| ZPH | ~871,650 | Native token (remaining after mints) |
| ZRS | ~1,765,350 | Reserve tokens |
| ZSD | ~149,775 | Stablecoin |
| ZYS | ~74,680 | Yield tokens |

**Protocol State:**
| Metric | Value |
|--------|-------|
| Reserve Ratio | ~701% |
| Total ZRS Supply | ~1,765,350 |
| Total ZSD Supply | ~224,925 |
| Total ZYS Supply | ~74,680 |

**Miner Wallet:** Small ZPH balance from mining rewards during init.

**Test Wallet:** Empty, ready for testing.

This state provides:
- All 4 asset types with sufficient liquidity
- Healthy reserve ratio (701%) in normal mode
- Multiple outputs per asset for ring signatures
- Ready for price manipulation and RR mode testing

---

## Zephyr CLI

The `zephyr-cli` tool (in the zephyr repo) provides high-level wallet commands for DEVNET:

```bash
# Set ZEPHYR_CLI for convenience (or use the full path)
ZEPHYR_CLI="$ZEPHYR_REPO_PATH/tools/zephyr-cli/cli"

# Check all wallet balances
$ZEPHYR_CLI balances

# Transfer funds between named wallets
$ZEPHYR_CLI send gov test 1000           # 1000 ZPH: gov -> test
$ZEPHYR_CLI send gov test 500 ZSD        # 500 ZSD: gov -> test

# Convert assets (self-transfer mint/redeem)
$ZEPHYR_CLI convert gov 50000 ZPH ZSD    # Mint ZSD from ZPH
$ZEPHYR_CLI convert gov 25000 ZSD ZYS    # Mint ZYS from ZSD

# Oracle price
$ZEPHYR_CLI price                        # Get current price
$ZEPHYR_CLI price 2.00                   # Set price to $2.00

# Protocol info
$ZEPHYR_CLI reserve_info
$ZEPHYR_CLI supply_info

# Interactive mode (REPL)
$ZEPHYR_CLI
```

Bridge-orch also wraps common operations:
```bash
make fund WALLET=test AMOUNT=1000         # Send 1000 ZPH to test wallet
make fund WALLET=test AMOUNT=100 ASSET=ZSD  # Send 100 ZSD to test wallet
$ZEPHYR_CLI balances                      # Show all balances
```

---

## Quick Verification

```bash
# Verify services are running
curl -s http://127.0.0.1:5555/status   # Fake oracle
curl -s http://127.0.0.1:5556/status   # Fake orderbook
curl -s http://127.0.0.1:7000/api/state | jq '.state.cex.markets'

# Check wallet balances (zephyr-cli)
$ZEPHYR_CLI balances

# Check current RR mode
curl -s http://127.0.0.1:7000/api/runtime | jq '.mode'

# Check service status
make status
```

---

## Test Workflow (Recommended)

For each test scenario:

```bash
# 1. Reset to known state (if DEVNET already running)
make dev-reset

# 2. Run your test scenario
# ...

# 3. Reset again for next test
make dev-reset
```

This ensures:
- Consistent starting state for each test
- Fast turnaround (~30 sec reset vs ~5 min full init)
- Reproducible test results

### Save/Restore Snapshots

For complex test sequences, save and restore named snapshots to avoid full re-init:

```bash
# Save current DEVNET state (persists across reboots, stored in ~/.zephyr-devnet/snapshots/)
./scripts/save-devnet.sh my-test-state

# ... run tests, make changes ...

# Restore to saved state
./scripts/restore-devnet.sh my-test-state

# Save without a name (uses "default")
./scripts/save-devnet.sh
./scripts/restore-devnet.sh
```

Snapshots are more powerful than checkpoints — they preserve the full chain state (node data, wallets, oracle config) and survive reboots, while checkpoints only track block height.

---

## DN01: RR Mode Transitions

**Purpose**: Verify engine correctly transitions between normal/defensive/crisis modes based on reserve ratio.

### Preparation

```bash
# Reset to clean state (if DEVNET already running)
make dev-reset

# Or start fresh (if DEVNET not running)
make dev-init
```

### Steps

```bash
# 1. Verify DEVNET services are running
make status

# 2. Wait for system to stabilize (~30s)
sleep 30

# 3. Verify normal mode
curl -s http://127.0.0.1:7000/api/runtime | jq '.mode'
# Expected: "normal"

# 4. Trigger defensive mode (drop price to force RR ~280%)
make set-price PRICE=0.80
sleep 30

curl -s http://127.0.0.1:7000/api/runtime | jq '.mode'
# Expected: "defensive"

# 5. Trigger crisis mode (RR ~140%)
make set-price PRICE=0.40
sleep 30

curl -s http://127.0.0.1:7000/api/runtime | jq '.mode'
# Expected: "crisis"

# 6. Recovery - return to normal
make set-price PRICE=2.00
sleep 30

curl -s http://127.0.0.1:7000/api/runtime | jq '.mode'
# Expected: "normal"
```

### Expected Results

| Step | Price | Expected RR | Expected Mode |
|------|-------|-------------|---------------|
| 3 | $15.00 | ~700% | normal |
| 4 | $0.80 | ~280% | defensive |
| 5 | $0.40 | ~140% | crisis |
| 6 | $2.00 | ~500% | normal |

### Verification

- [ ] Mode transitions occur within 30s of price change
- [ ] Dashboard shows correct mode indicator
- [ ] Strategy restrictions apply in defensive/crisis modes

---

## DN02: Controlled Arbitrage Detection

**Purpose**: Test arbitrage detection with known spreads between oracle and orderbook.

### Steps

```bash
# 1. Set normal price with tight spread
make set-scenario SCENARIO=normal

# 2. Check orderbook spread
curl -s http://127.0.0.1:5556/status | jq '.spreadBps'
# Expected: 50 (0.5%)

# 3. Widen spread to create arbitrage opportunity
curl -X POST http://127.0.0.1:5556/set-spread \
  -H "Content-Type: application/json" \
  -d '{"spreadBps": 500}'

# 4. Check engine arb detection
curl -s http://127.0.0.1:7000/api/state | jq '.state.analysis.arbitrage'

# 5. Reset to normal spread
curl -X POST http://127.0.0.1:5556/set-spread \
  -H "Content-Type: application/json" \
  -d '{"spreadBps": 50}'
```

### Expected Results

- [ ] Engine detects potential arbitrage with 500 bps spread
- [ ] Arb opportunities show in dashboard
- [ ] No arb detected with tight 50 bps spread

---

## DN03: PegKeeper Activation

**Purpose**: Verify PegKeeper triggers when ZSD depegs from target.

### Preconditions

- DEVNET stack running
- Engine in normal mode
- ZSD liquidity pool deployed

### Steps

```bash
# 1. Set normal market conditions
make set-scenario SCENARIO=normal

# 2. Verify PegKeeper state
curl -s http://127.0.0.1:7000/api/state | jq '.state.strategies.pegKeeper'

# 3. Simulate ZSD depeg by adjusting pool
# (This requires manual intervention in pool state or UI)

# 4. Monitor PegKeeper response
watch -n 5 'curl -s http://127.0.0.1:7000/api/state | jq ".state.strategies.pegKeeper"'
```

### Expected Results

- [ ] PegKeeper detects depeg condition
- [ ] Appropriate rebalancing action triggered
- [ ] ZSD returns to peg tolerance

---

## DN04: LPManager Range Adjustment

**Purpose**: Verify LPManager rebalances when price moves out of concentrated liquidity range.

### Steps

```bash
# 1. Start with normal price
make set-price PRICE=15.00
sleep 30

# 2. Check LP position range
curl -s http://127.0.0.1:7000/api/state | jq '.state.strategies.lpManager.positions'

# 3. Move price significantly (out of range)
make set-price PRICE=25.00
sleep 60

# 4. Check if LPManager triggered rebalance
curl -s http://127.0.0.1:7000/api/state | jq '.state.strategies.lpManager'

# 5. Return to normal price
make set-price PRICE=15.00
```

### Expected Results

- [ ] LPManager detects out-of-range condition
- [ ] Rebalance decision logged
- [ ] New position range covers current price

---

## DN05: Crisis Mode Operations

**Purpose**: Verify only emergency operations are allowed in crisis mode.

### Steps

```bash
# 1. Trigger crisis mode
make set-price PRICE=0.40
sleep 30

# 2. Verify crisis mode
curl -s http://127.0.0.1:7000/api/runtime | jq '.mode'
# Expected: "crisis"

# 3. Check which operations are allowed
curl -s http://127.0.0.1:7000/api/runtime | jq '.allowedOperations'

# 4. Attempt a restricted operation via UI
# - Navigate to http://127.0.0.1:7000
# - Try to execute a swap or liquidity operation
# - Should be blocked with crisis mode warning

# 5. Exit crisis mode
make set-price PRICE=2.00
```

### Expected Results

- [ ] Crisis mode shows on dashboard
- [ ] Non-emergency operations are blocked
- [ ] Clear user messaging about restrictions
- [ ] Operations resume after crisis exits

---

## DN06: Fast Iteration Test

**Purpose**: Test system stability under rapid price changes.

### Steps

```bash
# Rapid price cycling script
for price in 15.00 10.00 5.00 2.00 1.00 0.80 0.60 0.40 0.60 0.80 1.00 2.00 5.00 10.00 15.00; do
    echo "Setting price to \$$price"
    make set-price PRICE=$price
    sleep 10
done

# Monitor engine state throughout
watch -n 2 'curl -s http://127.0.0.1:7000/api/runtime | jq "{mode, lastUpdate: .lastUpdatedAt}"'
```

### Expected Results

- [ ] No crashes or hangs during rapid changes
- [ ] Mode transitions are smooth
- [ ] State remains consistent
- [ ] No memory leaks (check after extended run)

---

## Scenario Presets

Quick presets available via `make set-scenario SCENARIO=<preset>`:

| Preset | Price | Spread | Use Case |
|--------|-------|--------|----------|
| `normal` | $15.00 | 50 bps | Standard testing |
| `high-spread` | $15.00 | 200 bps | Arb detection |
| `defensive` | $0.80 | 100 bps | Defensive mode |
| `crisis` | $0.40 | 300 bps | Crisis mode |
| `recovery` | $2.00 | 50 bps | Recovery testing |
| `high-rr` | $25.00 | 50 bps | High RR mode |
| `depeg` | $15.00 | 50 bps | Stablecoin depeg sim |
| `volatility` | $5.00 | 150 bps | High volatility |

---

## Testing Matrix

| Scenario | Mainnet Fork | DEVNET | Notes |
|----------|:------------:|:------:|-------|
| B11-B22 (Bridge Core) | ✓ | ✓ | Both work |
| B23-B27 (UI/Pools) | ✓ | ✓ | Both work |
| FS11-FS20 (Engine Core) | ✓ | ✓ | Both work |
| FS21-FS28 (Strategies) | ○ | ✓ | DEVNET required for RR testing |
| DN01-DN06 (New) | ✗ | ✓ | DEVNET only |

Legend: ✓ = Supported, ○ = Limited, ✗ = Not supported

---

## Troubleshooting

### Fake Oracle Not Responding

```bash
# Check if services are running
make status

# Check logs for a specific service
make logs SERVICE=fake-oracle

# Or check Docker Compose status directly
docker compose ps
```

### Engine Not Seeing Price Changes

1. Check fake orderbook is tracking oracle:
   ```bash
   curl -s http://127.0.0.1:5556/status | jq '.oraclePriceUsd'
   ```

2. Verify engine is using fake orderbook:
   ```bash
   grep FAKE_ORDERBOOK $ENGINE_REPO_PATH/.env
   ```

3. Restart engine watchers:
   ```bash
   overmind restart engine-watchers
   ```

### Mode Not Transitioning

- Reserve ratio calculation depends on total supply
- Fresh DEVNET has minimal supply, affecting RR calculation
- Mine blocks to increase supply: Mine some blocks first
- Check engine logs for RR calculation details

---

## Reset Commands Reference

| Command | Description |
|---------|-------------|
| `make dev-init` | Full init from block 0 (~5-6 min) |
| `make dev-reset` | Reset to checkpoint (~30 sec) |
| `make dev-checkpoint` | Save current height as new checkpoint |
| `./scripts/save-devnet.sh [name]` | Save named snapshot (default: "default") |
| `./scripts/restore-devnet.sh [name]` | Restore from named snapshot |

---

## Related Documentation

- [03-bridge-scenarios.md](./03-bridge-scenarios.md) - Core bridge tests
- [04-full-stack-scenarios.md](./04-full-stack-scenarios.md) - Full stack tests
- [services/fake-orderbook/README.md](../../services/fake-orderbook/README.md) - Fake orderbook details
- [../../README.md](../../README.md) - Quick reference for DEVNET commands

<!-- L5-CATALOG-START -->
## L5 Integrated Edge-Case Catalog

This section fully integrates the scoped ZB edge-case tests that belong in this runbook.

| Total | SCOPED-READY | SCOPED-EXPAND | SCOPED-TBC |
|---:|---:|---:|---:|
| 16 | 4 | 1 | 11 |

Tests marked `SCOPED-TBC` are intentionally included now and require additional runbook detail in a follow-up pass.

### 6. RR Mode Boundaries (8)

| ID | Test | Priority | Severity | Runbook Status | Integration Action |
|---|---|---|---|---|---|
| `ZB-RR-001` | Exact boundary at RR = 400% (mode switch correctness) | P0 | High | `SCOPED-EXPAND` | Expand nearby scenario with explicit edge assertions. |
| `ZB-RR-002` | RR just below 400% (399.99%) | P0 | High | `SCOPED-TBC` | Add detailed runbook steps (TBC). |
| `ZB-RR-003` | RR just above 800% (ZRS mint constraints) | P1 | Medium | `SCOPED-TBC` | Add detailed runbook steps (TBC). |
| `ZB-RR-004` | RR boundary at 200% and 199.99% | P0 | High | `SCOPED-READY` | Already covered in this doc; keep as regression. |
| `ZB-RR-005` | Mode flapping stress (rapid oscillation) | P0 | High | `SCOPED-READY` | Already covered in this doc; keep as regression. |
| `ZB-RR-006` | Mid-operation mode change during unwrap/wrap | P0 | Critical | `SCOPED-TBC` | Add detailed runbook steps (TBC). |
| `ZB-RR-007` | Engine runtime endpoint correctness for all op combinations | P0 | High | `SCOPED-READY` | Already covered in this doc; keep as regression. |
| `ZB-RR-008` | Stale reserve snapshot handling | P0 | High | `SCOPED-TBC` | Add detailed runbook steps (TBC). |

### 12. Load & Stress (8)

| ID | Test | Priority | Severity | Runbook Status | Integration Action |
|---|---|---|---|---|---|
| `ZB-LOAD-001` | Burst create 10k bridge addresses | P1 | Medium | `SCOPED-TBC` | Add detailed runbook steps (TBC). |
| `ZB-LOAD-002` | Burst 1k deposits in 5 minutes | P0 | High | `SCOPED-TBC` | Add detailed runbook steps (TBC). |
| `ZB-LOAD-003` | Burst 1k burns in 5 minutes | P0 | High | `SCOPED-TBC` | Add detailed runbook steps (TBC). |
| `ZB-LOAD-004` | Rapid oracle price changes (10/sec) | P1 | Medium | `SCOPED-READY` | Already covered in this doc; keep as regression. |
| `ZB-LOAD-005` | SSE fanout: 500 concurrent stream clients | P1 | Medium | `SCOPED-TBC` | Add detailed runbook steps (TBC). |
| `ZB-LOAD-006` | Uniswap swap storm (10k swaps) | P1 | Medium | `SCOPED-TBC` | Add detailed runbook steps (TBC). |
| `ZB-LOAD-007` | Postgres slow queries / high latency injection | P0 | High | `SCOPED-TBC` | Add detailed runbook steps (TBC). |
| `ZB-LOAD-008` | Wallet RPC slow/timeout injection | P0 | High | `SCOPED-TBC` | Add detailed runbook steps (TBC). |

<!-- L5-CATALOG-END -->
