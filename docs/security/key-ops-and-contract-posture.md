---
title: Contract Posture & Key-Ops — Single-Hot-Key Risk (decision doc)
status: DECISION-PENDING — written for owner to consider; not yet actioned
author: security review
date: 2026-06-10
audience: owner + engineers
---

# Contract Posture & Key Operations

You asked for detail on the single-hot-key contract risk so you can decide later. This is that
detail: what the risk *is*, what an attacker gains, the options with honest tradeoffs, and a
recommendation. **No contract changes have been made** — this is a decision input.

---

## 1. The risk, precisely

`ZephyrWrappedToken` (wZEPH/wZSD/wZRS/wZYS) has **three privileged capabilities and no brakes**:

| Capability | Held by | What it can do | Brake today |
|---|---|---|---|
| `MINTER_ROLE` → `mintFromZephyr(to, amount, txHash)` | operator/deployer key | Mint **any amount** of wrapped tokens to any address | **none** — no cap, no pause |
| `oracleSigner` (signs EIP-712 claim vouchers, `BRIDGE_PK`) | bridge-api host (hot) | Authorize **any** `claimWithSignature` mint | **none** — no cap, no pause |
| `DEFAULT_ADMIN_ROLE` | deployer key | Rotate the oracle signer, grant/revoke `MINTER_ROLE` | — |

Verified in `zephyr-eth-foundry/src/ZephyrWrappedToken.sol`: there is **no `Pausable`, no mint cap,
no timelock, no multisig** anywhere in the contract. Roles default to the **deployer key** if the
`ADMIN`/`MINTER`/`SIGNER` env vars are unset at deploy (`script/01_DeployZephyrTokens.sol:38-40`).

### What an attacker gains
Compromise of **either** the `MINTER_ROLE` key **or** the `oracleSigner` key (the latter is a *hot*
key living in env on the bridge-api host) →
**unbounded minting of unbacked wrapped tokens** → dump them into the Uniswap pools → drain all the
real liquidity (USDC/USDT and the bridge's own seeded inventory). There is **no on-chain action that
slows this down**; the only response is `setOracleSigner`/`revokeRole`, which the admin must execute
*faster than the attacker can mint and dump* — a race the defender usually loses.

This is the **single largest residual risk** for a real-value launch. It is more dangerous than
CRIT-1 was, because CRIT-1 was bounded by the hot-wallet balance, whereas unbacked mint is unbounded.

### Why the hot signer key makes this acute
The bridge MUST be able to sign claim vouchers automatically (that's the wrap UX), so `BRIDGE_PK`
*has* to be online. An online key is, eventually, an exposed key. The mitigations below are all about
**bounding the damage of an inevitable key exposure**, not pretending exposure won't happen.

---

## 2. Options (with honest tradeoffs)

### Option A — Pausable (emergency stop)
Add OpenZeppelin `Pausable`; gate `mintFromZephyr` + both claim paths on `whenNotPaused`; give a
`PAUSER_ROLE` to a key (or multisig) that can be triggered by monitoring/alerting.
- **Pros:** turns "unbounded loss" into "loss until someone hits pause"; cheap to add; standard.
- **Cons:** only as fast as your detection + human response; a pause key is itself a target (and a
  griefing vector if mis-held); doesn't help if the *pauser* path is what's compromised.
- **Effort:** small contract change + redeploy + tests.

### Option B — Per-epoch mint cap (rate limit)
Track minted-per-time-window in the contract; revert mints exceeding a configured cap per epoch.
- **Pros:** bounds loss *without* requiring human reaction — the protocol self-limits even if the key
  is fully compromised; composes with monitoring.
- **Cons:** must size the cap above legitimate peak throughput (too low → blocks real users; too high
  → weak protection); adds state/gas; legitimate spikes (large LP onboarding) can hit the cap.
- **Effort:** moderate contract change + careful cap calibration + tests.

### Option C — Multisig / threshold admin (and ideally signer)
Move `DEFAULT_ADMIN_ROLE` (and the pauser) to a multisig (e.g. Safe). Optionally move claim signing
to a threshold scheme so no single host holds a key that mints.
- **Pros:** removes the single-key admin takeover; multisig admin is table-stakes for real-value
  bridges. Threshold signing removes the single hot-key mint authority entirely.
- **Cons:** multisig admin doesn't stop a compromised *minter/signer* (it stops *takeover*, not
  *mint*); threshold signing is a real engineering lift (the bridge signer flow must become an
  MPC/threshold flow) and slows ops.
- **Effort:** multisig admin = low (deploy config). Threshold signer = large.

### Option D — Timelock on admin actions
Put a timelock on role grants / signer rotation so a compromised admin can't instantly self-grant
minter.
- **Pros:** buys reaction time against admin compromise.
- **Cons:** also slows *legitimate* emergency response (e.g. rotating a leaked signer) — tension with
  Option A's goal; doesn't bound minting at all.
- **Effort:** moderate.

### Option E — Accept + runbook (what you do for v1 only if you must move fast)
Keep current contracts; **write down** that minter+signer are single points of failure, keep the keys
on hardened/isolated hosts, add monitoring + alerting on mint volume, and have a rehearsed compromise
runbook (below). This is *risk acceptance*, not risk *mitigation*.
- **Pros:** zero contract work; fastest to launch.
- **Cons:** the loss ceiling is "everything"; only acceptable for low-value / short-lived testnet, or
  as an explicit, eyes-open bet. **Not advisable for mainnet with real liquidity.**

---

## 3. Recommendation

For **testnet-v2 (no real value, resettable):** Option E is acceptable *now* to keep moving, provided
the keys aren't reused anywhere with value and the runbook exists.

For **mainnet:** ship at minimum **A + B + multisig-admin (C-lite)** — Pausable for human response,
a per-epoch mint cap for autonomous bounding, and a multisig admin so no single key is takeover. This
is the conventional floor for a custodial bridge holding real liquidity. Threshold signing (full C) is
the gold standard but can be a fast-follow. **Do not launch mainnet on Option E alone.**

These are contract changes → they require a redeploy and address migration (the bridge config,
`addresses.json`, and the pools all reference the token addresses), so they must land *before* the
mainnet deploy, not after. Budget for it in the launch timeline.

---

## 4. Signer/Minter compromise runbook (write this regardless of option)

This must exist even under Option E. Draft procedure (operators should rehearse it):

1. **Detect.** Alert on: mint volume per window exceeding a threshold; any mint not matching a
   verified Zephyr deposit; pool price moving abnormally; admin role changes.
2. **Contain.**
   - If `Pausable` exists: **pause** all tokens immediately (`PAUSER_ROLE`).
   - Else: `setOracleSigner(<fresh address>)` to invalidate the leaked signer for *claim* mints, and
     `revokeRole(MINTER_ROLE, <compromised>)` for *operator* mints. (Admin key required — keep it
     offline/multisig so it isn't compromised in the same breach.)
3. **Assess.** Diff on-chain wrapped supply per asset vs the native Zephyr held by the bridge wallet
   (the 1:1 backing invariant, INV-1) to quantify unbacked mint.
4. **Stop the bleed downstream.** Pull bridge-provided liquidity if pools are being drained; halt the
   engine; freeze unwrap payouts (the watcher) so unbacked tokens can't also extract native ZEPH.
5. **Rotate everything.** New signer key, new minter key, new admin if implicated; redeploy if the
   keys can't be cleanly rotated.
6. **Post-mortem + user comms.** Reconcile balances; document; disclose.

Put the finalized version at `docs/security/incident-runbook.md` and rehearse it before mainnet.

---

## 5. Cross-references
- The backing invariant this protects: `INVARIANTS.md` INV-1.
- The trust boundary: `THREAT-MODEL.md` Boundary B (the signer key).
- Deploy-time single-key default: `FINDINGS.md` "Contract structural risks".
