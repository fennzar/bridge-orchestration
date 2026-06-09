---
title: Bridge Threat Model & Trust Boundaries
status: AUTHORITATIVE (security)
author: security review
date: 2026-06-10
scope: Zephyr ↔ EVM custodial bridge (wrap, unwrap, claim, swap, LP) + strategy engine
---

# Bridge Threat Model & Trust Boundaries

This is the system's security backbone: **what we are protecting, from whom, and where the trust
boundaries lie.** If a proposed change touches any boundary below, it needs a security review.

---

## 1. Assets (what an attacker wants)

| Asset | Where it lives | Loss if compromised |
|---|---|---|
| **Bridge Zephyr hot wallet** | `wallet-*` RPC, key on bridge host | Direct theft of all native ZPH/ZSD/ZRS/ZYS reserves (this backs every wrapped token). |
| **Oracle signer key** (`BRIDGE_PK`) | env on bridge-api host | Can sign arbitrary claim vouchers → **mint unbacked wrapped tokens** → drain pools. The crown jewel. |
| **MINTER_ROLE key** | EVM, held by deployer/operator | Can `mintFromZephyr` arbitrary amounts directly → unbacked mint. |
| **DEFAULT_ADMIN_ROLE key** | EVM | Can rotate the oracle signer and grant `MINTER_ROLE` → full takeover. |
| **Engine keys** (`EVM_PRIVATE_KEY`, `CEX_PK`, wallet RPC) | engine host | Drains the engine's *own* inventory; not the user-custody wallet, but real funds. |
| **User custody** | implicit: deposited ZEPH not yet claimed; in-flight unwraps | Funds lost if claim expires, or paid to wrong destination, or double-spent. |
| **User privacy** | EVM↔Zephyr address map (`BridgeAccount`), per-address SSE/lookup | Deanonymization: links an EVM identity to a Zephyr (privacy-coin) address. |

---

## 2. Actors / attacker capabilities

| Actor | Can do | Cannot do (by design) |
|---|---|---|
| **Anonymous internet** | Hit any unauthenticated HTTP endpoint (`/unwraps/prepare`, `/bridge/address`, faucets, status, SSE); submit any EVM tx (claim with a held voucher, burn own tokens); read all on-chain state. | Forge a valid claim signature; assume `MINTER_ROLE`. |
| **A bridge user** | Everything anonymous can, plus: hold real deposits/vouchers, burn real wrapped tokens they own. | — |
| **Malicious LP / trader** | Manipulate Uniswap V4 pool prices; sandwich engine swaps. | — |
| **Compromised bridge-api** | Return arbitrary claim lists, prepared payloads, uniswap config, SSE events to the web app. | Sign a valid voucher *without* the signer key (but it usually *has* the signer key — see §3). |
| **Compromised bridge host** | Read the signer + wallet keys → game over for custody. | — |
| **Compromised engine host** | Drain engine inventory; cannot touch user custody (separate keys). | — |
| **Malicious operator (insider)** | Admin routes, key rotation, direct mint. | Out of scope for technical controls; mitigated by multisig (not yet implemented). |

---

## 3. Trust boundaries (the lines that matter)

```
                       ┌─────────────────────────────────────────────┐
   user's browser ───► │ bridge-web (Next.js, client-only, :7050)     │
   (MetaMask)          │  TRUSTS: bridge-api responses ALMOST FULLY   │  ◄── BOUNDARY A
                       └───────────────┬─────────────────────────────┘
                                       │ REST + SSE (no auth on most routes)
                       ┌───────────────▼─────────────────────────────┐
                       │ bridge-api (Hono, :7051)                     │
                       │  HOLDS: oracle signer key (BRIDGE_PK)        │  ◄── BOUNDARY B (crown jewel)
                       │  TRUSTS: chain-verified deposits (good);     │
                       │          client amount on /unwraps/prepare   │  ◄── BOUNDARY C (the CRIT-1 hole)
                       └───────┬───────────────────────┬─────────────┘
                               │                       │
            ┌──────────────────▼──┐        ┌───────────▼──────────────┐
            │ watcher-zephyr      │        │ watcher-evm              │
            │ (deposit finality)  │        │ (burn → payout relay)    │  ◄── BOUNDARY D (reorg/finality)
            └──────────┬──────────┘        └───────────┬──────────────┘
                       │                               │
        ┌──────────────▼──────────┐      ┌─────────────▼─────────────┐
        │ Zephyr daemon + wallet  │      │ EVM chain (Anvil/Sepolia) │
        │ (native custody)        │      │ wZEPH/wZSD/wZRS/wZYS       │
        └─────────────────────────┘      └───────────────────────────┘
```

**Boundary A — web ↔ api (the owner's stated worry).**
The web app is a *thin client* and structurally trusts bridge-api for almost everything that
matters. If bridge-api is honest, a third party cannot steal funds (signatures bind
amount/recipient/deadline; swap/burn are `simulateContract`-checked). **But the web app skips two
cheap verifications it could do**, so "API compromised" → instant user fund loss:
- it does not decode the unwrap burn payload to confirm the destination (HIGH-3);
- it does not pin swap/LP approval spenders against bundled config (HIGH-4).
**Hardening principle:** the web app should *verify everything it provably can* and never treat an
API response as authority for what the user signs.

**Boundary B — the signer key.**
`BRIDGE_PK` signing arbitrary claims is the single most dangerous capability in the system. Today it
is a hot key in env on the bridge host, with **no pause, no mint cap, no multisig, no rotation
runbook.** Compromise = unbounded unbacked mint. This is an *accepted but undocumented* risk; it must
become a *documented, mitigated* one before real value (see PLAN § Phase 3 and the key runbook).

**Boundary C — chain-verified vs client-supplied inputs (CRIT-1 lives here).**
The wrap path correctly trusts only **chain-verified** deposit data. The unwrap path **incorrectly
trusts a client-supplied amount** at `/unwraps/prepare` and never reconciles it against the actual
on-chain burn. This is the asymmetry that produced the critical drain. **Hardening principle:** every
value that moves money must be derived from, or reconciled against, authenticated on-chain data —
never from an unauthenticated request body.

**Boundary D — finality / reorg.**
Both watchers currently assume **instant finality** (0-conf burn→payout; no Zephyr reorg handling on
the wrap side after signing). Safe on Anvil (no reorgs), unsafe on any real chain. **Hardening
principle:** no irreversible payout before the triggering event is final at an agreed confirmation
depth.

---

## 4. Attack scenarios (ranked by expected loss)

1. **Unwrap drain (CRIT-1).** Anonymous; prepare-large + burn-dust; one pair of calls drains the hot
   wallet. *Status: fixed-in-branch, needs verification.*
2. **Signer/minter key compromise.** Host compromise or key leak → unbounded unbacked mint → pool
   drain. *Mitigation: none on-chain today (no pause/cap/multisig).*
3. **Reorg double-spend on real chains (HIGH-2).** Pay out on a burn that later reorgs out → ZEPH
   loss. *Status: open, devnet-masked.*
4. **API-compromise → user fund redirection (HIGH-3/4).** Malicious payload/spender → user signs away
   funds. *Status: open; cheap client-side fixes available.*
5. **Engine inventory drain via market manipulation (HIGH-5/6).** No armed risk controls + 0 slippage
   floor → sandwich/skew the pool, let the engine trade into it. *Status: open; engine is live-unsafe.*
6. **Debug-route DB wipe / user-map exfiltration (HIGH-1).** If dev flags are on in a reachable env.
   *Status: open.*
7. **Privacy deanonymization (LOW).** Unauthenticated per-address lookup + SSE. *Status: open;
   privacy not custody.*

---

## 5. Trust principles (apply these to every PR touching money)

1. **Money amounts come from authenticated on-chain data, never from unauthenticated request bodies.**
2. **No irreversible action before finality** (confirmation depth agreed per chain).
3. **The client verifies everything it provably can** before asking the user to sign.
4. **Every privileged capability is gated by a real auth token**, never a build-time/`NEXT_PUBLIC_*` flag.
5. **Single-key capabilities are documented risks with a written compromise runbook** until they're
   multisig/capped/pausable.
6. **Idempotency on every credit and every payout** — restart/replay must never double-act.
7. **Fail safe:** ambiguity or mismatch aborts the money-move; it never proceeds on a guess.

> If a change can't satisfy all seven for the path it touches, it is not ready for real value.
