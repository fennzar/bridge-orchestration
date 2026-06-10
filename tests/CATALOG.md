# Bridge Test Catalog — the single source of truth

This replaces `docs/testing/00-edge-case-scope.md`. Every test the framework runs is listed here,
mapped to the invariant it pins (`docs/security/INVARIANTS.md`) and grounded in the code-verified
protocol SoT (`docs/protocol/zephyr-reference.md`).

**The framework is organized by what a *functional bridge* must guarantee, not by code unit.** Tests
are written as the *correct* behavior; where the system has a hole the test is **red today** and
tagged so the run renders the holes as a worklist.

## How to read this

- **Layer** — the runner that proves it:
  `CT` forge (`zephyr-eth-foundry/test/`) · `LB` node:test (`zephyr-bridge/packages/**`) ·
  `LE` vitest (`zephyr-bridge-engine/tests/**`) · scenario suites `FLOW/MKT/SEC/RES/OPS` pytest
  (`tests/scenario/`) · `UI` Playwright (`zephyr-bridge/tests/e2e/`).
- **St** (expected status, today): **G** green (invariant held here) · **K** KNOWN-GAP (red today,
  tagged `@known_gap`, on the worklist, non-fatal to the gate) · **A** ACCEPTED (owner-accepted
  deviation, amber). A red that is **not** K/A = a REGRESSION (fatal). A K that goes green =
  UNEXPECTED-PASS (fatal → promote the INVARIANTS.md row to HELD and drop the marker).
- **Gate:** the bridge is releasable when every INV-1..19 row is **G** (the engine ships enabled, so
  section-D INV-14..17 are launch-blocking — not optional). `make test-report` renders the ledger.

---

## INV → primary tests (the ledger spine)

| INV | property | pinned by | today |
|---|---|---|---|
| INV-1 | no unbacked mint | CT-SUP-INV, FLOW-WRAP-*, SEC-UNBACKED-MINT | K |
| INV-2 | no double-credit | CT-MINT-IDEM, LB-HASH-NORM, FLOW-CLAIM-IDEM | partial→G/K |
| INV-3 | no over-payout on unwrap | LB-AMT-COVERS, SEC-PREPARE-DRAIN | G (interim) |
| INV-4 | no double-payout | FLOW-PREPARE-CANCEL, RES-DOUBLE-PAYOUT | K |
| INV-5 | asset-type integrity | LB-PAY-*, LB-CFG-MAP, FLOW-ASSET-INTEGRITY, CT-BYPASS-BURN | K |
| INV-6 | decimal correctness | CT-DEC-FUZZ, LB-AMT-SCALE, FLOW-ROUNDTRIP | G |
| INV-7 | claim non-expiry trap | FLOW-CLAIM-EXPIRY | K |
| INV-8 | voucher unforgeable | CT-SIG-*, CT-ROT-SIGNER, SEC-CLAIM-FORGE | G |
| INV-9 | no signature replay | CT-SIG-XTOKEN/XCHAIN, SEC-CLAIM-REPLAY-XTOKEN | G |
| INV-10 | burn nonce non-replay | CT-BURN-NONCE | G |
| INV-11 | no payout before finality | LB-CONF-*, **RES-REORG-UNWRAP ✓** | K (relays at ~1-conf, live-proven) |
| INV-12 | watcher exactly-once | RES-EXACTLY-ONCE | K |
| INV-13 | unwrap status truthfulness | LB-REC-STATUS, **FLOW-UNWRAP ✓**, RES-STATUS-TRUTH, UI-UNWRAP-HAPPY | **G** (status flips pending→confirmed live; memory note stale) |
| INV-14 | engine can't drain on bad price | MKT-ARB-DETECT, MKT-APPROVAL-RRMODE, MKT-PEG-DEFENSE (G); MKT-STALE-PRICE (K); LE: SLIPPAGE-FLOOR, RISK-DEFAULT-OFF (K) | K |
| INV-15 | realized accounting | LE: PNL-REALIZED, LOSS-BREAKER (K) | K |
| INV-16 | no fund-burning loop | LE: NO-PINGPONG (K) | K |
| INV-17 | execution-time gating | MKT-RRMODE-SWEEP, MKT-GATE-CONFORM-ZSD/ZRS-redeem, MKT-NO-DOOMED-PLAN (G); MKT-GATE-CONFORM-ZRS-mint-floor (K); MKT-ARB-EXECUTE/EXEC-TIME-GATE (—); LE-CONFORM-GATES (K) | K |
| INV-18 | privileged routes need auth | SEC-DEBUG-RESET-OPEN, SEC-ENGINE-CTRL-UNAUTH, CT-PAUSE-ABSENT, UI-CONNECT | K / A |
| INV-19 | /unwraps/prepare not weaponizable | SEC-PREPARE-UNAUTH, SEC-PREPARE-BADADDR/OVERMAX | K |

---

## CONTRACT — forge (`CT-*`) · `zephyr-eth-foundry/test/`
| id | asserts | INV | St |
|---|---|---|---|
| CT-DEC-FUZZ | wei↔atomic 1:1, rounding favors bridge (fuzz) | 6 | G |
| CT-MINT-ROLE / -IDEM / -SHARED | role-gated mint; idempotent `usedZephyrTx`; operator+claim share replay namespace | 1,2 | G |
| CT-SIG-FORGE/-BOUND/-EXPIRED/-XTOKEN/-XCHAIN/-MALLEABLE | EIP-712 voucher unforgeable & fully bound | 8,9 | G |
| CT-BURN-NONCE / -ZERO | burn nonce non-replay; zero-amount burn | 10 | G / K |
| CT-ROT-SIGNER | signer rotation invalidates old sigs | 8 | G |
| CT-SUP-INV | invariant fuzz: `totalSupply == Σmint − Σburn`; no mint without consuming a txhash | 1 | G |
| CT-BYPASS-BURN | inherited `burn()`/`burnFrom()` destroy supply with NO `Burned` event/destination | 1,5 | K |
| CT-PAUSE-ABSENT | no pause/cap/multisig (single-hot-key) | 18 | A |

## LOGIC — bridge node:test (`LB-*`) · `zephyr-bridge/packages/**/*.test.ts`
| id | asserts | INV | St |
|---|---|---|---|
| LB-AMT-FEE/-SCALE/-COVERS | fee+net>0; decimal scale 6/8/12-dec; `burnCoversPayout` (fuzz burn<prepared⇒false) | 3,6 | G |
| LB-PAY-ROUNDTRIP/-LEGACY/-FP | encode/decode burn payload; legacy fallback; fingerprint determinism | 5 | G |
| LB-CONF-* | evmConfirmations/isBurnConfirmed/safeHeadBlock/nextUnwrapCursor (existing) | 11 | G |
| LB-REC-STATUS | hydrateUnwrapFromTransfer flips confirmed only when height>0 | 13 | G |
| LB-CFG-MAP | token↔asset map: 4 assets, no decimal mismatch | 5 | G |
| LB-HASH-NORM | txid 0x/bytes32 normalization | 2 | G |

## LOGIC — engine vitest (`LE-*`) · `zephyr-bridge-engine/tests/**/*.spec.ts`
Run: `cd $ENGINE_REPO_PATH && pnpm vitest run tests/conformance` (no stack). Known-gaps use
`it.fails` (passes while the gap stands; fails the day it's fixed → promote). Built files in **bold**.
| id | asserts | grounds | St | Built |
|---|---|---|---|---|
| LE-SWAP | estimateSwapOutput fee/1e6, slip/1e4, never-neg, zero-in→0 | code | G | — |
| LE-RR/-SPREAD/-FEE | determineRRMode; mint=MAX(spot,MA), redeem=MIN; fees 10/100/10 bps | code | G | — |
| LE-PRICE/-STEP | buildPricingFromState ($1 anchor, ZEPH chaining); buildExecutionSteps | code | G | — |
| **LE-CONFORM-GATES** | `mapReserveInfo().policy` vs protocol gate table (matching cells + 3 ZRS-mint divergences) | zephyr-ref | G+K | **conformance/gates.spec.ts** (6, verified) |
| **LE-LOSS-BREAKER** | CircuitBreaker FSM opens on cumulative loss / consecutive failures when enabled | code | G | **conformance/risk.spec.ts** (verified) |
| **LE-RISK-DEFAULT-OFF** | `DEFAULT_RISK_LIMITS.enabled=false` ⇒ $2000 op + $1M loss not halted | code | K | **conformance/risk.spec.ts** (it.fails, verified) |
| LE-SLIPPAGE-FLOOR / LE-PNL-REALIZED / LE-NO-PINGPONG | swap `amountOutMin ?? 0n`; expected-vs-realized PnL; offsetting wrap/unwrap loop | code | K | — (reassigned from MKT) |
| LE-CONFORM-PRICING/-FEES | engine spread & fee model == protocol pricing/fees | zephyr-ref | G | — |

## SCENARIO — pytest · `tests/scenario/`
### FLOW (`flows/`) — money paths
| id | scenario | INV | St |
|---|---|---|---|
| FLOW-WRAP-{ZEPH,ZSD,ZRS,ZYS} | deposit→claim mints exact 1:1 | 1,6 | G |
| FLOW-UNWRAP ✓ | burn wZEPH→native payout relays; status flips pending→confirmed (~15s) | 1,13 | **G** (built, live-verified) |
| FLOW-ROUNDTRIP | wrap then unwrap reconciles; no value created/destroyed | 1,6 | G |
| FLOW-CLAIM-IDEM | claim twice → 2nd reverts | 2 | G |
| FLOW-CLAIM-EXPIRY | unclaimed 24h → expired, no re-sign → stuck | 7 | K |
| FLOW-ASSET-INTEGRITY | wrong/missing asset_type → correct token only (default-ZEPH wrong) | 5 | K |
| FLOW-PREPARE-CANCEL | prepare then cancel/never-burn → no payout | 3,4 | G |

### MKT (`market/`) — engine ↔ market dynamics (the heart)
St: G green · K known-gap red · — not yet built. "Built" = file:test present and collecting.
Method: drive oracle (`control.settle_price`) / push a pool (`pool.move_price` under `anvil_snapshot`);
observe via `/api/runtime` `enabled`, `/api/arbitrage/analysis|plans`, `/api/engine/evaluate`; assert
against the protocol gate oracle (`market/protocol_gates.py`, cited to zephyr-reference.md).

| id | scenario | INV | St | Built |
|---|---|---|---|---|
| MKT-RRMODE-SWEEP | oracle sweep $1.50→0.35 ⇒ measured RR drops; engine rrMode + reported RR track the daemon at every regime | 17 | G | `test_rrmode_sweep.py` |
| MKT-GATE-CONFORM-ZSD-mint | ZEPH→ZSD `enabled` == protocol MINT_STABLE(rr,ma) — matches | 17 | G | `test_gate_conformance.py` |
| MKT-GATE-CONFORM-ZRS-mint-floor | <400%: protocol allows ZEPH→ZRS (no floor), engine blocks (rr<4) — divergence | 17 | K | `test_gate_conformance.py` |
| MKT-GATE-CONFORM-ZRS-redeem / ZSD-redeem | ZRS→ZEPH / ZSD→ZEPH `enabled` == protocol gate — matches at baseline | 17 | G | `test_gate_conformance.py` |
| MKT-NO-DOOMED-PLAN | no auto-exec plan closes via a native hop the protocol blocks at measured RR (doomed tx) | 17 | G | `test_doomed_plans.py` |
| MKT-ARB-DETECT-ZSD-{prem,disc} | wZSD/USDT push ⇒ analysis reports correctly-signed gapBps + direction | 14 | G | `test_arb_dynamics.py` |
| MKT-APPROVAL-RRMODE | defensive RR ⇒ no ZRS plan auto-executable (`shouldAutoExecuteForRRMode`) | 14 | G | `test_arb_dynamics.py` |
| MKT-PEG-DEFENSE | wZSD off $1 ⇒ peg-keeper proposes a corrective op (not into the drop) | 14 | G | `test_peg_defense.py` |
| MKT-STALE-PRICE | engine exposes NO native price-freshness signal ⇒ can't refuse a stale oracle (absence assertion) | 14 | K | `test_price_safety.py` |
| MKT-ARB-EXECUTE | normal mode ⇒ full multi-step arb auto-executes; inventory returns | 14 | — | needs runner harness (queue/runner API) |
| MKT-EXEC-TIME-GATE | approve in normal, flip RR→crisis pre-exec ⇒ re-check aborts | 17 | — | needs runner harness; temporal gate |

**Reassigned to LE (deterministic vitest) — in-memory in the runner process, not observable via the
stateless read APIs; tested as pure conformance reds instead (task #14):**
| id | scenario | INV | St | Where |
|---|---|---|---|---|
| MKT-RISK-DEFAULT-OFF | `DEFAULT_RISK_LIMITS.enabled === false` ⇒ breaker `canExecute()` always allows | 14 | K | LE: `risk/limits.ts`, `circuitBreaker.ts` |
| MKT-LOSS-BREAKER | cumulative realized loss > max ⇒ breaker opens (FSM) | 15 | K | LE: `circuitBreaker.ts` |
| MKT-PNL-REALIZED | execution records expected score (`netUsdChangeUsd`), no realized-fill reconciliation | 15 | K | LE: execution/view |
| MKT-SLIPPAGE-FLOOR | swap uses `amountOutMin ?? 0n` (no slippage floor) ⇒ no abort on adverse fill | 14 | K | LE: execution swap step |
| MKT-NO-PINGPONG | offsetting wrap/unwrap loop burns real fees on accounting-only CEX legs | 16 | K | LE: routing / dedupe |

### SEC (`security/`) — adversarial
| id | scenario | INV | St |
|---|---|---|---|
| SEC-PREPARE-DRAIN | prepare large + burn dust ⇒ burnCoversPayout blocks relay (CRIT-1) | 3 | G |
| SEC-PREPARE-UNAUTH | /unwraps/prepare open+unauth ⇒ griefing/DoS | 19 | K |
| SEC-PREPARE-BADADDR/-OVERMAX | invalid dest rejected; >UNWRAP_MAX rejected | 19 | G |
| SEC-CLAIM-FORGE / -REPLAY-XTOKEN | attacker sig reverts; wZEPH voucher on wZSD reverts | 8,9 | G |
| SEC-UNBACKED-MINT | mint with no verified deposit blocked | 1 | G |
| SEC-DEBUG-RESET-OPEN | destructive GET /debug/reset/database reachable behind NEXT_PUBLIC flag | 18 | K |
| SEC-ENGINE-CTRL-UNAUTH | /api/engine/queue,/runner unauthenticated | 18 | K |

### RES (`resilience/`) — finality / consistency / watchers
| id | scenario | INV | St |
|---|---|---|---|
| RES-REORG-UNWRAP ✓ | burn relayed while only ~1-conf deep (ingest never checks isBurnConfirmed) | 11 | **K** (built, live-proven) |
| RES-DOUBLE-PAYOUT | re-relay of a prepared payout — same pre-signed txid ⇒ daemon-idempotent | 4 | likely **G** (deterministic txid; not yet built) |
| RES-EXACTLY-ONCE | WS reconnect/gap ⇒ every event once, none missed | 12 | K (needs watcher-crash orchestration) |
| RES-STATUS-TRUTH | payout lands ⇒ status pending→confirmed (folded into FLOW-UNWRAP ✓) | 13 | **G** (covered, live-verified) |
| RES-RECONCILE | reconcilePendingUnwraps sweeps stuck-sent → confirmed once mined | 13 | G (not yet built) |

### OPS (`ops/`) — stack / protocol sanity gates (run first)
`OPS-CHAIN-HEALTH`, `OPS-WALLET-BALANCES`, `OPS-CONTRACTS-DEPLOYED`, `OPS-ORACLE-CONTROL`,
`OPS-RR-COMPUTE`, `OPS-ASSET-V1V2-GUARD` (ZEPH→ZRS = invalid tx). All **G**.

## BROWSER — Playwright (`UI-*`) · `zephyr-bridge/tests/e2e/`
| id | scenario | INV | St |
|---|---|---|---|
| UI-CONNECT | MetaMask connects; wrong-network banner + switch works | 18 | G / K(clamp) |
| UI-WRAP-HAPPY / UI-UNWRAP-HAPPY | full wrap/unwrap via UI; unwrap reaches "Complete" | 13 | G / K |
| UI-SWAP-HAPPY | swap executes via UI | — | G |
| UI-LP-ADD | add-liquidity via UI (Permit2 two-step) | — | G |
| UI-FAUCET | faucet ZSD/ZRS dispenses | — | G / K(502) |
