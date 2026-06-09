---
title: Zephyr Protocol Primer (for bridge engineers)
status: reference
author: security review, grounded in zephyr/README.md + code
date: 2026-06-10
audience: both (humans + agents)
note: protocol facts grounded in zephyr/README.md; bridge-specific facts cited to code
---

# Zephyr Protocol Primer

You do not need to understand all of Zephyr to work on the bridge — but the bridge's correctness
*depends* on a few protocol facts. This is the minimum mental model, with the bits that matter to
the bridge and the engine flagged. For depth, read `zephyr/README.md` (the protocol's own doc).

---

## 1. What Zephyr is

A **Monero fork** (privacy via ring signatures + stealth addresses) that adds an **over-collateralized
algorithmic stablecoin system** based on the **Minimal Djed** protocol (the same family as Cardano's
Djed). It is a privacy coin *and* a stablecoin platform in one chain.

Consequences for the bridge:
- **Privacy primitives apply:** deposits arrive at **subaddresses**; amounts and senders are not
  trivially linkable on-chain. The bridge identifies deposits via wallet RPC, not block scanning.
- **It's a UTXO/CryptoNote chain**, not account-based: payouts select inputs/ring members and have
  **unlock times** (coinbase maturity ~60 blocks; spends have lock periods). This is why pre-signed
  transactions can become invalid and why "instant finality" assumptions are wrong (see bridge
  finality issues, INV-11).

## 2. The assets

Zephyr has gone through a naming generation. **Never mix V1 and V2** in a conversion — the daemon
rejects it as an invalid tx type.

| Role | V1 name | V2 name | Priced by |
|---|---|---|---|
| Base coin | `ZEPH` | `ZPH` | market (and the oracle for USD) |
| Stable dollar | `ZEPHUSD` | `ZSD` | **oracle** (targets ~$1) |
| Reserve share | `ZEPHRSV` | `ZRS` | **reserve formula** (equity ÷ supply) |
| Yield | `ZYIELD` | `ZYS` | reserve/yield formula |

The current stack runs **V2** (`ZPH/ZSD/ZRS/ZYS`). The wrapped EVM tokens are `wZEPH/wZSD/wZRS/wZYS`
(the `wZEPH` ticker wraps the base coin regardless of V1/V2 naming).

## 3. The Djed reserve system (why conversions are gated)

Users **mint** or **redeem** ZSD/ZRS in exchange for the base coin. Minting adds base coin (+fee) to
a shared **reserve** that collateralizes all stablecoins. Two ratios bound the system:

- **Minimum 400% collateralization.** If the reserve ratio (RR) falls below 400% (e.g. ZEPH price
  drops), **new ZSD cannot be minted** — but ZRS gets cheaper, incentivizing reserve top-up.
- **Maximum 800% reserve ratio.** Caps ZRS dilution.

The **reserve ratio is a global, price-dependent gate on what conversions are allowed at any moment.**
The engine models this as `rrMode`. This is the single most important market-dynamic fact for the
engine: *conversion availability changes with price*, so a plan built when RR=450% can become
invalid before it executes if RR crosses 400%.

### Pricing nuances the engine must respect
- **Oracle prices the stable side**; a **reserve formula** prices ZRS. Both come from the daemon
  (`get_reserve_info` → `ReservePriceReport`).
- The daemon reports prices in **atomic units (1e12)**. Fields (per bridge notes, verify against
  daemon): `spot` (ZEPH), `stable` (ZSD), `reserve` (ZRS), `yield_price` (ZYS).
- Mint/redeem use a **spot-vs-moving-average spread**: conceptually `mint ≈ MAX(spot, MA)` and
  `redeem ≈ MIN(spot, MA)` — a protection band. **The engine computes this but its *executing* path
  prices at spot** (FINDINGS MED-8 / INV-14) — a known gap that overstates arb edge.
- Conversions carry **protocol fees** (bridge notes ZSD:10bps, ZRS:100bps, ZYS:10bps — verify
  against daemon; the executing engine path passes fee=0, another gap).

## 4. What the bridge relies on (the protocol contract)

The bridge is **custodial**: it holds native Zephyr in a hot wallet and mints/burns EVM
representations 1:1. For that to be safe, these protocol facts must hold:

1. **A deposit is final after N confirmations** and won't reorg out. The wrap watcher must use the
   **daemon** chain tip (`get_info`), because the **wallet RPC `get_height`/`get_transfers` return
   stale values** (verified gotcha — see `docs/reference/zephyr-tips.md`).
2. **Amounts are 12-decimal atomic units** on both sides → 1:1 with the wrapped token (`decimals()==12`).
3. **A native payout (unwrap) is a real spend** with unlock/ring constraints → pre-signing it long
   before broadcast risks `tx_rejected` (verified flake — FINDINGS HIGH-8).
4. **`get_balance` needs `all_assets:true`** to return ZSD/ZRS/ZYS, not just ZPH.

## 5. Devnet vs reality

The dev/testnet stack runs **DEVNET mode**: fresh genesis, a **controllable fake oracle**
(`make set-price PRICE=<usd>`), instant-ish mining, fast resets. This is excellent for testing
protocol *logic* but **masks the two things that break bridges**: real confirmation latency and
chain reorgs. Any "it works on devnet" claim about finality, payout timing, or reorg safety is
**not** evidence it works on a real chain (Sepolia/mainnet). See the finality invariants (INV-11/12).

---

## See also
- `bridge-protocol.md` — how the bridge wraps these assets (the EIP-712 + burn-payload spec).
- `../security/THREAT-MODEL.md` — the trust boundaries this primer's facts protect.
- `zephyr/README.md` — the protocol's own (authoritative) description.
- `../reference/zephyr-tips.md` — hands-on wallet/RPC gotchas.
