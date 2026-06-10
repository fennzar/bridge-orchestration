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
| INV-1 | no unbacked mint | CT-SUP ✓, CT-MINT-ROLE ✓, FLOW-WRAP-* ✓, SEC-UNBACKED-MINT — but **CT-BYPASS-BURN ✓ (K)** drags the roll-up | K |
| INV-2 | no double-credit | CT-MINT-IDEM ✓, LB-HASH-NORM ✓, FLOW-CLAIM-IDEM ✓ | G |
| INV-3 | no over-payout on unwrap | LB-AMT-COVERS ✓, FLOW-PREPARE-CANCEL ✓, SEC-PREPARE-DRAIN | G (interim) |
| INV-4 | no double-payout | (crash-idempotency only — **uncovered**, see RES note → task #8) | — |
| INV-5 | asset-type integrity | CT-BYPASS-BURN ✓, CT-BURN-ZERO ✓, FLOW-WRAP-{ZSD,ZRS,ZYS} ✓ | K |
| INV-6 | decimal correctness | CT-DEC ✓, LB-AMT-SCALE ✓, FLOW-ROUNDTRIP ✓ | G |
| INV-7 | claim non-expiry trap | FLOW-CLAIM-EXPIRY ✓ | K |
| INV-8 | voucher unforgeable | CT-SIG-*, CT-ROT-SIGNER, SEC-CLAIM-FORGE | G |
| INV-9 | no signature replay | CT-SIG-XTOKEN/XCHAIN, SEC-CLAIM-REPLAY-XTOKEN | G |
| INV-10 | burn nonce non-replay | CT-BURN-NONCE | G |
| INV-11 | no payout before finality | LB-CONF-*, **RES-REORG-UNWRAP ✓** | K (relays at ~1-conf, live-proven) |
| INV-12 | watcher exactly-once | (WS-reconnect gap-fill only — **uncovered**, see RES note → task #8/#18) | — |
| INV-13 | unwrap status truthfulness | LB-REC-STATUS, **FLOW-UNWRAP ✓**, RES-STATUS-TRUTH, UI-UNWRAP-HAPPY | **G** (status flips pending→confirmed live; memory note stale) |
| INV-14 | engine can't drain on bad price | MKT-ARB-DETECT, MKT-APPROVAL-RRMODE, MKT-PEG-DEFENSE (G); MKT-STALE-PRICE (K); LE-RISK-DEFAULT-OFF (K), LE-LOSS-BREAKER per-op (G); SLIPPAGE-FLOOR (—) | K |
| INV-15 | realized accounting | LE-LOSS-BREAKER ✓ (G when enabled + off-by-default K); PNL-REALIZED (—) | K |
| INV-16 | no fund-burning loop | (NO-PINGPONG not built — **uncovered**, needs CEX-accounting grounding) | — |
| INV-17 | execution-time gating | MKT-RRMODE-SWEEP, MKT-GATE-CONFORM-ZSD/ZRS-redeem, MKT-NO-DOOMED-PLAN (G); MKT-GATE-CONFORM-ZRS-mint-floor (K); MKT-ARB-EXECUTE/EXEC-TIME-GATE (—); LE-CONFORM-GATES (K) | K |
| INV-18 | privileged routes need auth | SEC-DEBUG-RESET-OPEN, SEC-ENGINE-CTRL-UNAUTH, CT-PAUSE-ABSENT, UI-CONNECT | K / A |
| INV-19 | /unwraps/prepare not weaponizable | SEC-PREPARE-UNAUTH (A — unauth by design, theft-bound by burnCoversPayout), SEC-PREPARE-BADADDR/ZERO/MISSING ✓ (G), -OVERMAX (skipped, no cap set) | A |

---

## CONTRACT — forge (`CT-*`) · `zephyr-eth-foundry/test/ZephyrWrappedToken.t.sol`
The 24 tests self-declare their INV in NatSpec (`/// INV-N`); `invariant-report.py` reads that to roll
them into the ledger (no fn renames). ✓ = present + ledger-mapped. The CT-* ids below are conceptual
groupings; the live test fn names appear in the ledger pins.
| id | asserts | INV | St |
|---|---|---|---|
| CT-MINT-ROLE / -IDEM / -SHARED ✓ | role-gated mint (ByNonMinter); idempotent `usedZephyrTx` (Replay); operator+claim share replay namespace (AfterMintFromZephyr_SameTx) | 1,2 | G |
| CT-SIG-FORGE/-BOUND/-EXPIRED/-XTOKEN/-XCHAIN/-MALLEABLE ✓ | EIP-712 voucher unforgeable & fully bound | 8,9 | G |
| CT-BURN-NONCE ✓ / -ZERO ✓ | burn nonce non-replay (NonceReplay, INV-10 G); zero-amount burn (KNOWNGAP, pinned INV-5 K) | 10,5 | G / K |
| CT-DEC ✓ | `decimals()==12` (1:1 with Zephyr atomic) — Decimals_Is12 | 6 | G |
| CT-ROT-SIGNER ✓ | signer rotation invalidates old sigs + admin-gated | 8 | G |
| CT-SUP ✓ | `totalSupply == Σmint − Σburn` across both mint paths — Supply_TracksMintMinusBurn (unit, not fuzz) | 1 | G |
| CT-BYPASS-BURN ✓ | inherited `burn()` destroys supply with NO `Burned` event/destination (KNOWNGAP) | 1,5 | K |
| CT-PAUSE-ABSENT | no pause/cap/multisig (single-hot-key) — not yet pinned by a test | 18 | A |
| ~~CT-DEC-FUZZ / CT-SUP-INV~~ | fuzz/stateful-invariant variants — **not built**: the unit CT-DEC + CT-SUP already pin INV-6/1; a stateful invariant would only re-express the CT-BYPASS-BURN gap. Future hardening. | 1,6 | — |

## LOGIC — bridge node:test (`LB-*`) · `zephyr-bridge/packages/bridge/src/unwraps/*.test.ts`
node 22 strips types; run via `pnpm test`. Titles carry `[INV-NN]` + an `LB-*` id; default-on in
`invariant-report.py` (run_node, TAP parse). ✓ = present + ledger-mapped.
| id | asserts | INV | St |
|---|---|---|---|
| LB-AMT-COVERS/-DRAIN/-FEE ✓ | `burnCoversPayout` (legit allowed; dust<prepared BLOCKED = CRIT-1; fee headroom; non-positive rejected) | 3 | G |
| LB-AMT-SCALE ✓ | `weiToAtomic` 12-dec 1:1; 18-dec scales down 1e6 | 6 | G |
| LB-CONF-DEPTH/-GATE/-HEAD/-CURSOR/-REORG ✓ | evmConfirmations/isBurnConfirmed/safeHeadBlock/nextUnwrapCursor (10 tests) — the unwired reorg-safe primitives | 11 | G |
| LB-REC-STATUS ✓ | `hydrateUnwrapFromTransfer` status=confirmed only when height>0 (truthful decision; live gap is the stale source) | 13 | G |
| LB-HASH-NORM ✓ | txid → 0x-lowercase hash + plain id (claim/burn replay-key linking) | 2 | G |
| ~~LB-PAY-* / LB-CFG-MAP~~ | payload encode/decode round-trip; token↔asset map — **not built**: INV-5 is already pinned K by CT-BYPASS-BURN/-ZERO; payload/cfg are happy-path encoders, low marginal coverage. Future. | 5 | — |

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
| FLOW-WRAP-ZEPH ✓ | deposit ZEPH→claim mints exact 1:1 | 1,6 | G |
| FLOW-WRAP-{ZSD,ZRS,ZYS} ✓ | parametrized deposit→claim; asserts claim.token == the matching wZ* (asset routing) | 1,5,6 | G |
| FLOW-UNWRAP ✓ | burn wZEPH→native payout relays; status flips pending→confirmed (~15s) | 1,13 | **G** (built, live-verified) |
| FLOW-CLAIM-IDEM ✓ | claim twice → 2nd reverts | 2 | G |
| FLOW-ROUNDTRIP ✓ | wrap then unwrap same amount → wZEPH balance returns to baseline, no net mint | 1,6 | G |
| FLOW-PREPARE-CANCEL ✓ | prepare then never burn → no payout relayed (assert-by-absence) | 3,4 | G |
| FLOW-CLAIM-EXPIRY ✓ | no voucher re-sign endpoint exists → an expired deposit is stuck (route probe) | 7 | K |
| FLOW-ASSET-INTEGRITY ✓ | folded into FLOW-WRAP-{ZSD,ZRS,ZYS}: a V2 deposit credits ONLY its matching token. The degenerate missing-`asset_type`→ZEPH default (watcher index.ts:190) is a watcher-unit gap, not pinnable via a real deposit (daemon always sets asset_type) | 5 | G |

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
| MKT-RISK-DEFAULT-OFF | `DEFAULT_RISK_LIMITS.enabled === false` ⇒ breaker `canExecute()` always allows | 14 | K | LE: `risk.spec.ts` (`[INV-14] [gap]`) |
| MKT-LOSS-BREAKER | breaker FSM trips on cumulative loss / consecutive failures **when enabled** (green); off-by-default (gap) | 15 | G+K | LE: `risk.spec.ts` (`[INV-15]` green + `[gap]`) |

**Not yet built — distinct sub-properties whose INV row is already lit by a sibling, OR genuinely
uncovered. Listed honestly so the catalog never claims coverage the ledger doesn't show:**
| id | scenario | INV | St | Why not built |
|---|---|---|---|---|
| MKT-PNL-REALIZED | recorded score is `expectedPnl` (`netUsdChangeUsd`), never reconciled to the realized fill | 15 | — | needs executed-trade + realized-fill accounting grounding. INV-15 already RED-GAP via the breaker default-off, so the ledger already flags the row. |
| MKT-SLIPPAGE-FLOOR | swap uses `amountOutMin ?? 0n` (no slippage floor) ⇒ no abort on adverse fill | 14 | — | needs an executed swap with a moved pool to observe the realized-vs-min gap. INV-14 already RED-GAP via price-freshness + risk-default-off. |
| MKT-NO-PINGPONG | offsetting wrap/unwrap loop burns real fees on accounting-only CEX legs | 16 | — | a faithful test must model the CEX accounting-only price diverging from the real fee-bearing legs — needs engine-internal grounding. A flat-market proxy would duplicate `mkt_peg_quiet_when_on_peg` and **falsely green** INV-16. **INV-16 stays honestly UNCOVERED in the ledger** until grounded (sibling of #8/#18). |

(MKT-ARB-EXECUTE and MKT-EXEC-TIME-GATE also not built — see the live-scenario table above; both need the runner approve→execute harness. INV-17 is already RED-GAP via gate-conformance + rrmode, INV-14 via price-freshness.)

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
| RES-STATUS-TRUTH | payout lands ⇒ status pending→confirmed — folded into FLOW-UNWRAP ✓ (live) + LB-REC-STATUS ✓ (unit) | 13 | **G** (covered) |
| ~~RES-DOUBLE-PAYOUT / RES-EXACTLY-ONCE / RES-RECONCILE~~ | crash-mid-`sending` re-relay (INV-4); WS-reconnect gap-fill (INV-12); reconcile sweep (INV-13) — **not built**: all need watcher process-kill / WS-fault orchestration. Deferred to **task #8** (watcher reorg-safety + crash idempotency) + **#18** (needs the crash harness decision). INV-4/12 remain UNCOVERED in the ledger by design. | 4,12,13 | — |

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
