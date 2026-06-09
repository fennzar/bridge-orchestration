---
title: Zephyr Protocol — Mega Reference
status: AUTHORITATIVE (protocol source-of-truth)
author: security review
date: 2026-06-10
audience: both (humans + agents)
provenance: protocol mechanics verified against the zephyr/ C++ source on 2026-06-10; history/lineage
  cross-checked against the whitepaper + GitHub releases (web). Every load-bearing claim is tagged.
---

# Zephyr Protocol — Mega Reference

The single deep reference for **what Zephyr is, how it works, and how the bridge sits on top of it.**
If you only need the bridge-relevant minimum, read [`zephyr-primer.md`](./zephyr-primer.md) instead;
this is the exhaustive version. For the wrap/unwrap protocol itself, see
[`bridge-protocol.md`](./bridge-protocol.md).

> **Source legend.** Claims are tagged by how they were verified:
> - **`[code]`** — confirmed in the `zephyr/` C++ source on 2026-06-10 (`file:line` cited). Ground truth.
> - **`[web]`** — from the whitepaper / GitHub releases / official posts (citations in §12). Reliable but secondary.
> - **`[⚠️]`** — unverified or could not be confirmed against a primary source; treat as provisional.
>
> Where `[web]` and `[code]` agree, the figure is doubly grounded and noted as such. **Code wins on conflict.**

---

## 1. What Zephyr is

Zephyr Protocol (**ZEPH**) is a **privacy-preserving, over-collateralized algorithmic stablecoin
system**: a **Monero fork** (privacy base) that implements the **Minimal Djed** stablecoin protocol
on-chain, so every asset inherits Monero's ring signatures, stealth addresses, and RingCT/Bulletproofs. `[web]`

- **Lineage.** Monero (CryptoNote, RandomX PoW) for the privacy/UTXO base; **Minimal Djed** (Emurgo/IOG,
  formally verified in eprint 2021/1069) for the over-collateralized stablecoin mechanics. The whitepaper
  positions Zephyr explicitly against **Haven Protocol (xUSD/XHV)** — the earlier Monero-fork stablecoin
  that died via unlimited minting — and over-collateralization is the deliberate fix. `[web]`
- **Timeline.** Mainnet launched **2023-05-29**; the stablecoin protocol activated at a hardfork on
  **2023-10-01**. `[web]`
- **Money unit.** `COIN = 10^12` — **12 decimals**, one trillion atomic units per whole coin
  (`cryptonote_config.h:69`). `[code]` This is the number that makes the bridge's `decimals()==12` wrapped
  tokens line up 1:1 with native atomic units.
- **Block time.** `DIFFICULTY_TARGET_V2 = 120` seconds (`cryptonote_config.h:82`). `[code]`
- **PoW / supply.** RandomX (CPU). Total supply ≈ **18.4M ZEPH + 0.6 ZEPH/block tail emission**; emission
  speed factor 21 (`cryptonote_config.h:57`, `MONEY_SUPPLY=(uint64_t)(-1)` with a tail subsidy floor). `[web]`+`[code]`
- **Team.** Effectively pseudonymous; not disclosed in primary docs. `[⚠️]`

### Why this matters for the bridge
Zephyr is a **UTXO / CryptoNote** chain, not account-based. Payouts select inputs + ring members and carry
**unlock times**; outputs mature before they're spendable. So "instant finality" assumptions are wrong, and
a transaction pre-signed long before broadcast can become invalid. Privacy also means the bridge identifies
deposits via **wallet RPC**, not block scanning. (See §8 and the finality invariants INV-11/12.)

---

## 2. Native assets

A **four-asset** model, differentiated on-chain by an `asset_type` string. Zephyr went through a naming
generation; **never mix V1 and V2 in a single conversion** — the daemon rejects it as an invalid tx type. `[code]`

| Role | V1 `asset_type` | V2 `asset_type` | Priced by | Notes |
|---|---|---|---|---|
| **Base coin / collateral** | `ZEPH` | `ZPH` | market; oracle for USD | The reserve asset. Mint/redeem moves ZEPH **into/out of the reserve**; it is never spontaneously created by stablecoin ops. |
| **Stable dollar** | `ZEPHUSD` | `ZSD` | **oracle** (spot + MA) | USD-pegged, over-collateralized by ZEPH. |
| **Reserve share** | `ZEPHRSV` | `ZRS` | **reserve formula** | Equity coin: leveraged ZEPH exposure + accrued mint/redeem fees. Priced off reserve state, *not* the oracle. |
| **Yield share** | `ZYIELD` | `ZYS` | yield-reserve formula | Share of the ZSD Yield Reserve. Stake ZSD → get ZYS (see §7). |

The current stack runs **V2** (`ZPH/ZSD/ZRS/ZYS`). Wrapped EVM tokens are `wZEPH/wZSD/wZRS/wZYS` (the `wZEPH`
ticker wraps the base coin regardless of V1/V2 naming).

### The V1→V2 rename was a security event, not cosmetics
The on-chain `asset_type` strings were renamed (ZEPH→ZPH, etc.) at **HF11 (block 536000)** to **separate
audited from unaudited supply** after the 2024–25 reconciliation (see §9). Post-HF11, old asset types are
invalid. `[code]`+`[web]` **Integration consequence:** a deposit watcher must match `asset_type` **exactly**
(`ZPH`/`ZSD`/`ZRS`/`ZYS`) or it will miscredit one asset as another — exactly the class of bug that the
bridge's INV-5 (asset-type integrity) guards against.

---

## 3. The Djed reserve system

Zephyr is an autonomous on-chain bank. Users **mint** ZSD by locking ZEPH into a shared **reserve** and
**redeem** ZSD back for ZEPH; ZRS holders provide/withdraw reserve equity. Mint/redeem **fees accrue to the
reserve** (i.e. to ZRS holders), structurally reinforcing over-collateralization. `[web]`

The **reserve ratio (RR)** = assets / liabilities = `(zeph_reserve × oracle_price) / num_stables`. It is the
global, price-dependent gate on which conversions are allowed *right now*.

### The exact enforcement gates `[code]`
From `reserve_ratio_satisfied()` in `cryptonote_core/cryptonote_tx_utils.cpp:748-894` (HF_VERSION_V5+):

```
const uint64_t RESERVE_RATIO_MIN = 4 * COIN;   // 400%   (line ~834)
const uint64_t RESERVE_RATIO_MAX = 8 * COIN;   // 800%   (line ~835)
```

| Conversion | tx_type | Gate (BOTH spot AND moving-average must pass) |
|---|---|---|
| ZEPH → ZSD | `MINT_STABLE` | RR_spot ≥ 400% **and** RR_MA ≥ 400% — else **blocked** |
| ZSD → ZEPH | `REDEEM_STABLE` | allowed as long as reserve assets > 0 (no RR floor beyond that) |
| ZEPH → ZRS | `MINT_RESERVE` | RR_spot < 800% **and** RR_MA < 800% — else **blocked** (bootstrap exception: allowed if circulating ZSD < 100) |
| ZRS → ZEPH | `REDEEM_RESERVE` | RR_spot ≥ 400% **and** RR_MA ≥ 400% — else **blocked** |
| ZSD ⇄ ZYS | `MINT_YIELD`/`REDEEM_YIELD` | not gated by this function (returns true; yield has its own brake, §7) |

So: **the 400% floor gates ZSD minting and ZRS redemption; the 800% ceiling gates ZRS minting.** Below 100% the
whitepaper notes ZSD redeems for its pro-rata share of the reserve rather than face value. `[web]`

### Zephyr's deviation from canonical Djed — dual reserve ratio
Every gate above checks **both** the **spot** RR and the **720-record moving-average** RR, and requires both to
pass (`reserve_ratio_satisfied` computes `reserve_ratio_spot` and `reserve_ratio_MA`; `get_moving_average_reserve_ratio`
averages over 720 records, `cryptonote_tx_utils.cpp:1184`). `[code]` Canonical Djed uses a single oracle price;
Zephyr's two-price requirement is an explicit anti-manipulation measure (you can't pump or dump a single block's
price to unlock a conversion). `[web]`

### Why this is the #1 fact for the engine
**Conversion availability changes with price.** A plan built when RR = 450% can become invalid before it executes
if RR crosses 400% (price drop) — or a ZRS mint can blow through the 800% ceiling. The engine models this as
`rrMode`; it **must re-check RR at execution time**, not just at planning time (FINDINGS MED-7, INV-15). This is
the heart of the "engine ↔ Zephyr market-dynamics interplay" the owner flagged as launch-critical.

---

## 4. Conversion pricing & fees `[code]`

The price used for a conversion deliberately disadvantages the converter, via a **spot-vs-moving-average band**,
and then a protocol fee is subtracted. All confirmed in `cryptonote_tx_utils.cpp`:

| Conversion | Function (line) | Price used | Fee (HF_VERSION_V5+) | Fee (pre-V5) |
|---|---|---|---|---|
| ZEPH → ZSD | `zeph_to_zephusd` (1244) | `max(stable, stable_ma)` | **0.1%** (`/1000`) | 2% |
| ZSD → ZEPH | `zephusd_to_zeph` (1274) | `min(stable, stable_ma)` | **0.1%** | 2% |
| ZEPH → ZRS | `zeph_to_zephrsv` (1189) | `max(reserve, reserve_ma)` | **1%** (`/100`) | 0% |
| ZRS → ZEPH | `zephrsv_to_zeph` (1219) | `min(reserve, reserve_ma)` | **1%** | 2% |
| ZSD → ZYS | `zephusd_to_zyield` (1300) | `yield_price` | **0.1%** | — |
| ZYS → ZSD | `zyield_to_zephusd` (1325) | `yield_price` | **0.1%** | — |

**The rule:** minting an asset prices at **MAX(spot, MA)** (you get fewer of it); redeeming prices at
**MIN(spot, MA)** (you get fewer ZEPH back). The band + fee is the protocol's edge and the reason naive
spot-priced arb math overstates profit.

### Engine gap to know
The engine **computes** this band but its *executing* path has historically priced at bare **spot with fee=0**
(FINDINGS MED-8 / INV-14). That overstates arb edge and can plan conversions that the daemon prices worse than
expected. Any "the arb was profitable" claim from the engine must be validated against these exact functions.

---

## 5. Oracle & pricing records

ZEPH/USD enters consensus through a **signed pricing record** carrying both a **spot** price and a **moving
average**. `[web]`

- **Mechanism.** When a miner mines a block it fetches the oracle response and embeds a **pricing record**
  into the block; the signature is verified as the block is added and re-verified by other nodes as part of
  consensus. This is a **centralized/federated signed feed** (a trusted key signs the price) — *not*
  decentralized. A "v2" decentralized oracle is described as future work. `[web]` `[⚠️]` current v2 status.
- **Staleness window `[code]`** (`cryptonote_config.h:215-216`):
  - `PRICING_RECORD_VALID_BLOCKS = 10` — a pricing record is valid within 10 blocks.
  - `PRICING_RECORD_VALID_TIME_DIFF_FROM_BLOCK = 120` seconds — and within 120s of the block timestamp
    (enforced in `oracle/pricing_record.cpp:282`).
- **Pricing-record fields** (the daemon's `get_reserve_info` → `ReservePriceReport`, all atomic 1e12):
  `spot` (ZEPH/USD), `moving_average`, `stable` / `stable_ma` (ZSD), `reserve` / `reserve_ma` (ZRS),
  `yield_price` (ZYS), `reserve_ratio` / `reserve_ratio_ma`.
- **Trust note.** The signed oracle is the protocol's central trust assumption: a compromised feed can move
  reserve ratios, unlock or block conversions, and depeg ZSD. Djed-family analysis calls this out explicitly. `[web]`

### Devnet caveat
The dev/testnet stack runs a **controllable fake oracle** (`make set-price PRICE=<usd>`). Great for testing
protocol logic, but it masks real confirmation latency and reorgs — the two things that actually break bridges.
"It works on devnet" is **not** evidence of finality/reorg safety on Sepolia/mainnet.

---

## 6. Reserve ratio + price → conversion availability (the engine's world model)

Putting §3–§5 together, the state the engine must track each cycle:

1. Read `get_reserve_info` → current `reserve_ratio` and `reserve_ratio_ma`.
2. Derive `rrMode`: which conversions are open (ZSD mint open iff both RRs ≥ 400%; ZRS mint open iff both <
   800%; ZSD/ZRS redemption per the table in §3).
3. Price any planned conversion with the **band + fee** from §4 — never bare spot.
4. **Re-validate at execution time** — both RR gates and the prices can move between plan and broadcast.
5. Respect the **pricing-record staleness window** — a plan built against a record about to expire can fail.

This is precisely where the "stable market + minting/redeeming rules" difficulty the owner called out lives:
the wZEPH market is a simple AMM, but ZSD's availability is **gated by a global, price-reflexive ratio** that
the engine doesn't control and must continuously respect.

---

## 7. Yield (ZYS) `[code]`+`[web]`

Introduced at **HF_VERSION_V6 (block 360000, ~2024-10-13)** (`hardforks.cpp:41`). Users stake **ZSD → ZYS**, a
native asset representing a share of the growing **ZSD Yield Reserve**; redeemable anytime (no lockup). `[web]`

- **Funding.** A slice of the block reward mints new ZSD into the yield reserve; ZYS appreciates as the reserve
  grows (`get_zeph_yield_reward`, `blockchain.cpp:4890`). The v2.0.0 reward split is reported as
  Miner 65% / Reserve 30% / ZSD-Yield 5% / Governance 0%. `[web]`
- **Reserve discipline.** Reported **7:1** — for every 1 ZSD minted as yield, ~7 ZEPH added to the reserve
  (normalizes RR toward 700%). `[web]`
- **Safety brake `[code]` (this one the web flagged unverified — now confirmed).**
  `blockchain.cpp:4895-4897`:
  ```
  const uint64_t YIELD_RSV_MIN = 2 * COIN; // 200%
  if (reserve_ratio > YIELD_RSV_MIN && reserve_ratio_ma > YIELD_RSV_MIN) { /* mint yield reward */ }
  ```
  → **yield reward minting halts when either the spot OR the MA reserve ratio drops to/below 200%.** ZYS
  conversions themselves (`MINT_YIELD`/`REDEEM_YIELD`) are not RR-gated; it is the *block-reward yield accrual*
  that stops.

---

## 8. Privacy & UTXO mechanics the bridge must respect `[code]`

| Fact | Value | Source | Bridge consequence |
|---|---|---|---|
| Atomic unit | `COIN = 10^12` (12 decimals) | `cryptonote_config.h:69` | 1:1 with wrapped `decimals()==12`; the `amountWei` field is a misnomer |
| Block time | 120 s | `cryptonote_config.h:82` | confirmation latency is real on mainnet |
| Coinbase maturity | 60 blocks | `CRYPTONOTE_MINED_MONEY_UNLOCK_WINDOW`, `:45` | freshly mined ZEPH unspendable for ~60 blocks (devnet warm-up mines past this) |
| Normal output spendable age | 10 blocks | `CRYPTONOTE_DEFAULT_TX_SPENDABLE_AGE`, `:51` | a payout's change/inputs have lock periods → pre-signing long before broadcast risks `tx_rejected` (FINDINGS HIGH-8) |
| Mempool tx lifetime | 3 days | `cryptonote_config.h:105` | a stuck prepared payout eventually drops |

Other hard-won wallet-RPC facts (see `../reference/zephyr-tips.md`):
- **`get_balance` needs `all_assets:true`** to return ZSD/ZRS/ZYS — without it you only get ZPH.
- **Wallet `get_height`/`get_transfers` are stale** — they track the wallet's internal refresh, not the chain
  tip. For true finality the watcher must read the **daemon** `get_info` (INV-13).
- Transfers/conversions are private, but **mint/redeem/reserve amounts are revealed on-chain** for consensus
  reserve accounting — so wrap/unwrap ZEPH amounts are visible while the spending output set is not. `[web]`

---

## 9. Hardfork timeline & the 2024–25 Supply Integrity Audit `[code]`+`[web]`

Mainnet hardforks (`hardforks.cpp:34-47`, block heights are `[code]`; dates `[web]`):

| HF | Block | ~Date | What |
|---|---|---|---|
| v6 | 360000 | 2024-10-13 | **ZSD Yield** (ZYS) introduced (§7) |
| v8 | 481500 | 2025-03-31 | **Supply Integrity Audit** opened (`AUDIT_FORK_HEIGHT`, `cryptonote_config.h:185`) |
| v10 | (HF10) | 2025-05 | audit migration stage `[web]` |
| v11 | 536000 | 2025-06-15 | **V11**: audited asset-type rename (ZEPH→ZPH …) + one-time reconciliation mint (`HF_VERSION_V11_FORK_HEIGHT`, `:186`) |

### The incident (real, disclosed)
Suspicious historical transactions were found in late 2024 (after exploits on other Monero-fork stablecoins),
and exchange deposits were paused. `[web]` Two findings: (1) a **cross-asset "morphing" ring-member bug** —
pre-v2.0.2 consensus didn't strictly enforce that ring members match the spending output's `asset_type`,
letting modified wallets spend e.g. ZSD/ZRS as ZEPH (~30 transactions, bounded amount morphed ~1:1 into ZEPH);
(2) range-proof anomalies on a few historical txs. The staged hardforks (v8→v11) audited the chain and
invalidated unaudited coins. `[web]`

### The reconciliation mint — code-confirmed
Because a custodial exchange (MEXC) couldn't audit its full balance in time, HF11 included a **one-time mint** to
reconcile it. The web postmortem (paywalled) reported "1,921,650 ZEPH" as `[⚠️]`; **this is now confirmed in
code**: `cryptonote_config.h:194`
```
#define UNAUDITABLE_ZEPH_AMOUNT  ((uint64_t)1921650000000000000) // 1,921,650 ZEPH
```
added to `base_reward` exactly at `V11_HEIGHT` (`blockchain.cpp:4902-4903`). (A `DEVNET_MIRROR_SUPPLY` build
uses ~11.16M to mirror mainnet circulating supply, `:192`.)

**Why this matters for the bridge.** The morphing bug is the canonical example of why **asset-type integrity is
a money-critical invariant** (INV-5): on a chain where a consensus bug once let one asset masquerade as another,
the bridge must never default an unknown/missing `asset_type` to `ZEPH`. The chain's own history is the argument
for the bridge's strictest input validation.

---

## 10. How the bridge is designed

Full spec: [`bridge-protocol.md`](./bridge-protocol.md). Summary of the trust model:

The bridge is **custodial**. It holds native Zephyr in a hot wallet and mints/burns EVM representations 1:1.
Two flows:

- **Wrap (ZEPH → wZEPH).** User sends native ZEPH to a bridge-controlled subaddress. The **watcher-zephyr**
  detects the deposit (via wallet RPC, using the **daemon** tip for finality). The bridge signs an **EIP-712
  claim voucher** (`Claim(address to,uint256 amount,bytes32 zephyrTxHash,uint256 deadline)`, domain
  `EIP712("ZephyrClaims","1")`), and the user calls `claimWithSignature(...)` to mint wZEPH. Replay is blocked
  per-token by `usedZephyrTx[zephyrTxHash]`, and the operator `mintFromZephyr` path **shares the same replay
  namespace** so a deposit can be minted at most once total. (Proven by the forge suite in
  `zephyr-eth-foundry/test/ZephyrWrappedToken.t.sol`.)
- **Unwrap (wZEPH → ZEPH).** User calls `burnWithData(amount, zephDestination, nonce)` on the token. The
  **watcher-evm** observes `Burned`, and the bridge relays a native ZEPH payout. Burn replay is blocked per
  `usedNonce[msg.sender][nonce]`. The payout **amount is bound to the burned amount** (CRIT-1 fix in
  `packages/bridge/src/unwraps/ingest.ts`) so a burn cannot extract more native ZEPH than was destroyed.

**The 1:1 backing invariant (INV-1)** — circulating wrapped supply per asset ≤ native ZEPH held by the bridge —
is the property everything else protects. The contract has **no mint cap, pause, or multisig** today; the
single-hot-key risk and options are in [`../security/key-ops-and-contract-posture.md`](../security/key-ops-and-contract-posture.md).

### Integration gotchas (for anyone building on Zephyr)
- Match `asset_type` **exactly** post-HF11: base coin is **`ZPH`**, not `ZEPH`. (§2)
- Atomic unit = **1e12**; never assume 18 decimals. (§1, §8)
- Mint/redeem/reserve amounts are **publicly revealed** on-chain even though transfers are private. (§8)
- Conversion availability is **price-reflexive** via the 400/800/200% gates — not constant. (§3, §6)
- Use the **daemon** for chain tip/finality; wallet height is stale. (§8)

### Bridge status (web)
An official EVM bridge effort wraps **ZSD** (yield-accruing) onto EVM chains (ETH/Polygon/Arbitrum/Base),
lock-on-Zephyr → mint-on-EVM, currently **testnet** (`testnet-bridge.zephyrprotocol.com`); a Cross-Chain Bridge
Proposal exists (2025-09-25). `[web]` `[⚠️]` exact proposal contents (JS-rendered, not fetched). *This repo's
bridge is its own implementation — treat the official effort as related context, not a spec.*

---

## 11. Known risks & trust assumptions

| Risk | Class | Notes |
|---|---|---|
| **Centralized signed oracle** | protocol | Single trusted signer for ZEPH/USD; compromise → depeg / reserve manipulation. v2 decentralized oracle is future work. `[web]` |
| **Reflexive collateral** | protocol | ZEPH collateralizes its own stablecoins; a severe ZEPH crash stresses the reserve (Minimal Djed mitigates, doesn't eliminate, the death-spiral class). `[web]` |
| **Capital inefficiency** | protocol | The 400% floor locks large collateral; whitepaper lists this as an explicit limitation. `[web]` |
| **Redemption crunch** | protocol | In extremes, ZSD redemption value can be impaired before ZEPH recovers / reserve refills. `[web]` |
| **Consensus history** | protocol | The morphing bug (§9) is fixed, but it's the reason asset-type strictness is non-negotiable. `[code]` |
| **Single hot key (mint/signer)** | bridge | Unbounded unbacked-mint risk; no on-chain brake. See key-ops doc. |

---

## 12. Sources

**Code (zephyr/, verified 2026-06-10):**
- `src/cryptonote_config.h` — `COIN` (:69), block time (:82), MA window (:84), maturity/spendable-age (:45,:51),
  pricing-record validity (:215-216), HF heights (:184-186), `UNAUDITABLE_ZEPH_AMOUNT` (:192,:194).
- `src/cryptonote_core/cryptonote_tx_utils.cpp` — `reserve_ratio_satisfied` 400/800% gates (:748-894),
  conversion pricing + fees (:1189-1348), MA reserve ratio /720 (:1184).
- `src/cryptonote_core/blockchain.cpp` — yield reward + `YIELD_RSV_MIN = 2*COIN` 200% halt (:4890-4903).
- `src/hardforks/hardforks.cpp` — mainnet HF schedule (:34-47).
- `src/oracle/pricing_record.cpp` — pricing-record block validation (:282).

**Web (secondary; see the research briefing for the full annotated list):**
- Zephyr whitepaper (2023-06-05) — Djed mechanics, 400/800% bounds, dual-ratio anti-manipulation, Haven comparison.
- GitHub releases — hardfork/version timeline + block-reward split.
- Official posts / X postmortem (2025) — Supply Integrity Audit, morphing bug, MEXC reconciliation (figure
  now code-confirmed in §9).
- `eprint.iacr.org/2021/1069` — "Djed: A Formally Verified Crypto-Backed Pegged Algorithmic Stablecoin."

---

## See also
- [`zephyr-primer.md`](./zephyr-primer.md) — the bridge-engineer minimum (start here if short on time).
- [`bridge-protocol.md`](./bridge-protocol.md) — the wrap/claim/unwrap protocol spec.
- [`../security/INVARIANTS.md`](../security/INVARIANTS.md) — the money-critical invariants these facts protect.
- [`../security/THREAT-MODEL.md`](../security/THREAT-MODEL.md) — trust boundaries.
- `zephyr/README.md` — the protocol's own description.
