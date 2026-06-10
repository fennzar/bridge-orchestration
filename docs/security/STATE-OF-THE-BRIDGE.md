---
title: State of the Bridge — Release-Readiness Assessment
status: AUTHORITATIVE (security)
author: security review, commissioned by repo owner
date: 2026-06-10
verification_legend:
  "✅": verified against ground-truth code in this session (file:line cited)
  "⚠️": relayed from a sub-audit, plausible but NOT independently re-verified
  "❓": open question, needs a human or a running-stack test to settle
supersedes: any earlier doc claiming the bridge is release-ready
---

# State of the Bridge — Release-Readiness Assessment

> **One-line verdict:** The bridge is **NOT safe to release for real value today.** There is at
> least one **confirmed, unauthenticated, single-transaction hot-wallet drain** (CRIT-1, fixed in
> this branch but not yet stack-verified) plus a cluster of HIGH issues that each individually
> block a money-bearing launch. The *wrap/claim* path and the *EVM token contract crypto* are
> genuinely sound. The danger is concentrated in the **unwrap payout path** and the **engine's
> disabled-by-default risk controls**.

This document is the trustworthy replacement for any prior "implementation coverage" / "ready for
testnet" claim. Existing docs were largely written by lower-tier models; **this one cites code.**

---

## 0. How to read this

The owner's stated fear — "we are 90% there, I just need confidence" — is **the wrong mental
model.** 90%-done is not how bridge security works: a single unbacked-mint or unbounded-payout path
makes the *other 99% irrelevant*, because an attacker only needs one. The correct model is a
**gate list**: a set of named invariants, each of which must be provably held before any real
value flows. This doc gives you that gate list and tells you, per gate, whether it currently holds.

See companion docs:
- [`THREAT-MODEL.md`](./THREAT-MODEL.md) — who can attack what, and the trust boundaries.
- [`INVARIANTS.md`](./INVARIANTS.md) — the money-critical invariant ledger + test coverage.
- [`FINDINGS.md`](./FINDINGS.md) — the full severity-ranked register with fixes.
- [`../plans/bridge-hardening.md`](../plans/bridge-hardening.md) — the remediation + test + stress roadmap.

---

## 1. What is actually SOUND (don't waste hardening effort here)

These were verified and are good. Confidence-builders — lead with these.

| Area | Why it's sound | Evidence |
|---|---|---|
| **EVM token contract crypto** | EIP-712 domain includes `chainId` + `verifyingContract` (per-token, per-chain replay isolation); OZ 5.4 ECDSA rejects malleable/high-s sigs; `usedZephyrTx` mapping blocks claim replay; deadline enforced in both claim paths. | ✅ `zephyr-eth-foundry/src/ZephyrWrappedToken.sol:57,113-118,164-170` |
| **Wrap/claim amount integrity** | The minted amount is derived from the **chain-verified deposit** (`tx.amountAtomic`), not from any client- or DB-writable field. Re-signing is blocked once a signature exists. | ✅ `zephyr-bridge/packages/bridge/src/claims/ingest.ts:108-112`; signer guards in `claims/signer.ts` |
| **Decimals** | Both sides are **12 decimals** (wrapped token `decimals()==12` mirrors Zephyr atomic units). Conversion is 1:1, no silent scaling. The `amountWei` field name is a misnomer but the math is correct. | ✅ `ZephyrWrappedToken.sol:66-68`; `packages/bridge/src/unwraps/amount.ts:54-65` |
| **Secrets hygiene** | `SECRETS.MD` and deploy keys are gitignored and **never committed** (verified via full-history pickaxe). | ✅ `git log --all -- SECRETS.MD` empty; `.gitignore:31` |
| **Burn nonce replay** | `usedNonce[msg.sender][nonce]` blocks per-account burn-event replay on-chain. | ✅ `ZephyrWrappedToken.sol:131-138` |

---

## 2. The CRITICAL: unauthenticated unwrap hot-wallet drain (CRIT-1)

**This is the finding that matters most. Two independent sub-audits converged on it; I then
verified it end-to-end across all three layers myself.**

### The mechanism (✅ verified at every layer)

1. **`POST /unwraps/prepare` is unauthenticated** and takes a client-supplied `amountWei` +
   `destination`. It immediately asks the bridge wallet to **pre-sign a real Zephyr payout** for
   that amount to that address (`do_not_relay:true`) and returns a `payload`.
   ✅ `zephyr-bridge/apps/api/src/routes/unwraps.ts:74-132`
2. **The burn payload carries no amount.** It encodes only `{version, txHash, walletFingerprint,
   destination}`.
   ✅ `zephyr-bridge/packages/bridge/src/unwraps/payload.ts:14-20`
3. **`burnWithData(amount, zephDestination, nonce)` treats the payload as opaque bytes** — it burns
   the caller's `amount` and emits an event, with **zero binding between burned amount and payload.**
   ✅ `zephyr-eth-foundry/src/ZephyrWrappedToken.sol:129-138`
4. **The watcher relays the pre-signed metadata for the *prepare-time* amount**, guarded only by a
   tx-hash equality check — it reads the actual burned amount (`burnWei`) but **never compares it**
   to the prepared payout.
   ✅ `zephyr-bridge/packages/bridge/src/unwraps/ingest.ts:368-407` (pre-fix)

### The exploit (no auth, two transactions, no special access)

```
1. attacker → POST /unwraps/prepare { token: wZEPH, amountWei: <entire bridge balance>,
                                       destination: <attacker's own Zephyr address> }
              ← bridge signs a full-balance payout, returns `payload`
2. attacker → burnWithData(1, payload, nonce)      // burns 1 atomic unit they already own
3. watcher  → relays the full-balance pre-signed payout to the attacker
   RESULT: attacker spent 1 atomic wZEPH, received the entire bridge hot wallet in ZEPH.
```

Repeatable per prepare, bounded only by the hot-wallet balance. The hot-wallet balance is also
**publicly readable** (`GET /status/zephyr-wallet/balances`, unauthenticated) so the attacker knows
exactly how much to drain. ✅ `apps/api/src/routes/status.ts` (status route, balances endpoint)

### Status: FIXED IN BRANCH (fail-safe interim guard), NOT YET STACK-VERIFIED

I added an amount-binding guard in the relay path: it relays **only if the on-chain burned amount
(in atomic units) covers the prepared payout**, else it throws → the unwrap is marked failed and
the draft rolls back. Fail-safe: a bug in the guard can only *block* a payout (recoverable
liveness), never *authorize* an over-payout.
- Patch: `zephyr-bridge/packages/bridge/src/unwraps/ingest.ts` (search `SECURITY (critical) — bind the relayed payout`).
- Typecheck: ✅ `pnpm --filter @zephyr-bridge/bridge typecheck` clean.
- ❓ **Still needs:** an automated invariant test (`burn < prepared ⇒ no payout`) + a live-stack run.
- **The interim guard is not the real fix.** The architecturally-correct fix is to **size and sign
  the payout from the observed burn**, after the burn reaches sufficient confirmation depth — and
  to authenticate / rate-limit `/unwraps/prepare`. See PLAN § Phase 1.

---

## 3. The HIGH cluster — each one blocks a money-bearing launch

| ID | Where | What | Verified |
|---|---|---|---|
| **HIGH-1** | api: `routes/debug/index.ts:8-85` | Destructive `/debug/reset/database` (incl. a **GET** variant, CSRF/prefetch-triggerable) and `/debug/bridge-accounts/backup` (dumps the entire EVM↔Zephyr-deposit map → deanonymizes every user) are gated **only** by `NEXT_PUBLIC_ENABLE_DEV_CONTROLS`/`ENABLE_DEV_RESET` — a build-time/client-facing flag, **no admin token**. | ✅ |
| **HIGH-2** | watcher-evm: `apps/watcher-evm/src/index.ts`; `confirmations.ts:31` | Burn→payout relays at **0 EVM confirmations** (chain head). `getEvmConfirmationTarget()` (=20) exists but is **never used** in the burn path. On Sepolia/mainnet a reorg that drops the burn after payout = irreversible ZEPH loss. Hidden in dev because Anvil never reorgs. | ⚠️ |
| **HIGH-3** | web: `app/unwrap/unwrap-client.tsx:300-326`; `use-contract.ts:184` | The burn `destination` arg is the **API-returned `payload` blob, never decoded client-side** to confirm it encodes the address the user typed. What the user *sees* and what they *sign* are independently sourced → a compromised API redirects the payout with no client tripwire. `decodeBurnPayload` already exists; it's just not called. | ⚠️ |
| **HIGH-4** | web: swap `swap-client.tsx`; LP `use-token-approval.ts:139-166` | Swap/LP grant **unlimited approvals** (`MaxUint256` / `MAX_UINT160`) to `router`/`permit2`/`positionManager` addresses **fetched at runtime from `/uniswap/config` with no pinning** against `@zephyr-bridge/config`. Compromised config → user signs unlimited approval to attacker contract. (Pinning helpers already exist.) | ⚠️ |
| **HIGH-5** | engine: `src/domain/risk/limits.ts:26`; `circuitBreaker.ts:59-61` | **All risk controls are `enabled: false` by default** ("DISABLED by default for testnet v2"). Circuit breaker `canExecute()` always allows; threshold checks no-op. Only `RISK_CONTROLS_ENABLED=true` arms them — and it is **not set** in the dev/prod Procfiles. | ✅ |
| **HIGH-6** | engine: `execution.dispatch.ts:108`; `pegkeeper.ts`/`rebalancer.ts` | Peg-keeper and rebalancer EVM swaps dispatch with `amountOutMin: step.expectedAmountOut ?? 0n` — and **neither strategy ever sets `expectedAmountOut`** → effective **slippage minimum of 0** → trivially sandwichable; LP burns pass `amount0Min/amount1Min: 0`. | ✅ (peg/rebalance set nothing: grep empty) |
| **HIGH-7** | engine: `engine.helpers.ts:25-27`; `engine.execution.ts:114` | Recorded PnL is the **expected** PnL, never the realized PnL. The loss tracker is fed forecasts, so `maxDailyLossUsd` can never trip on real losses **even if risk controls were enabled.** The engine cannot detect it is losing money. | ⚠️ |
| **HIGH-8** | watcher-evm: `ingest.ts:393-426`; admin `unwraps.ts` (`/retry`,`/resend`); `recovery.ts` `decideResend` | **Double-relay window** (FIXED): recovery is now anchored on the pre-signed payout (fixed inputs → stable hash → mines at most once), so re-relay (`/retry`, ingest reconcile) is **idempotent**. The one fresh-input path (`/resend`) is structurally gated — it fresh-sends only with **no pre-signed commit in any persisted source** (row hashes, linked prepared/outgoing draft, structured `burnPayload`) and no lineage; else heals or refuses fail-closed (409/503). INV-4 → HELD; reviewed to convergence. | ✅ |

**Engine framing (important):** the engine's CRIT/HIGH items are **"devnet-fine, live-dangerous."**
They do not threaten the bridge's custody directly on devnet/testnet-v2 with fake markets, but they
make the engine **unfit to run against real markets with real inventory.** If testnet-v2 is purely a
demo with no real value and the engine is the trading layer, you can ship the bridge with the engine
**disabled** and revisit HIGH-5..8 before enabling live trading. That decoupling is the single
biggest scope-reducer available to you.

---

## 4. The two thin areas you named, assessed

### 4a. "Security of the bridge-web itself"

**Assessment: structurally sound, but it under-defends.** No XSS sinks, no secrets in the client
bundle, no server-only key imports, no app-side signing routes (it's a pure client). The problem is
that **its entire security rests on trusting bridge-api**, and it skips two *cheap, client-side*
verifications it could trivially do:
- decode the burn payload and assert the destination matches what the user typed (HIGH-3);
- pin swap/LP spender addresses against the bundled config before approving (HIGH-4).

There is also **no wrong-network guard on the signing pages** (only `/testnet` checks chain id) and
**swap/LP approvals are not simulated** before sending (MED). So the web app is not *exploitable on
its own*, but it converts "API compromised" or "user on wrong chain" into direct fund loss with no
tripwire. These are all fixable with small, local, additive changes — see FINDINGS.

### 4b. "Engine ↔ Zephyr network & market dynamics"

**Assessment: the skeleton is thoughtful, the execution layer is full of stubs and optimistic
assumptions.** The engine *reads* the reserve ratio / `rrMode` and gates plans on it, which is the
hard conceptual part and it's done. But:
- **RR is checked at plan *evaluation*, not at *execution*** — a manually-approved plan can execute
  minutes/hours later against flipped conversion availability with no re-check. ⚠️
- The distinctive Zephyr mint/redeem **spot-vs-moving-average spread** is computed but used only in
  the *report-only* planner; the **executing** path prices conversions at spot → systematically
  **overstates arb edge** in volatile periods. ⚠️
- **No settlement waits in real modes**: unwrap returns before the Zephyr payout lands; conversions
  don't wait for the ~10-block unlock; the next step fires against funds that don't exist yet. Works
  only because devnet mines instantly. ⚠️
- The **CEX layer is accounting-only** (`marketOrder` moves nothing, returns a fake price) while the
  real legs of the same plan move **real** funds and pay **real** fees → a fee-burning ping-pong.
  **Now gated (INV-16, 2026-06-11):** `checkAccountingOnlyCexLoop` in `shouldAutoExecute` refuses any
  auto-exec plan that pairs a real fund-moving leg with a `tradeCEX` leg while the CEX is
  accounting-only (devnet, and live + `MEXC_PAPER`) — the 60s cooldown is no longer the only brake. ✅
- **Stale Zephyr oracle never blocks** — freshness is checked for EVM/CEX but `STALE_THRESHOLDS.zephyr`
  is defined and never used. A frozen oracle yields confident stale prices for every decision. ⚠️

The honest summary: **the engine is a sophisticated devnet demo, not a production market maker.**
The Zephyr-specific economics (RR gating, mint/redeem spread, unlock latency, conversion fees) are
*modeled* in the planning/reporting layer but **not enforced in the executing layer.**

---

## 5. Doc-vs-code drift worth knowing (trust calibration)

The owner is right not to trust the existing docs. Concrete examples found:
- `zephyr-bridge-engine/docs/execution-and-risk.md` presents the CircuitBreaker/RiskLimits as the
  risk system **without stating both are disabled-by-default and inert**, and describes "each step
  threads its actual output to the next" — but the live loop **bypasses** `ExecutionEngine.executePlan`
  entirely (dead code) and no venue returns a real `amountOut`. ⚠️
- Any doc implying the unwrap payout amount is "verified from the burn" is **false** (CRIT-1). ✅
- `zephyr-eth-foundry/script/02_Mint.s.sol` comment says "1e18 for wZ*" — **wrong**, tokens are
  12-decimal. ✅
- `NOTES.md` / `addresses.example.json` still reference `chainId 31337` — orchestration moved to
  `271337/271338`. ✅
- The per-repo README files are, by contrast, **accurate** and are the best existing references.

---

## 6. Release gate — the explicit checklist

Do **not** flow real value until every CRIT and HIGH below is closed *and covered by an automated
invariant test* (see INVARIANTS.md). This is the answer to "how do I get confident enough to ship."

- [ ] **CRIT-1** unwrap amount-binding — interim guard verified by test + live stack; real fix
      (sign-from-burn + authenticate `/unwraps/prepare`) landed.
- [ ] **HIGH-1** debug/admin routes behind a real auth token; destructive ops POST-only; no
      `NEXT_PUBLIC_*` gating of destructive ops.
- [ ] **HIGH-2** burn→payout waits for `getEvmConfirmationTarget()` confirmations (reorg safety).
- [ ] **HIGH-3** web decodes burn payload and blocks on destination mismatch.
- [ ] **HIGH-4** web pins swap/LP spenders against config; prefers exact-amount approvals.
- [x] **HIGH-8** burn→payout idempotency proven against crash-after-broadcast (no double-relay) — pre-signed-tx anchor + structurally-gated fresh-input `/resend`; pinned by `LB-RESEND` + live `RES-RESEND-*`/`RES-REINGEST`. INV-4 HELD.
- [ ] Contract: a **pause / mint-cap / multisig-admin** story for the single-hot-key risk (or an
      explicit, written acceptance that the keys are single points of failure).
- [ ] Engine: either **disabled for launch**, or HIGH-5/6/7 closed (risk controls armed, real
      slippage minimums, realized-PnL accounting).
- [ ] A **signer-key compromise runbook** exists (rotate `setOracleSigner`, revoke `MINTER_ROLE`).
- [ ] Invariant test suite (INVARIANTS.md) green in CI; CI actually runs on push (currently the
      foundry CI triggers are commented out).

---

## 7. TL;DR

- **Verdict: not releasable for real value today.** One confirmed unauthenticated drain (CRIT-1,
  fixed-in-branch, needs verification) + ~8 HIGH issues, each a launch blocker.
- **Genuinely safe:** the EVM token crypto, the wrap/claim amount path, decimals, secrets hygiene.
  Lead your confidence from here.
- **The danger lives in the unwrap payout path and the engine's disabled risk controls** — not in
  the web app, which is sound-but-under-defending.
- **Biggest scope-reducer:** ship the bridge with the **engine disabled**; the engine's worst issues
  are live-trading issues, not custody issues.
- **Mental model fix:** it's not "90% done" — it's a **gate list** (§6). Close every gate, prove each
  with a test, *then* you're confident. That's the path out of the discomfort.
- Don't trust the old docs; trust [`INVARIANTS.md`](./INVARIANTS.md), [`FINDINGS.md`](./FINDINGS.md),
  and the cited code.
