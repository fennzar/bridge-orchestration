---
title: ETH Bridge Protocol Specification
status: AUTHORITATIVE — ground-truth from code (cited)
author: security review
date: 2026-06-10
audience: both (humans + agents)
scope: wrap, claim, unwrap message formats + replay + decimals + state machine
---

# ETH Bridge Protocol Specification

This is the **precise, code-cited spec** of how value crosses the Zephyr↔EVM boundary. Where prior
docs describe intent, this describes what the code actually does (with file:line). If you change any
of these formats, you change the protocol — update this doc and the invariant tests together.

The bridge is **custodial and 1:1**: native Zephyr held in a hot wallet backs each wrapped ERC-20.

---

## 1. Components

| Component | Repo / path | Role |
|---|---|---|
| Wrapped tokens | `zephyr-eth-foundry/src/ZephyrWrappedToken.sol` | wZEPH/wZSD/wZRS/wZYS; mint, burn, claim |
| bridge-api | `zephyr-bridge/apps/api` (Hono :7051) | deposit-address registry, claim signer, unwrap prepare |
| watcher-zephyr | `zephyr-bridge/apps/watcher-zephyr` | detect deposits → enable claim signing |
| watcher-evm | `zephyr-bridge/apps/watcher-evm` | detect mints/burns → relay native payout |
| bridge-web | `zephyr-bridge/apps/web` (Next.js :7050) | user dapp |
| shared | `zephyr-bridge/packages/{bridge,db,zephyr,evm,config}` | ingest logic, Prisma, RPC, viem |

---

## 2. WRAP (Zephyr → EVM): deposit → voucher → mint

```
user → POST /bridge/address {evmAddress}           → bridge returns a dedicated Zephyr subaddress
user → send native ZPH/ZSD/ZRS/ZYS to that subaddress
watcher-zephyr (every ~5s):
  daemon get_info → true tip; wallet get_transfers → incoming
  for each deposit tx: ingestZephyrTransfer  → Claim record (pending→queued→ready)
  at ≥ N confirmations: signClaim → EIP-712 voucher (status: claimable)
user → claimWithSignature(to, amount, zephyrTxHash, deadline, signature)  → wZ* minted
watcher-evm: MintedFromZephyr event → mark claim `claimed`
```

### The claim voucher (EIP-712) — exact format
- **Domain:** `EIP712("ZephyrClaims", "1")` — OZ includes `chainId` + `verifyingContract` (the token).
  `ZephyrWrappedToken.sol:57`.
- **Type:** `Claim(address to,uint256 amount,bytes32 zephyrTxHash,uint256 deadline)`.
  `ZephyrWrappedToken.sol:40-42`.
- **Signer:** `oracleSigner` (env `BRIDGE_PK`), verified on-chain in `claimWithSignature`
  (`:106-118`). **The amount is derived from the chain-verified deposit** (`tx.amountAtomic`),
  not from any client input — `packages/bridge/src/claims/ingest.ts:108-112`.
- **Replay:** `usedZephyrTx[zephyrTxHash]` (per token) blocks re-mint; DB primary key is
  `bytes32(zephTxId)`. `ZephyrWrappedToken.sol:164-170`.
- **Expiry:** deadline enforced on-chain (`:113`); voucher TTL ~24h off-chain. ⚠️ **No re-sign path**
  → an unclaimed-in-time deposit is stuck (INV-7).

**Security status: SOUND.** The wrap amount path is the model the unwrap path should follow.

## 3. UNWRAP (EVM → Zephyr): prepare → burn → payout

```
user → POST /unwraps/prepare {token, amountWei, destination}
       bridge PRE-SIGNS a Zephyr payout (do_not_relay) for `amountWei`→`destination`,
       returns `payload` (opaque bytes) + draftId            ← unwraps.ts:74-132
user → burnWithData(amount, payload, nonce)                  ← ZephyrWrappedToken.sol:129-138
watcher-evm: Burned event → ingestEvmBurn
       decode payload → preparedHash → load pre-signed metadata → relayZephyrTransfer
       (native payout broadcast)                             ← ingest.ts:360-429
```

### The burn payload — exact format
ABI-encoded `(uint8 version, bytes32 txHash, bytes32 walletFingerprint, bytes destination)`,
version=1. **Carries no amount.** `packages/bridge/src/unwraps/payload.ts:14-20`.

### ⚠️ SECURITY-CRITICAL property (CRIT-1)
The pre-signed payout amount comes from the **unauthenticated** `/unwraps/prepare` request body and
was **not** reconciled against the actual on-chain burn (`ingest.ts` pre-fix). The contract's
`burnWithData` treats the payload as opaque and does not bind amount. **This allowed a
prepare-large + burn-dust drain.** An interim amount-binding guard now blocks relay unless
`weiToAtomic(burnedAmount) ≥ preparedPayoutAtomic`. **The protocol-correct design (not yet
implemented):** the payout must be *sized and signed from the observed burn*, after the burn is
final, and `/unwraps/prepare` must be authenticated/rate-limited. See `../security/STATE-OF-THE-BRIDGE.md` §2.

### Burn nonce
`usedNonce[msg.sender][nonce]` blocks per-account burn replay (`:131-138`). Note: plain
`ERC20Burnable.burn()`/`burnFrom()` are inherited and **bypass `burnWithData` entirely** — they emit
no `Burned` event, so tokens can be destroyed with no unwrap (FINDINGS LOW-5). Consider disabling them.

## 4. Decimals (both directions)
- Wrapped tokens are **12 decimals** (`ZephyrWrappedToken.decimals()==12`, `:66-68`) to mirror
  Zephyr's atomic units → **1:1, no scaling**. The bridge field `amountWei` is a misnomer (it's
  12-dec base units). Conversion helpers floor wei→atomic (rounding favors the bridge):
  `packages/bridge/src/unwraps/amount.ts:54-65`.

## 5. State machines
- **Claim:** `pending → queued → ready → (sign) → claimable → claimed`; `expired` on deadline pass.
- **Unwrap:** `pending → (relay) → confirmed`; plus `sendStatus(idle→sending→sent)` and
  `reconcileStatus`. ⚠️ Confirm is driven by **stale wallet height**, so it often never reaches
  `confirmed` → UI sticks (INV-13 / FINDINGS MED-2). Fix: confirm via daemon.

## 6. On-chain roles
- `DEFAULT_ADMIN_ROLE` (rotate signer, grant roles), `MINTER_ROLE` (`mintFromZephyr`, unbounded),
  `oracleSigner` (claim signer; rotated by admin). **No pause, no mint cap, no multisig** today
  (FINDINGS contract posture).

## 7. The 1:1 backing invariant (the whole point)
At all times: `Σ wrapped-token supply (per asset) ≤ native Zephyr held by the bridge (per asset)`.
Every CRIT/HIGH in the findings register is ultimately a way this invariant can break — unbacked
mint (signer compromise), over-payout (CRIT-1), reorg double-spend (HIGH-2), double-relay (HIGH-8).
Pin it with INV-1/INV-3 tests.

---

## See also
- `zephyr-primer.md` — the underlying asset/reserve mechanics.
- `../security/INVARIANTS.md` — the invariants this spec must uphold.
- `zephyr-bridge/docs/{wrap-flow,unwrap-flow}.md` — older flow docs (useful but predate CRIT-1; treat as secondary).
