# Bridge Hardening & Release-Readiness Plan

**Status:** DRAFT for sign-off · **Date:** 2026-06-10
**Sign-off:** ☐ owner   ☐ peer review   ☐ (then `/orchestrate`)

> Scoring uses **stars (0.5★–5★)** for effort/complexity, never time. This plan is the executable
> path from today's state ("not releasable, one confirmed drain + HIGH cluster") to "every
> money-critical invariant `HELD`, engine decision made." It operationalizes the security docs:
> [STATE](../security/STATE-OF-THE-BRIDGE.md) · [THREAT-MODEL](../security/THREAT-MODEL.md) ·
> [INVARIANTS](../security/INVARIANTS.md) · [FINDINGS](../security/FINDINGS.md).

**Guiding rule:** for every fix, write the *negative* (attack) test **first**, watch it pass-the-attack
(or fail) on current code, then fix until the attack is blocked, then promote the invariant to `HELD`.
No fix is "done" until its invariant test is green in CI.

---

## Phase 0 — Decisions to make before coding (0.5★) — **owner input needed**

These change the scope of everything else. (Use `/ask` to resolve.)

1. **Is testnet-v2 carrying real value, or is it a fake-market demo?** If demo-only, custody risk is
   contained and the engine criticals (HIGH-5/6/7) are deferrable.
2. **Ship with the engine ENABLED or DISABLED?** Strong recommendation: **disabled for first launch.**
   The engine's worst issues are live-trading issues, not custody issues; disabling it removes
   INV-14..17 from the launch gate entirely.
3. **Contract posture for the single-hot-key risk:** add Pausable + mint cap + multisig admin (a
   contract change + redeploy), or write an explicit risk-acceptance + compromise runbook for v1?

---

## Phase 1 — Close the custody criticals (5★) — **blocks launch**

Each item: the fix + the invariant test that proves it. Order = by expected loss.

### 1.1 — CRIT-1 unwrap over-payout (INV-3) — *interim done, finish it*
- ✅ **Done:** fail-safe amount-binding guard in `packages/bridge/src/unwraps/ingest.ts`
  (`burnedAtomic ≥ preparedPayoutAtomic`, else throw). Typecheck clean.
- ☐ **Test:** `burn < prepared ⇒ relay throws, no native send, draft rolls back`; `burn == prepared ⇒
  relays once`. (vitest in `packages/bridge`, mock `relayZephyrTransfer`.)
- ☐ **Real fix (architectural):** stop pre-signing at prepare time from client input. Instead: on
  `Burned`, *size the payout from `evt.amount`*, then prepare+sign+relay. Make `/unwraps/prepare`
  either authenticated (EVM signature binding `from`) or a pure quote (no wallet-input commitment).
- ☐ **Harden prepare:** validate `destination` is a real Zephyr address (`validateZephyrAddress`)
  before any wallet interaction; rate-limit; reject `amountWei` exceeding a configured per-tx cap.

### 1.2 — HIGH-2 reorg-safe payout (INV-11) — 2★
- ☐ Gate `ingestEvmBurn` relay on `headBlock − burnBlock ≥ getEvmConfirmationTarget()` (the function
  already exists, just unused). Config the depth per chain (Anvil=0/1, Sepolia/mainnet=N).
- ☐ **Test:** burn at head ⇒ no relay until depth reached; reorg before depth ⇒ never relays.

### 1.3 — HIGH-8 double-relay idempotency (INV-4) — 2★
- ☐ Persist a durable `broadcastAttempted` marker **before** `relayZephyrTransfer`; on restart,
  reconcile via **daemon** `get_transactions`/txid lookup (not stale wallet) before any re-relay.
- ☐ **Test:** simulate crash between broadcast and persist; restart ⇒ exactly one payout.

### 1.4 — INV-13 unwrap confirm via daemon — 1.5★
- ☐ `hydrateUnwrapFromTransfer` / confirm path must read finality from the **daemon**, not wallet
  `get_transfer_by_txid` height. (Also fixes the "stuck pending → never complete" UX bug.)
- ☐ **Test:** mined payout ⇒ status reaches `confirmed` ⇒ UI maps to `complete`.

### 1.5 — INV-5 asset-type integrity — 1★
- ☐ `transformTransfer` must **reject** a deposit with missing/unknown `asset_type` (no `"ZEPH"`
  default). ☐ **Test:** ZSD deposit never produces a wZEPH credit; unknown asset ⇒ rejected.

---

## Phase 2 — Close the auth + web + crypto-test gaps (4★) — **blocks launch**

### 2.1 — HIGH-1 authorize privileged routes (INV-18) — 1.5★
- ☐ `requireAdmin` on all `/debug/*` and on engine `/api/engine/{queue,runner}`; remove GET
  `/reset/database`; never gate destructive ops on `NEXT_PUBLIC_*`. Confirm dev flags OFF on the
  testnet host. ☐ **Test:** each privileged route 401s without token.

### 2.2 — HIGH-3 web decodes burn payload (Boundary A) — 1★
- ☐ In `unwrap-client.tsx`, `decodeBurnPayload(payload)` before burn; hard-block if
  `decoded.destination !== userInput` or fingerprint mismatch. ☐ **Test (web/unit):** mismatched
  payload ⇒ burn blocked.

### 2.3 — HIGH-4 web pins approval spenders (Boundary A) — 1★
- ☐ Cross-check `/uniswap/config` router/permit2/positionManager against `@zephyr-bridge/config`
  pinned addresses; refuse on mismatch; prefer exact-amount approvals over `MaxUint256`.
- ☐ Add a shared **wrong-network guard** to wrap/unwrap/swap/lp (reuse `switchOrAddChain`); simulate
  approvals before send (MED-5).

### 2.4 — Contract test suite from zero (INV-8/9/10) — 2★
`zephyr-eth-foundry/test/` has **no `ZephyrWrappedToken` tests.** Write forge tests for:
- ☐ claim: valid mint; wrong signer rejected; expired deadline rejected; malleable sig rejected;
  replay (`usedZephyrTx`) rejected; **cross-token** voucher rejected; **cross-chain** (changed
  chainid) rejected; `to=0`/amount=0 behavior.
- ☐ burn: nonce replay rejected; event contents; `amount=0`/empty payload behavior; plain
  `burn()`/`burnFrom()` policy (disable or accept-with-doc).
- ☐ invariant/fuzz: `totalSupply == Σ minted(unconsumed) − burned`; `decimals()==12`.
- ☐ Re-enable the foundry CI triggers (`.github/workflows/test.yml`).

---

## Phase 3 — Key ops & contract posture (3★) — **decision-gated (Phase 0.3)**

- ☐ **Signer/minter compromise runbook** (the missing doc): how to rotate `setOracleSigner`, revoke
  `MINTER_ROLE`, pause (if added), and reconcile in-flight claims/unwraps. Put it in
  `docs/security/key-ops-runbook.md`.
- ☐ If chosen: add `Pausable` + per-epoch **mint cap** to `ZephyrWrappedToken`; move admin to a
  multisig; redeploy + migrate addresses. Tests for pause-blocks-mint, cap-enforced.
- ☐ Move engine `CEX_PK`/`CEX_ADDRESS` out of Procfile command strings (visible in `ps`/logs) into
  env files (MED-9).

---

## Phase 4 — Engine hardening (4★) — **only if engine ships enabled (Phase 0.2)**

- ☐ HIGH-5: refuse to start live with `RISK_CONTROLS_ENABLED!=true`; arm limits in real-value config.
- ☐ HIGH-6: compute+enforce real `amountOutMin` on every swap/burn (quote − tolerance).
- ☐ HIGH-7 / MED-1: thread **realized** venue outputs into PnL + the loss tracker; fix the
  string-bigint deserialization in the manual-approval path.
- ☐ MED-7/8: re-check rrMode + prices at **execution** time; price conversions with the mint/redeem
  spread + protocol fees, not bare spot.
- ☐ INV-16: cap or detect the wrap/unwrap fee-burning loop (cumulative-notional guard, not just the
  60s cooldown).
- ☐ Engine tests: rewrite from the engine invariants (drain-resistance, realized accounting,
  execution-time gating) — not API-shape assertions.

---

## Phase 5 — First-principles test rewrite (4★) — *spans all repos*

The current ~720 tests are mostly happy-path API-shape checks; ~55% of the edge catalog isn't
automated; the contract has zero tests. **Rewrite from invariants down**, organized by the
INVARIANTS.md ledger, not by file structure.

| Layer | Runner | New invariant tests (examples) |
|---|---|---|
| Contracts | forge | INV-3/8/9/10 (above), fuzz INV-1/6 |
| bridge pkg | vitest | INV-3 (amount binding), INV-4 (crash idempotency), INV-5 (asset integrity), INV-2 (concurrent claim+rescan race) |
| watchers | vitest + harness | INV-11 (confirmation depth), INV-12 (WS-reconnect gap-fill), INV-13 (daemon confirm) |
| api | vitest/supertest | INV-18 (route auth), INV-19 (prepare can't be weaponized) |
| engine | vitest | INV-14/15/16/17 |
| full-stack | the L1–L5 make targets, rebuilt | end-to-end wrap/unwrap with the attack scenarios from THREAT-MODEL §4 |

Deliverable: every INVARIANTS.md row reaches `HELD`, wired into CI.

---

## Phase 6 — Stress test bridge-web + testnet-v2 deployment (3★)

> **Runnable procedure:** [`../security/stress-test-runbook.md`](../security/stress-test-runbook.md)
> operationalizes this phase (Legs A–D, each mapped to an invariant + the make target / check that
> runs it). The adversarial API leg (ZB-SEC-013..017) is already wired into `make test-edge-sec`.

Grounded, not vibes (use `chrome-debug` for the browser legs):
- ☐ **Functional E2E on a live stack:** wrap, claim, unwrap (incl. the CRIT-1 attack: prepare-large +
  burn-dust ⇒ must be blocked), swap, LP add/remove — verified in real Chrome, not just typecheck.
- ☐ **Adversarial web:** wrong-network attempts; malformed/oversized Zephyr destination; double-claim;
  stale SSE; API-returns-garbage (point web at a mock returning a hostile payload/spender — HIGH-3/4
  must block).
- ☐ **Load/DoS:** spam `/unwraps/prepare` (input contention), many concurrent SSE subscribers
  (Postgres connection exhaustion, MED), rapid claim/burn.
- ☐ **Deployment dry-run:** fresh `make dev-init → dev-setup → dev`; verify dev flags OFF, CORS not
  `*`, no debug routes reachable, secrets not in `ps`/logs; reorg-sim on the EVM side if feasible.
- ☐ Capture results in `reports/` and update the INVARIANTS ledger.

---

## Release gate (copy of STATE §6, the definition of "confident enough")

Ship for real value only when: **all of INVARIANTS §A/B/C/E are `HELD`**, the engine is disabled
*or* §D is `HELD`, the key-compromise runbook exists, and CI runs the invariant suite green on push.

---

## Execution notes
- Branch per phase via `wt` (worktrunk); the CRIT-1 guard is currently **uncommitted on `master`** in
  `zephyr-bridge` — review + move it to a branch before committing (master = no auto-commit).
- Phases 1+2 are the true launch blockers and are parallelizable (`/orchestrate` once signed off).
- Re-verify every ⚠️ finding against code before changing a money path — the sub-audits are AI too.
