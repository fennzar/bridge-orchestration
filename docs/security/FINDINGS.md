---
title: Security Findings Register
status: AUTHORITATIVE (security)
author: security review — 5 parallel sub-audits, deduped
date: 2026-06-10
verification: "✅ verified vs code this session · ⚠️ from sub-audit, plausible · ❓ open"
---

# Security Findings Register

Deduped across bridge-api, bridge-web, contracts, watchers, and engine audits. Severity =
expected loss × likelihood. Each finding: where · what · why it matters · fix · status.
Cross-referenced to `INVARIANTS.md` (INV-#).

---

## CRITICAL

### CRIT-1 — Unauthenticated unwrap hot-wallet drain  ✅  (INV-3) — FIXED-IN-BRANCH
- **Where:** `apps/api/src/routes/unwraps.ts:74-132` + `packages/bridge/src/unwraps/payload.ts:14-20` + `zephyr-eth-foundry/src/ZephyrWrappedToken.sol:129-138` + `packages/bridge/src/unwraps/ingest.ts:368-407`.
- **What:** `/unwraps/prepare` (unauth) pre-signs a payout for a client-supplied amount; the burn payload carries no amount; `burnWithData` is opaque; the watcher relays the pre-signed amount without checking the actual burn. Prepare-large + burn-dust = drain.
- **Fix (done, interim):** amount-binding guard in `ingest.ts` — relay only if `weiToAtomic(burnWei) ≥ preparedPayoutAtomic`, else throw (fail-safe). **Real fix (pending):** size+sign payout from the observed burn; authenticate + rate-limit `/unwraps/prepare`.
- **Status:** guard applied + typecheck-clean; ❓ needs invariant test + live-stack verification.

---

## HIGH

### HIGH-1 — Destructive debug routes gated by a client-facing flag  ✅  (INV-18)
- **Where:** `apps/api/src/routes/debug/index.ts:8-85`.
- **What:** `/debug/reset/database` (incl. **GET** → CSRF/prefetch-triggerable) and `/debug/bridge-accounts/backup` (dumps full EVM↔Zephyr deposit-address map) gated only by `NEXT_PUBLIC_ENABLE_DEV_CONTROLS`/`ENABLE_DEV_RESET`, no admin token.
- **Fix:** `requireAdmin` on all `/debug/*`; remove the GET reset; never gate destructive ops on a `NEXT_PUBLIC_*` flag. Confirm these flags are OFF on the testnet host.

### HIGH-2 — Burn→payout at 0 EVM confirmations  ✅  (INV-11) — FIXED
- **Where:** `apps/watcher-evm/src/index.ts`; `confirmations.ts` (`getUnwrapRelayConfirmations`).
- **What:** payout relayed at chain head; a reorg dropping the burn after payout = irreversible ZEPH loss on real chains. Anvil masks this.
- **Fix (done):** `ingestEvmBurn` parks a burn shallower than `UNWRAP_RELAY_CONFIRMATIONS` (devnet=3) as `pending`; the watcher's confirmation sweep (`relayConfirmedUnwraps`) relays only once `headBlock − burnBlock ≥ target`. Burn block persisted (`Unwrap.evmBlockNumber`). Pinned `LB-CONF-*` + `res_unwrap_relayed_only_after_reorg_safe_depth` (live). **Devnet posture:** with the gate on, standalone/engine-run unwraps need block production past the depth — interval-mining (`anvil --block-time`) is the companion; the suite mines the depth explicitly.

### HIGH-3 — Web never decodes the unwrap burn payload  ⚠️  (Boundary A)
- **Where:** `apps/web/app/unwrap/unwrap-client.tsx:300-326`; `use-contract.ts:184`.
- **What:** the burn `destination` arg is the API `payload` blob, passed verbatim, never decoded to confirm it encodes the address the user typed. Sign ≠ display under API compromise.
- **Fix:** `decodeBurnPayload(payload)` client-side; hard-block burn if `decoded.destination !== userInput` (and fingerprint mismatch). Decoder already exists.

### HIGH-4 — Web grants unlimited approvals to API-supplied spenders  ⚠️  (Boundary A)
- **Where:** swap `swap-client.tsx:201-243,356-374`; LP `use-token-approval.ts:139-166`, `use-liquidity-actions.ts:49-71`.
- **What:** `router`/`permit2`/`positionManager` come from `/uniswap/config` with no pinning; approvals are `MaxUint256`/`MAX_UINT160`. Malicious config → unlimited approval to attacker.
- **Fix:** cross-check against `@zephyr-bridge/config` (`getPermit2Address`/`getPositionManagerAddress`/`getSwapRouterAddress` exist) and refuse on mismatch; prefer exact-amount approvals.

### HIGH-5 — Engine risk controls disabled by default  ✅  (INV-14)
- **Where:** `src/domain/risk/limits.ts:26` (`enabled:false`); `circuitBreaker.ts:59-61`.
- **What:** `canExecute()` always allows; thresholds no-op. `RISK_CONTROLS_ENABLED=true` not set in Procfiles.
- **Fix:** arm risk controls in any real-value config; make the engine refuse to start in live mode with controls disabled.

### HIGH-6 — Zero slippage floor on peg/rebalance swaps  ✅  (INV-14)
- **Where:** `src/domain/execution/execution.dispatch.ts:108` (`amountOutMin: step.expectedAmountOut ?? 0n`); peg/rebalancer never set `expectedAmountOut`; LP burn `amount0Min/1Min:0`.
- **What:** unbounded slippage → trivially sandwichable.
- **Fix:** compute and enforce a real `amountOutMin` (quote − tolerance) on every swap/burn.

### HIGH-7 — PnL/loss tracker uses forecast, not realized  ✅  (INV-15) — FIXED
- **Where:** `apps/engine/src/engine.helpers.ts`; `engine.execution.ts`.
- **What:** `calculatePnlFromSteps` returned `expectedPnl`; the breaker's daily-loss trip was unreachable even when enabled.
- **Fix (done):** risk controls default ON and wired into execution; realized execution outputs feed the loss tracker so the daily-loss breaker is reachable. Pinned `LE-EXEC-RISK-WIRING`, `LE-LOSS-BREAKER`, `LE-RISK-DEFAULT-ON`.

### HIGH-8 — Double-relay window on watcher crash  ✅  (INV-4)
- **Where:** `packages/bridge/src/unwraps/ingest.ts:393-426`; `apps/api/src/routes/admin/unwraps.ts` (`/retry`, `/resend`); `packages/bridge/src/unwraps/recovery.ts` (`decideResend`).
- **What:** crash between broadcast and persistence re-ingests the burn; `sending`-state guard falls through → re-relay → `error::tx_rejected` double-spend. (This was the documented "unwrap flake.")
- **Fix (shipped):** the recovery model is now anchored on the **pre-signed payout** (fixed inputs → stable commit hash → mines at most once), so re-relaying is *idempotent* by construction, not a double-spend.
  - **Idempotent recovery** (`/retry`, ingest entry-reconcile) re-relays / converges to the *same* pre-signed tx — safe to repeat across crash/restart/redelivery.
  - **Fresh-input** payout exists only on `POST /admin/unwraps/:id/resend` (`zephyrTransferSimple`, new UTXOs → breaks idempotency). `decideResend` gates it structurally: fresh-send *only* when **no pre-signed commit exists in any persisted source** — row `zephTxId`/`zephTxHashHex`/`preparedZephTxId`/`preparedZephTxHashHex`, a linked `ZephyrPrepared`/`ZephyrOutgoing` draft (looked up by id **and** by unwrapId, failing **closed** on lookup error), or the structured `burnPayload.txHash` — **and** no payout lineage. Any commit → heal (visibly on-chain) or refuse (409). Lookup uncertainty (`get_transfer_by_txid` -8 is ambiguous: mempool ≡ never-existed) → refuse fail-closed (503, retryable). Safety is therefore **structural**, independent of probe accuracy.
- **Verification:** `LB-RESEND` (`decideResend` unit table) + live `RES-DOUBLE-PAYOUT` / `RES-RESEND-FAILCLOSED` / `RES-RESEND-DRAFT-RECOVERY` / `RES-RESEND-PAYLOAD-RECOVERY` / `RES-REINGEST`. Peer-reviewed through source-enumeration convergence (no second `zephyrTransferSimple` path; no separate persisted EVM-burn store carrying another commit). INV-4 → **HELD**.

---

## MEDIUM (selected — full list in sub-audit reports)

- **MED-1** ❓ Engine manual-approval path deserializes plans with string bigints (`engine.queue.ts:43`, `op.plan as unknown`) → type-broken amounts in the *default* prod path. (INV-15)
- **MED-2** ✅ Unwrap "stuck pending" — FIXED. The scheduled `reconcilePendingUnwraps` sweep reads the payout transfer's own mined height via `getTransferByTxid` and flips `pending→confirmed` once `height>0` (`reconcile.ts:81-108`); no longer gated on the wallet's stale internal height. Pinned by live `test_flow_unwrap_pays_out_and_status_confirms` (status reaches `confirmed` ~24s, no skip). INV-13 → HELD. (INV-13)
- **MED-3** ✅ Missing `asset_type` defaults to `"ZEPH"` in deposit ingest (`watcher-zephyr index.ts:190`) — asset-confusion seam. (INV-5)
- **MED-4** ⚠️ No rate limiting anywhere; CORS `*` on unauthenticated mutating routes. (INV-19)
- **MED-5** ⚠️ Web has no wrong-network guard on wrap/unwrap/swap/lp (only `/testnet`); swap/LP approvals not `simulateContract`-checked. (Boundary D)
- **MED-6** ⚠️ Web claim path doesn't validate target token ∈ pinned list, nor `to == connected address`, nor display `to`. (Boundary A)
- **MED-7** ⚠️ Engine RR/conversion availability not re-checked at execution time. (INV-17)
- **MED-8** ⚠️ Engine prices conversions at spot, ignoring the protocol's mint=MAX(spot,MA)/redeem=MIN(spot,MA) spread the code itself computes → overstates arb edge. (INV-14)
- **MED-9** ⚠️ Engine wrap leg returns success without a claim ever happening → strands wZEPH unclaimed (`bridge/executor.ts:161-169`).
- **MED-10** ⚠️ No security headers / CSP on the wallet-signing web app (`next.config.mjs`) → clickjacking surface.
- **MED-11** ⚠️ Unwrap `destination` not validated as a real Zephyr address before pre-signing (`unwraps.ts:86-132`).
- **MED-12** ✅ ACCEPTED (network isolation) — Engine control plane (`/api/engine/queue`, `/runner`) is unauthenticated but same-origin/browser-driven with no external caller. Owner decision 2026-06-10: engine runs operator-only behind an authenticated reverse proxy / private network (the documented testnet deployment firewalls 7000 and does not proxy it; reach via SSH tunnel). An in-bundle token would be forgeable theater, so not added. Marked `@accepted_risk(INV-18)`. See [engine-deployment-posture.md](./engine-deployment-posture.md). (DB `manualApproval` overriding the CLI flag is a separate INV-15/correctness note, not an auth gap.)

## LOW (selected)

- **LOW-1** ⚠️ Global `onError` leaks `err.message`; `/debug/evm/*` not env-gated, leak RPC URL + stack.
- **LOW-2** ⚠️ Faucet falls back to `BRIDGE_PK` if no faucet key (crown-jewel reuse; faucet off on mainnet).
- **LOW-3** ⚠️ Per-address SSE / `lookupAddress` unauthenticated → privacy/deanonymization.
- **LOW-4** ⚠️ Admin token compared with non-constant-time `===`.
- **LOW-5** ✅ Contract `burn`/`burnFrom` (from `ERC20Burnable`) bypass `Burned` event entirely → tokens destroyed with no unwrap trigger; `burnWithData` accepts `amount==0`/empty destination.
- **LOW-6** ✅ Foundry CI triggers commented out (`.github/workflows/test.yml`) → tests never run automatically.

---

## Contract structural risks (not bugs, but launch-blocking posture)

- **No pause / no mint cap / no timelock / single hot keys.** Compromise of `MINTER_ROLE` *or* the
  oracle signer = unbounded unbacked mint with no on-chain circuit breaker. ✅ verified absent in
  `ZephyrWrappedToken.sol`. Decision required before real value: Pausable + per-epoch mint cap +
  multisig admin, *or* a written, explicit risk acceptance + a tested compromise runbook.
- **Deploy roles default to a single deployer key** if `ADMIN`/`MINTER`/`SIGNER` env unset
  (`script/01_DeployZephyrTokens.sol:38-40`) — fine on devnet, dangerous if the same script shape
  is reused for mainnet. ✅
- **Zero tests for `ZephyrWrappedToken`** — `test/` holds only the Uniswap v4 template. ✅

---

## Notes on trust of THIS document

CRIT-1, HIGH-1, HIGH-5, HIGH-6, MED-3, LOW-5/6 and the contract posture were **re-verified against
code this session** (✅). Items marked ⚠️ come from the parallel sub-audits and are consistent with
the code I did read, but were not independently re-traced — verify before acting on a ⚠️ in a money
path. Items marked ❓ need a running stack or a human decision.
