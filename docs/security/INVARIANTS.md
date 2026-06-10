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
| **INV-1** | **No unbacked mint.** Every wrapped-token mint corresponds to a unique, chain-verified Zephyr deposit of the matching asset and amount. | HELD | Wrap amount is chain-derived ✅ (`claims/ingest.ts:108-112`); replay blocked by `usedZephyrTx` ✅. Supply invariant pinned (`Supply_TracksMintMinusBurn`, stateful fuzz) and the only supply-destroying path is `burnWithData` (emits `Burned`) — inherited `burn()`/`burnFrom()` revert (`PlainBurn_Disabled_Reverts`). Residual: signer-key compromise has no on-chain cap (contract single-key — see [key-ops-and-contract-posture.md](./key-ops-and-contract-posture.md), accepted/owner-decision). |
| **INV-2** | **No double-credit.** A single Zephyr deposit tx can never mint twice (across restarts, rescans, or token contracts). | PARTIAL | On-chain `usedZephyrTx` per token ✅; DB primary key = `bytes32(zephTxId)` ✅. Untested: concurrent claim+rescan race; cross-token (one tx legitimately consumable once per *each* of 4 tokens — off-chain-only guard). |
| **INV-3** | **No over-payout on unwrap.** The native payout never exceeds the value actually burned on-chain. | HELD | **CRIT-1** guard in place (`burnedAtomic ≥ preparedPayoutAtomic`) and pinned: `LB-AMT-COVERS`/`LB-AMT-DRAIN` (burn < prepared ⇒ no relay) + `flow_prepare_without_burn_pays_nothing` (live). Residual architectural fix (size payout *from* the burn, authenticate prepare) still recommended — see FINDINGS CRIT-1. |
| **INV-4** | **No double-payout.** A single burn event pays out at most once, even across watcher crash/restart mid-broadcast. | PARTIAL | Lock + `sendStatus` guard exist, but the `sending`-state crash window re-relays (**HIGH-8**) → the `tx_rejected` flake. No crash-restart idempotency test. |
| **INV-5** | **Asset-type integrity.** A ZSD deposit is credited only as wZSD (never wZEPH), and burns map to the correct native asset. | HELD | Asset→token mapping pinned per asset (`flow_wrap_asset_mints_correct_token[ZSD/ZRS/ZYS]` + ZPH, live). `transformTransfer` now **rejects** a missing/unsupported `asset_type` against `SUPPORTED_ASSET_TYPES` instead of defaulting to `"ZEPH"` (`watcher-zephyr index.ts:190`) — confirmed live that every real deposit carries an explicit V2 asset_type. Zero-amount burn rejected (`BurnWithData_ZeroAmount_Reverts`). |
| **INV-6** | **Decimal correctness.** 12-dec Zephyr atomic ↔ 12-dec wrapped token is 1:1 with no precision loss in the money direction (rounding favors the bridge, never the user-at-bridge-expense). | ENFORCED-UNTESTED | 1:1 confirmed ✅ (`amount.ts`, `ZephyrWrappedToken.decimals()==12`); wei→atomic floors (favors bridge) ✅. No property test across the full range; 2 failing liquidity-math decimal tests in the engine suite. |
| **INV-7** | **Claim non-expiry trap.** A user who made a real deposit can always eventually claim it (no permanent lockout). | HELD | Admin-gated re-sign endpoint added (`POST /claims/:evm/resign`, `requireAdmin` → 403 unauth) that re-issues a fresh voucher for an expired-but-unclaimed deposit; pinned by `flow_expired_voucher_has_resign_path` (live). |

## B. Signature / replay invariants (the crypto gate)

| # | Invariant | Status | Evidence / gap |
|---|---|---|---|
| **INV-8** | **Voucher unforgeable.** Only the oracle signer can produce a valid claim; sig is bound to (to, amount, zephTxHash, deadline, this token, this chain). | ENFORCED-UNTESTED | EIP-712 domain w/ chainId + verifyingContract ✅ (`ZephyrWrappedToken.sol:57`); OZ 5.4 ECDSA ✅. **Zero contract tests exist** for wrong-signer / expired / malleable / cross-token / cross-chain. |
| **INV-9** | **No signature replay** across tokens, chains, or repeated submission. | ENFORCED-UNTESTED | Domain separation + `usedZephyrTx` ✅. Untested: replay a wZEPH voucher against a second wZEPH deployment on the same chain (different address — blocked by `verifyingContract`, but unpinned by test). |
| **INV-10** | **Burn nonce non-replay.** `usedNonce[msg.sender][nonce]` blocks burn-event replay. | ENFORCED-UNTESTED | ✅ `ZephyrWrappedToken.sol:131-138`; no test. |

## C. Finality / consistency invariants

| # | Invariant | Status | Evidence / gap |
|---|---|---|---|
| **INV-11** | **No payout before finality.** Burn→payout waits for an agreed EVM confirmation depth; wrap voucher invalidated if the deposit reorgs out. | HELD | `ingestEvmBurn` parks a burn shallower than `UNWRAP_RELAY_CONFIRMATIONS` (devnet=3) as `pending`; the EVM watcher's confirmation sweep (`relayConfirmedUnwraps`) relays only once buried reorg-safe deep. Burn block persisted (`Unwrap.evmBlockNumber`). Pinned: `LB-CONF-*` (depth/gate/head/cursor/reorg) + `res_unwrap_relayed_only_after_reorg_safe_depth` (live). Residual: no Zephyr-side reorg handling after voucher signing (separate from the EVM burn gate). |
| **INV-12** | **Watcher exactly-once.** Across crashes/WS-reconnects, every relevant event is processed exactly once (no missed `Burned`/`Minted`, no duplicate ingest). | PARTIAL | Cursors advance only on delivered logs; **WS-reconnect gap-fill missing** (HIGH); backfill only at startup. |
| **INV-13** | **Unwrap status truthfulness.** UI/API "complete" ⇔ the native payout actually landed on-chain. | VIOLATED | Unwrap confirm reads **stale wallet height** not daemon → never flips `pending→confirmed` (`recovery.ts:4`); UI maps only `confirmed→complete` so it sticks (`unwrap-client.tsx:43-68`). |

## D. Engine invariants (gate only if the engine runs against real value)

| # | Invariant | Status | Evidence / gap |
|---|---|---|---|
| **INV-14** | **Engine cannot drain inventory on a bad/stale/ manipulated price.** Armed risk limits + real slippage floor + freshness gate. | HELD | Risk controls default ON + wired into execution (`LE-RISK-DEFAULT-ON`, `LE-EXEC-RISK-WIRING`); native-oracle price-freshness signal gates auto-exec (`LE-PRICE-FRESHNESS`, `mkt_engine_tracks_native_price_freshness` live); loss breaker armed (`LE-LOSS-BREAKER`); arb detection/approval gating pinned live (`mkt_arb_detect_*`, `mkt_approval_*`). |
| **INV-15** | **Realized accounting.** Recorded PnL and the loss-tracker use *actual* fill amounts, not forecasts. | HELD | Risk wiring threads realized execution outputs into the loss tracker so the daily-loss breaker is reachable (`LE-EXEC-RISK-WIRING`, `LE-LOSS-BREAKER`, `LE-RISK-DEFAULT-ON`). |
| **INV-16** | **No fund-burning loop.** The engine cannot ping-pong wrap/unwrap (paying real fees) on accounting-only CEX legs. | PARTIAL | Only the 60s cooldown brakes it; CEX trades move nothing while bridge legs move real funds + fee. |
| **INV-17** | **Execution-time gating.** Conversion availability (rrMode) and prices are re-checked at execution, not just at evaluation. | HELD | Engine gate model aligned to the protocol RR table (MINT_STABLE@400, MINT_RESERVE@800, yield-halt@200) and re-checked; the engine no longer emits a plan that closes via a daemon-rejected conversion. Pinned: `LE-CONFORM-GATES` + `mkt_gate_conform_*`, `mkt_no_doomed_plan_*`, `mkt_rrmode_*` (live). |

## E. Authorization invariants

| # | Invariant | Status | Evidence / gap |
|---|---|---|---|
| **INV-18** | **Every state-mutating privileged route requires a real auth token.** | PARTIAL (1 design fork) | Bridge `/debug/*` now `requireAdmin`-gated (401 unauth) and the destructive GET DB-reset removed (HIGH-1 closed; `sec_debug_backup_requires_auth` live). **Open — DESIGN FORK:** engine `/api/engine/{runner,queue}` (toggle auto-exec; approve/reject queued ops) are **same-origin, browser-driven** (`apps/web/app/engine/page.tsx`, `'use client'`, relative `fetch`). A static bearer token would have to ship in the browser bundle = forgeable = false green. Real auth needs an **operator-auth mechanism decision** (session-cookie login / network isolation / reverse-proxy auth). Kept `@known_gap(INV-18)` (`sec_engine_{runner,queue}_unauth`) pending that decision — see FINDINGS HIGH-1 / [key-ops-and-contract-posture.md](./key-ops-and-contract-posture.md). |
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
