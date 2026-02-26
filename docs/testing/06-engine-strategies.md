# Engine Strategy Testing

Test all 4 engine strategies via the evaluate endpoint. Requires DEVNET mode with controllable oracle prices.

> **Edge-case scope:** Strategy-adjacent edge tests (RR boundaries, stale data, runtime allow/deny drift) are cataloged in [00-edge-case-scope.md](./00-edge-case-scope.md).
>
> **Runner:** Use `make test-l5` (or `./scripts/run-l5-tests.py`) for L5 planning/lint.
>
> **TBC note:** Any scenario marked `SCOPED-TBC` in the scope catalog still needs command-level runbook guidance before execution.

**Endpoint:** `GET http://localhost:7000/api/engine/evaluate?strategies=<ids>`

**Strategy IDs:** `arb`, `peg`, `lp`, `rebalancer`, or `all`

---

## Prerequisites

- DEVNET running (`make dev-init` or `make dev-reset`)
- Engine web running on port 7000 (via overmind or manually)
- Engine `.env` must have DEVNET settings:
  ```
  ZEPHYR_D_RPC_URL=http://127.0.0.1:47767   # NOT 48081 (mainnet-fork)
  FAKE_ORDERBOOK_ENABLED=true
  FAKE_ORDERBOOK_PORT=5556
  ```
- If engine shows "Failed to build state" / "fetch failed", check `ZEPHYR_D_RPC_URL` port

---

## Quick Smoke Test

```bash
# All 4 strategies in one call
curl -s 'http://localhost:7000/api/engine/evaluate?strategies=all' | python3 -c "
import sys, json
d = json.load(sys.stdin)
s = d['state']
print(f'State: RR={s[\"reserveRatio\"]:.1f}%, price=\${s[\"zephPrice\"]}, mode={s[\"rrMode\"]}')
for sid, strat in d['results'].items():
    opps = strat.get('opportunities', [])
    warns = strat.get('warnings', [])
    print(f'  {sid}: {len(opps)} opportunities, {len(warns)} warnings')
print(f'Errors: {d.get(\"errors\", \"none\")}')
"
```

**Expected:** 4 result keys (`arb`, `peg`, `lp`, `rebalancer`), no errors.

---

## Test 1: Arbitrage Strategy (`arb`)

Detects EVM/CEX price discrepancies vs Zephyr native reference prices.

```bash
curl -s 'http://localhost:7000/api/engine/evaluate?strategies=arb' | python3 -c "
import sys, json
d = json.load(sys.stdin)
arb = d['results']['arb']
print(f'Opportunities: {len(arb[\"opportunities\"])}')
for o in arb['opportunities']:
    print(f'  [{o[\"urgency\"]}] {o[\"asset\"]} {o[\"direction\"]}: {o[\"trigger\"]}')
    print(f'    Expected PnL: \${o[\"expectedPnl\"]:.2f}')
m = arb['metrics']
print(f'Legs checked: {m[\"totalLegsChecked\"]}, found: {m[\"opportunitiesFound\"]}')
print(f'Gaps (bps): ZSD={m.get(\"ZSD_gapBps\",\"?\")}, ZEPH={m.get(\"ZEPH_gapBps\",\"?\")}, ZRS={m.get(\"ZRS_gapBps\",\"?\")}, ZYS={m.get(\"ZYS_gapBps\",\"?\")}')
"
```

### Pass Criteria

- [x] Returns structured `opportunities` array with `id`, `strategy`, `trigger`, `asset`, `direction`, `expectedPnl`, `urgency`
- [x] Metrics include `totalLegsChecked`, `opportunitiesFound`, gap per asset
- [x] Detects EVM discount/premium vs native reference prices
- [x] Urgency levels assigned correctly (high for large gaps)

---

## Test 2: Peg Keeper Strategy (`peg`)

Monitors WZSD/USDT pool price and detects deviations from $1.00 peg.

```bash
curl -s 'http://localhost:7000/api/engine/evaluate?strategies=peg' | python3 -c "
import sys, json
d = json.load(sys.stdin)
peg = d['results']['peg']
m = peg['metrics']
print(f'ZSD price: \${m[\"zsdPriceUsd\"]:.6f}')
print(f'Deviation: {m[\"deviationBps\"]}bps')
print(f'Threshold (normal): 30bps')
print(f'Opportunities: {len(peg[\"opportunities\"])}')
for w in peg.get('warnings', []):
    print(f'  warn: {w}')
"
```

### Threshold Behavior by RR Mode

| Mode | Min Deviation | Urgent | Critical |
|------|--------------|--------|----------|
| Normal | 30bps (0.3%) | 100bps (1%) | 300bps (3%) |
| Defensive | 100bps (1%) | 200bps (2%) | 500bps (5%) |
| Crisis | 300bps (3%) | 500bps (5%) | 1000bps (10%) |

### Pass Criteria

- [x] Reports `zsdPriceUsd` and `deviationBps` in metrics
- [x] At current peg (~$1.00, <30bps deviation): returns 0 opportunities
- [x] Warnings adjust based on RR mode (defensive: "widened peg tolerance", crisis: "only buying ZSD at significant discount")
- [ ] If ZSD depegs >30bps: detects opportunity with direction `zsd_premium` or `zsd_discount` (requires pool price manipulation — not yet automated)

**Note:** Peg keeper reads the EVM pool price, not the oracle. To trigger a detection, you'd need to execute a large swap on the WZSD/USDT pool to move its price. Oracle price changes alone don't affect the pool price.

---

## Test 3: LP Manager Strategy (`lp`)

Monitors Uniswap V4 LP positions for range status and fee collection.

```bash
curl -s 'http://localhost:7000/api/engine/evaluate?strategies=lp' | python3 -c "
import sys, json
d = json.load(sys.stdin)
lp = d['results']['lp']
m = lp['metrics']
print(f'Positions: {m[\"totalPositions\"]} (in-range: {m[\"inRangePositions\"]})')
print(f'Total value: \${m[\"totalValueUsd\"]:.2f}')
print(f'Uncollected fees: \${m[\"totalFeesUsd\"]:.2f}')
print(f'Opportunities: {len(lp[\"opportunities\"])}')
for w in lp.get('warnings', []):
    print(f'  warn: {w}')
"
```

### Pass Criteria

- [x] Returns metrics: `totalPositions`, `inRangePositions`, `totalValueUsd`, `totalFeesUsd`
- [x] With 0 positions: returns 0 opportunities (expected on fresh DEVNET)
- [x] RR-aware warnings ("Consider adjusting LP ranges for defensive/crisis mode")
- [ ] With active positions: detects out-of-range, fee collection opportunities, and range adjustment needs (requires LP positions to be created first)

**Note:** LP strategy queries the database for tracked positions. On a fresh DEVNET with no LP activity, it correctly returns 0 positions.

---

## Test 4: Rebalancer Strategy (`rebalancer`)

Detects inventory allocation drift across venues (EVM, native, CEX).

```bash
curl -s 'http://localhost:7000/api/engine/evaluate?strategies=rebalancer' | python3 -c "
import sys, json
d = json.load(sys.stdin)
reb = d['results']['rebalancer']
m = reb['metrics']
print(f'Opportunities: {len(reb[\"opportunities\"])}')
for o in reb['opportunities']:
    ctx = o['context']
    print(f'  {o[\"asset\"]}: {ctx[\"fromVenue\"]} -> {ctx[\"toVenue\"]} ({ctx[\"deviationPct\"]:.0f}% deviation, \${ctx[\"amount\"]:.0f})')
print(f'\\nDistribution:')
for asset in ['ZEPH', 'ZSD', 'ZRS', 'ZYS', 'USDT']:
    evm = m.get(f'{asset}_evmPct', 0)
    native = m.get(f'{asset}_nativePct', 0)
    cex = m.get(f'{asset}_cexPct', 0)
    if evm or native or cex:
        print(f'  {asset}: EVM={evm:.0f}% Native={native:.0f}% CEX={cex:.0f}%')
"
```

### Target Allocations

| Asset | EVM | Native | CEX |
|-------|-----|--------|-----|
| ZEPH | 30% | 50% | 20% |
| ZSD | 60% | 30% | 10% |
| ZRS | 40% | 60% | 0% |
| ZYS | 50% | 50% | 0% |
| USDT | 70% | 0% | 30% |

### Pass Criteria

- [x] Reports per-asset allocation percentages in metrics
- [x] Detects deviation from target allocations (threshold: 10%)
- [x] Generates rebalance opportunities with `fromVenue`, `toVenue`, `amount`, `deviationPct`
- [x] On fresh DEVNET (100% EVM): detects over-allocation for all assets
- [x] Urgency: high for >40% deviation, medium for >25%

---

## Test 5: RR Mode Transitions

Test all strategies across normal, defensive, and crisis reserve ratio modes.

```bash
ZEPHYR_CLI="$ROOT/zephyr/tools/zephyr-cli/cli"

for SCENARIO in normal defensive crisis; do
  case $SCENARIO in
    normal)    PRICE="1.50" ;;
    defensive) PRICE="0.50" ;;
    crisis)    PRICE="0.25" ;;
  esac

  # Set oracle price and mine blocks to propagate
  make set-price PRICE=$PRICE > /dev/null 2>&1
  $ZEPHYR_CLI mine start > /dev/null 2>&1; sleep 6
  $ZEPHYR_CLI mine stop > /dev/null 2>&1; sleep 2

  echo "=== $SCENARIO (oracle=\$$PRICE) ==="
  curl -s "http://localhost:7000/api/engine/evaluate?strategies=all" | python3 -c "
import sys, json
d = json.load(sys.stdin)
s = d['state']
print(f'  RR: {s[\"reserveRatio\"]:.1f}%  Mode: {s[\"rrMode\"]}  Price: \${s[\"zephPrice\"]}')
for sid, strat in d['results'].items():
    opps = strat.get('opportunities', [])
    warns = strat.get('warnings', [])
    print(f'  {sid:12s}: {len(opps)} opps, {len(warns)} warns')
"
  echo ""
done

# Restore
make set-price PRICE=1.50 > /dev/null 2>&1
$ZEPHYR_CLI mine start > /dev/null 2>&1; sleep 8
$ZEPHYR_CLI mine stop > /dev/null 2>&1
echo "Restored to \$1.50"
```

### Expected Results

| Scenario | Price | RR | Mode | Arb | Peg | LP | Rebalancer |
|----------|-------|----|------|-----|-----|----|------------|
| Normal | $1.50 | ~650% | normal | 3 opps (gaps exist) | 0 opps | 0 opps (no positions) | 5 opps (100% EVM) |
| Defensive | $0.50 | ~217% | defensive | 2 opps + RR warning | 0 opps + tolerance warning | 0 opps + range warning | 5 opps |
| Crisis | $0.25 | ~108% | crisis | 2 opps + crisis warning | 0 opps + crisis warning | 0 opps + range warning | 5 opps |

### Pass Criteria

- [x] RR mode transitions correctly: normal (>400%), defensive (200-400%), crisis (<200%)
- [x] Arb strategy adds RR-specific warnings
- [x] Peg keeper adjusts thresholds per mode
- [x] LP manager flags range adjustment for non-normal modes
- [x] All strategies handle mode transitions without errors

---

## Test 6: Error Handling

```bash
# Unknown strategy
curl -s 'http://localhost:7000/api/engine/evaluate?strategies=bogus' | python3 -c "
import sys, json; d = json.load(sys.stdin)
print(f'Results: {list(d[\"results\"].keys())}')
print(f'Errors: {d.get(\"errors\", \"none\")}')
"

# Mixed valid + invalid
curl -s 'http://localhost:7000/api/engine/evaluate?strategies=arb,bogus,peg' | python3 -c "
import sys, json; d = json.load(sys.stdin)
print(f'Results: {list(d[\"results\"].keys())}')
print(f'Errors: {d.get(\"errors\", \"none\")}')
"

# Default (no param) - should default to arb
curl -s 'http://localhost:7000/api/engine/evaluate' | python3 -c "
import sys, json; d = json.load(sys.stdin)
print(f'Results: {list(d[\"results\"].keys())}')
"
```

### Pass Criteria

- [x] Unknown strategy: returns error in `errors` array, no crash
- [x] Mixed valid+invalid: valid strategies still evaluate, invalid ones listed in errors
- [x] Default (no param): defaults to `arb` strategy
- [x] `all` keyword: evaluates all 4 strategies

---

## Test Results (2026-02-19, DEVNET)

| Test | Status | Notes |
|------|--------|-------|
| 1. Arb Strategy | PASS | 3 opportunities (ZEPH discount, ZRS/ZYS premiums), all metrics populated |
| 2. Peg Keeper | PASS | ZSD at $0.9999 (-1bps), correctly no opportunity. RR-aware warnings work |
| 3. LP Manager | PASS | 0 positions (expected, fresh DEVNET). Metrics and warnings correct |
| 4. Rebalancer | PASS | 5 opportunities (all assets 100% EVM). Deviation detection correct |
| 5. RR Mode Transitions | PASS | normal→defensive→crisis all trigger correct behavior |
| 6. Error Handling | PASS | Unknown strategies, mixed queries, defaults all handled |

### DEVNET `.env` Fix Required

The engine `.env` (generated by `sync-env.sh`) uses mainnet-fork port `48081` for `ZEPHYR_D_RPC_URL`. For DEVNET testing, manually update to `47767` and add `FAKE_ORDERBOOK_ENABLED=true`.

### What's Not Yet Testable

- **Peg keeper opportunity detection**: Requires manipulating the WZSD/USDT pool price via on-chain swap (oracle price changes don't affect pool price)
- **LP manager with positions**: Requires LP positions to exist in the database (need to add liquidity via the PositionManager contract first)
- **Execution engine paper mode with new strategies**: Paper execution for peg/rebalancer/LP steps needs the full engine run mode, not just evaluate

---

## L5 Strategy-Adjacent Edge Cases

These ZB tests are integrated here as strategy-adjacent checks. Some are fully runnable now; others are marked TBC pending deeper runbook detail.

| ID | Test | Priority | Severity | Runbook Status | Notes |
|---|---|---|---|---|---|
| `ZB-CONC-010` | Engine evaluation concurrent with reserve mode change | P0 | High | `SCOPED-TBC` | Add looped evaluate + rapid price toggle harness. |
| `ZB-CONS-010` | Engine DB snapshots align with current on-chain pool state | P0 | High | `SCOPED-EXPAND` | Extend state/evm checks with tighter drift assertions. |
| `ZB-RR-007` | Engine runtime endpoint correctness for all op combinations | P0 | High | `SCOPED-READY` | Covered by runtime/mode checks; keep as regression. |
| `ZB-RR-008` | Stale reserve snapshot handling | P0 | High | `SCOPED-TBC` | Add daemon pause + staleness expectation assertions. |
| `ZB-TIME-008` | Engine staleness guard (market data age) | P0 | High | `SCOPED-TBC` | Add MEXC feed stop/invalidate and evaluate assertions. |
| `ZB-CONF-010` | Wrong RR thresholds configured in engine | P0 | High | `SCOPED-EXPAND` | Add config override checks and expected mode matrix. |

<!-- L5-CATALOG-START -->
## L5 Seeding Verification

Automated checks in `scripts/l5_checks/seed.py` — verify the seeding pipeline populated engine wallets correctly.

| ID | Test | Priority | Status | Notes |
|---|---|---|---|---|
| `ZB-SEED-001` | Engine Zephyr wallet is funded with all asset types | P0 | `SCOPED-READY` | Automated check. |
| `ZB-SEED-002` | Bridge API recognises the engine EVM address | P0 | `SCOPED-READY` | Automated check. |
| `ZB-SEED-003` | At least 4 completed claims exist for engine | P0 | `SCOPED-READY` | Automated check. |
| `ZB-SEED-004` | Engine holds non-zero wrapped token balances | P0 | `SCOPED-READY` | Automated check. |
| `ZB-SEED-005` | Engine holds non-zero USDC and USDT balances | P0 | `SCOPED-READY` | Automated check. |
| `ZB-SEED-006` | All 5 pools have non-zero liquidity | P0 | `SCOPED-READY` | Automated check. |
| `ZB-SEED-007` | All pools have non-zero sqrtPriceX96 | P0 | `SCOPED-READY` | Automated check. |
| `ZB-SEED-008` | Seed is idempotent — no excessive duplicates | P0 | `SCOPED-READY` | Automated check. |

## L5 Engine Arbitrage Edge Cases

Automated checks in `scripts/l5_checks/engine_arb.py` — 4 stages: Detection (6) | Planning (4) | Execution (6) | Guardrails (6).

| ID | Test | Priority | Status | Notes |
|---|---|---|---|---|
| `ZB-ARB-001` | ZEPH evm_premium detection via pool swap | P0 | `SCOPED-READY` | Automated: sells wZEPH to push price up, checks engine API. |
| `ZB-ARB-002` | ZEPH evm_discount detection via pool swap | P0 | `SCOPED-READY` | Automated: sells wZSD to push price down, checks engine API. |
| `ZB-ARB-003` | ZSD evm_premium detection via wZSD-USDT pool | P1 | `SCOPED-TBC` | Push wZSD above $1 peg. |
| `ZB-ARB-004` | ZSD evm_discount detection via wZSD-USDT pool | P1 | `SCOPED-TBC` | Push wZSD below $1 peg. |
| `ZB-ARB-005` | Aligned baseline — no false triggers | P0 | `SCOPED-READY` | Automated: no manipulation, verify all assets aligned. |
| `ZB-ARB-006` | Price restore realigns engine state | P0 | `SCOPED-READY` | Automated: push price, restore, verify aligned. |
| `ZB-ARB-007` | ZEPH premium plan — swapEVM open leg | P0 | `SCOPED-READY` | Automated: push premium, verify plan has swapEVM open leg. |
| `ZB-ARB-008` | ZEPH discount plan — swapEVM open leg | P0 | `SCOPED-READY` | Automated: push discount, verify plan has swapEVM open leg. |
| `ZB-ARB-009` | Plan includes expectedPnl > minProfitUsd | P1 | `SCOPED-TBC` | Verify plan expectedPnl exceeds $1 threshold. |
| `ZB-ARB-010` | Plan respects clip size limits | P1 | `SCOPED-TBC` | Verify clip <= 10% pool depth and <= inventory. |
| `ZB-ARB-011` | ZEPH premium executed in paper mode | P0 | `SCOPED-READY` | Automated: push premium, engine auto-executes, verify history. |
| `ZB-ARB-012` | ZEPH discount executed in paper mode | P0 | `SCOPED-READY` | Automated: push discount, engine auto-executes, verify history. |
| `ZB-ARB-013` | Execution history has step results | P1 | `SCOPED-TBC` | Verify stepResults array matches plan steps. |
| `ZB-ARB-014` | Execution records PnL and duration | P1 | `SCOPED-TBC` | Verify netPnlUsd > 0 and durationMs > 0. |
| `ZB-ARB-015` | ZSD premium executed in paper mode | P1 | `SCOPED-TBC` | Push ZSD premium, verify execution in history. |
| `ZB-ARB-016` | ZSD discount executed in paper mode | P1 | `SCOPED-TBC` | Push ZSD discount, verify execution in history. |
| `ZB-ARB-017` | Crisis mode blocks auto-execution | P0 | `SCOPED-TBC` | RR<200%, push premium, engine detects but does not execute. |
| `ZB-ARB-018` | Defensive mode blocks ZRS arb | P1 | `SCOPED-TBC` | 200%<RR<400%, push ZRS gap, verify blocked. |
| `ZB-ARB-019` | Defensive mode ZEPH profit gate | P1 | `SCOPED-TBC` | Defensive mode requires >=$20 ZEPH profit for auto-execute. |
| `ZB-ARB-020` | High spread blocks auto-execute | P1 | `SCOPED-TBC` | >5% spot/MA spread blocks non-stable auto-execute. |
| `ZB-ARB-021` | Manual mode queues instead of executing | P1 | `SCOPED-TBC` | --manual flag queues to operationQueue. |
| `ZB-ARB-022` | Inventory snapshot matches seeded state | P0 | `SCOPED-TBC` | /api/inventory/balances matches expected seeded state. |
<!-- L5-CATALOG-END -->
