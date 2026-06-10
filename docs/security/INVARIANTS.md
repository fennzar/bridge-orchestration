---
title: Money-Critical Invariant Ledger
status: AUTHORITATIVE (security) — this is the release gate
author: security review
date: 2026-06-10
coverage_legend:
  HELD: enforced in code AND covered by an automated invariant test
  ENFORCED-UNTESTED: enforced in code but no automated test pins it
  PARTIAL: partially enforced / tested only on the happy path
  VIOLATED: a known code path breaks this invariant today
  NONE: neither reliably enforced nor tested
---

# Money-Critical Invariant Ledger

This is the **gate list**. The bridge is releasable for real value when every invariant below is
`HELD` — enforced in code *and* pinned by an automated test that fails loudly if the property
breaks. "Confidence" is not a feeling; it is this table being green.

Tests are now **invariant-driven**: each pins a row below and asserts the *property*, not an API
shape (see [`tests/CATALOG.md`](../../tests/CATALOG.md) and [`docs/testing/README.md`](../testing/README.md)).
`make test-report` rolls every layer into this gate. Many rows are red-by-design today (KNOWN-GAP) —
that red is the worklist; a row goes green only when a tagged test holds it.

---

## A. Custody invariants (the ones that lose user money)

| # | Invariant | Status | Evidence / gap |
|---|---|---|---|
| **INV-1** | **No unbacked mint.** Every wrapped-token mint corresponds to a unique, chain-verified Zephyr deposit of the matching asset and amount. | PARTIAL | Wrap amount is chain-derived ✅ (`claims/ingest.ts:108-112`); replay blocked by `usedZephyrTx` ✅. But no test asserts "mint ⇒ prior verified deposit ≥ mint", and signer-key compromise has no on-chain cap. |
| **INV-2** | **No double-credit.** A single Zephyr deposit tx can never mint twice (across restarts, rescans, or token contracts). | PARTIAL | On-chain `usedZephyrTx` per token ✅; DB primary key = `bytes32(zephTxId)` ✅. Untested: concurrent claim+rescan race; cross-token (one tx legitimately consumable once per *each* of 4 tokens — off-chain-only guard). |
| **INV-3** | **No over-payout on unwrap.** The native payout never exceeds the value actually burned on-chain. | VIOLATED → fixed-in-branch | **CRIT-1**: pre-fix the payout amount came from an unauthenticated prepare request, never reconciled to the burn (`ingest.ts:368-407`). Interim guard added (`burnedAtomic ≥ preparedPayoutAtomic`); **needs a test** `burn < prepared ⇒ throw, no relay`. |
| **INV-4** | **No double-payout.** A single burn event pays out at most once, even across watcher crash/restart mid-broadcast. | PARTIAL | Lock + `sendStatus` guard exist, but the `sending`-state crash window re-relays (**HIGH-8**) → the `tx_rejected` flake. No crash-restart idempotency test. |
| **INV-5** | **Asset-type integrity.** A ZSD deposit is credited only as wZSD (never wZEPH), and burns map to the correct native asset. | PARTIAL | Asset→token mapping exists, but `transformTransfer` defaults missing `asset_type` to `"ZEPH"` (**MED**, `watcher-zephyr index.ts:190`) — should reject. No multi-asset-in-one-tx test. |
| **INV-6** | **Decimal correctness.** 12-dec Zephyr atomic ↔ 12-dec wrapped token is 1:1 with no precision loss in the money direction (rounding favors the bridge, never the user-at-bridge-expense). | ENFORCED-UNTESTED | 1:1 confirmed ✅ (`amount.ts`, `ZephyrWrappedToken.decimals()==12`); wei→atomic floors (favors bridge) ✅. No property test across the full range; 2 failing liquidity-math decimal tests in the engine suite. |
| **INV-7** | **Claim non-expiry trap.** A user who made a real deposit can always eventually claim it (no permanent lockout). | VIOLATED | Voucher TTL 24h, lazy→`expired`, **no re-sign endpoint** → a real deposit unclaimed within 24h of signing is stuck (**HIGH/MED**, `claims/signer.ts:36-39`). Needs an admin-or-owner re-sign path. |

## B. Signature / replay invariants (the crypto gate)

| # | Invariant | Status | Evidence / gap |
|---|---|---|---|
| **INV-8** | **Voucher unforgeable.** Only the oracle signer can produce a valid claim; sig is bound to (to, amount, zephTxHash, deadline, this token, this chain). | ENFORCED-UNTESTED | EIP-712 domain w/ chainId + verifyingContract ✅ (`ZephyrWrappedToken.sol:57`); OZ 5.4 ECDSA ✅. **Zero contract tests exist** for wrong-signer / expired / malleable / cross-token / cross-chain. |
| **INV-9** | **No signature replay** across tokens, chains, or repeated submission. | ENFORCED-UNTESTED | Domain separation + `usedZephyrTx` ✅. Untested: replay a wZEPH voucher against a second wZEPH deployment on the same chain (different address — blocked by `verifyingContract`, but unpinned by test). |
| **INV-10** | **Burn nonce non-replay.** `usedNonce[msg.sender][nonce]` blocks burn-event replay. | ENFORCED-UNTESTED | ✅ `ZephyrWrappedToken.sol:131-138`; no test. |

## C. Finality / consistency invariants

| # | Invariant | Status | Evidence / gap |
|---|---|---|---|
| **INV-11** | **No payout before finality.** Burn→payout waits for an agreed EVM confirmation depth; wrap voucher invalidated if the deposit reorgs out. | VIOLATED | **HIGH-2**: 0-conf payout (`getEvmConfirmationTarget` unused in burn path); no Zephyr reorg handling after signing. Devnet-masked. |
| **INV-12** | **Watcher exactly-once.** Across crashes/WS-reconnects, every relevant event is processed exactly once (no missed `Burned`/`Minted`, no duplicate ingest). | PARTIAL | Cursors advance only on delivered logs; **WS-reconnect gap-fill missing** (HIGH); backfill only at startup. |
| **INV-13** | **Unwrap status truthfulness.** UI/API "complete" ⇔ the native payout actually landed on-chain. | VIOLATED | Unwrap confirm reads **stale wallet height** not daemon → never flips `pending→confirmed` (`recovery.ts:4`); UI maps only `confirmed→complete` so it sticks (`unwrap-client.tsx:43-68`). |

## D. Engine invariants (gate only if the engine runs against real value)

| # | Invariant | Status | Evidence / gap |
|---|---|---|---|
| **INV-14** | **Engine cannot drain inventory on a bad/stale/ manipulated price.** Armed risk limits + real slippage floor + freshness gate. | VIOLATED | Risk controls `enabled:false` by default (HIGH-5); `amountOutMin ?? 0n` (HIGH-6); Zephyr oracle staleness never blocks. |
| **INV-15** | **Realized accounting.** Recorded PnL and the loss-tracker use *actual* fill amounts, not forecasts. | VIOLATED | PnL = `expectedPnl` always (HIGH-7); breaker fed forecasts → daily-loss trip unreachable. |
| **INV-16** | **No fund-burning loop.** The engine cannot ping-pong wrap/unwrap (paying real fees) on accounting-only CEX legs. | PARTIAL | Only the 60s cooldown brakes it; CEX trades move nothing while bridge legs move real funds + fee. |
| **INV-17** | **Execution-time gating.** Conversion availability (rrMode) and prices are re-checked at execution, not just at evaluation. | VIOLATED | RR sampled once at evaluate; manually-approved plans execute later with no re-check. |

## E. Authorization invariants

| # | Invariant | Status | Evidence / gap |
|---|---|---|---|
| **INV-18** | **Every state-mutating privileged route requires a real auth token.** | VIOLATED | Destructive `/debug/*` gated by `NEXT_PUBLIC_*` flag, incl. a GET DB-reset (HIGH-1); engine control plane (`/api/engine/queue`,`/runner`) unauthenticated. |
| **INV-19** | **`/unwraps/prepare` cannot be weaponized** (no unauthenticated commitment of bridge-wallet inputs / griefing). | PARTIAL | Open + unauth; even post-CRIT-1-fix it can spam prepares to contend wallet inputs (DoS). Needs auth/rate-limit. |

---

## How to use this ledger

1. **Pick an invariant.** Write the *negative* test first — the attack that would violate it — and
   confirm it currently fails (or, for VIOLATED rows, currently *passes the attack*).
2. **Fix the code** until the attack is blocked.
3. **Promote the row to `HELD`** only when the test is in CI and green.
4. **Release gate:** all of section A, B, C, E `HELD`; section D `HELD` *or* the engine is disabled
   for launch (documented decision).

This table — not a vibe — is the definition of "confident enough to release." See
`STATE-OF-THE-BRIDGE.md` §6 for the rolled-up checklist and `FINDINGS.md` for the fixes.
