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
| INV-11 | no payout before finality | LB-CONF-*, RES-REORG-UNWRAP | K |
| INV-12 | watcher exactly-once | RES-EXACTLY-ONCE | K |
| INV-13 | unwrap status truthfulness | LB-REC-STATUS, FLOW-UNWRAP-*, RES-STATUS-TRUTH, UI-UNWRAP-HAPPY | K |
| INV-14 | engine can't drain on bad price | LE-APPROVAL/RISK, MKT-STALE-PRICE, MKT-SLIPPAGE-FLOOR, MKT-RISK-DEFAULT-OFF | K |
| INV-15 | realized accounting | MKT-PNL-REALIZED, MKT-LOSS-BREAKER | K |
| INV-16 | no fund-burning loop | MKT-NO-PINGPONG | K |
| INV-17 | execution-time gating | LE-CONFORM-GATES, MKT-RRMODE-SWEEP, MKT-GATE-CONFORM-*, MKT-EXEC-TIME-GATE | K |
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
| id | asserts | grounds | St |
|---|---|---|---|
| LE-SWAP | estimateSwapOutput fee/1e6, slip/1e4, never-neg, zero-in→0 | code | G |
| LE-RR/-SPREAD/-FEE | determineRRMode; mint=MAX(spot,MA), redeem=MIN; fees 10/100/10 bps | code | G |
| LE-PRICE/-STEP | buildPricingFromState ($1 anchor, ZEPH chaining); buildExecutionSteps | code | G |
| LE-APPROVAL/-RISK | spread≥500bps blocks; RR gates; limits-disabled→allow; breaker FSM | code | G |
| LE-CONFORM-GATES | engine gate-availability fn vs protocol gate table at boundary RRs (199/201/399/401/799/801%) | zephyr-ref | K |
| LE-CONFORM-PRICING/-FEES | engine spread & fee model == protocol pricing/fees | zephyr-ref | G |

## SCENARIO — pytest · `tests/scenario/`
### FLOW (`flows/`) — money paths
| id | scenario | INV | St |
|---|---|---|---|
| FLOW-WRAP-{ZEPH,ZSD,ZRS,ZYS} | deposit→claim mints exact 1:1 | 1,6 | G |
| FLOW-UNWRAP-{×4} | burn→native payout lands; status flips to complete | 1,13 | G / K(status) |
| FLOW-ROUNDTRIP | wrap then unwrap reconciles; no value created/destroyed | 1,6 | G |
| FLOW-CLAIM-IDEM | claim twice → 2nd reverts | 2 | G |
| FLOW-CLAIM-EXPIRY | unclaimed 24h → expired, no re-sign → stuck | 7 | K |
| FLOW-ASSET-INTEGRITY | wrong/missing asset_type → correct token only (default-ZEPH wrong) | 5 | K |
| FLOW-PREPARE-CANCEL | prepare then cancel/never-burn → no payout | 3,4 | G |

### MKT (`market/`) — engine ↔ market dynamics (the heart)
| id | scenario | INV | St |
|---|---|---|---|
| MKT-RRMODE-SWEEP | price sweep ⇒ RR crosses 800/400/200; engine rrMode + /runtime track protocol gates | 17 | K |
| MKT-GATE-CONFORM-{ZSD,ZRS,ZYS} | RR<400% ⇒ daemon rejects MINT_STABLE; engine must not auto-plan it | 17 | K |
| MKT-ARB-DETECT-{prem,disc}×{4} | pool push ⇒ engine detects opp, correct sign+gapBps | 14 | G |
| MKT-ARB-EXECUTE | normal mode ⇒ full multi-step arb auto-executes; inventory returns | 14 | G |
| MKT-STALE-PRICE | pricing record stale (age>10 blk) ⇒ engine refuses to execute | 14 | K |
| MKT-SLIPPAGE-FLOOR | realized<expected ⇒ engine aborts (not amountOutMin ?? 0n) | 14 | K |
| MKT-PNL-REALIZED | recorded PnL = actual fill, not expectedPnl | 15 | K |
| MKT-LOSS-BREAKER | cumulative realized loss>max ⇒ breaker trips | 15 | K |
| MKT-NO-PINGPONG | no wrap/unwrap fee-burning loop on accounting-only CEX legs | 16 | K |
| MKT-EXEC-TIME-GATE | approve in normal, flip RR→crisis pre-exec ⇒ re-check aborts | 17 | K |
| MKT-PEG-DEFENSE | wZSD off $1 ⇒ peg-keeper proposes corrective mint/redeem within gates | 14 | G |
| MKT-RISK-DEFAULT-OFF | risk controls enabled:false default ⇒ $2000 op not blocked | 14 | K |

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
| RES-REORG-UNWRAP | burn at head; anvil snapshot+revert erases it ⇒ no payout (relay deferred) | 11 | K |
| RES-DOUBLE-PAYOUT | crash watcher mid-`sending`, restart ⇒ pays out exactly once | 4 | K |
| RES-EXACTLY-ONCE | WS reconnect/gap ⇒ every event once, none missed | 12 | K |
| RES-STATUS-TRUTH | payout lands ⇒ status pending→confirmed→complete (not stuck on stale wallet height) | 13 | K |
| RES-RECONCILE | reconcilePendingUnwraps sweeps stuck-sent → confirmed once mined | 13 | G |

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
