---
title: Bridge Stress-Test Runbook (testnet-v2 / live stack)
status: AUTHORITATIVE (runnable procedure)
author: security review
date: 2026-06-10
audience: operator + engineers
---

# Bridge Stress-Test Runbook

The concrete, runnable version of [hardening plan §Phase 6](../plans/bridge-hardening.md). Each leg
states **what it proves** (which invariant), **how to run it**, and **the pass condition**. Run order
is A→D; A and D need a live stack, B and C are mostly automated.

> **Grounding rule:** visible/stateful behavior must be verified in real Chrome —
> typecheck + unit tests do not catch GPU/WebGL/runtime issues. Use the `chrome-debug` skill for the
> browser legs. Record every run's results in `reports/` and update
> [`INVARIANTS.md`](./INVARIANTS.md) ledger rows.

---

## Preconditions

```bash
make dev                       # infra + apps (or: make dev-setup then make dev if first run)
make status                    # confirm services are up
```

- Bridge API on `:7051`, web on `:7050`, engine on `:7000`, Anvil `:8545`, Zephyr nodes up.
- A funded EVM test wallet in MetaMask (see `docs/METAMASK-SETUP.md`; fund from the Anvil deployer key).
- For the **prepare-cap** sub-test (Leg B), set on the API host before starting it:
  `UNWRAP_MAX_AMOUNT_WEI=<atomic cap>` (e.g. a per-tx ceiling). Unset = cap test is informational only.
- DEVNET masks real finality/reorgs (see [`../protocol/zephyr-primer.md`](../protocol/zephyr-primer.md) §5);
  the finality legs (INV-11/12/13) must ultimately be repeated on **Sepolia (testnet-v3)**, not just devnet.

---

## Leg A — Functional E2E (real Chrome)

**Proves:** the happy paths still work end-to-end *and* the CRIT-1 attack is blocked (INV-1/3/4/5).

Attach with `chrome-debug` (CDP :9222), then through the web UI (`:7050`):

1. **Wrap → claim.** Send native ZEPH to the bridge subaddress; confirm the deposit is detected, a
   claim voucher appears, `claimWithSignature` mints wZEPH 1:1. ✅ when wZEPH balance == deposited atomic.
2. **Unwrap (honest).** Burn wZEPH via `burnWithData`; confirm native ZEPH is paid out to the
   destination and the record reaches `complete` (watch for the INV-13 "stuck pending" UX bug).
3. **Swap + LP.** Execute a swap and an LP add/remove (these exercise the Permit2 two-step approval —
   see memory `lp-add-liquidity-permit2`).

### A.x — The CRIT-1 attack (MUST be blocked) 🔴

This is the crown-jewel test. It proves the unwrap payout is bound to the *burned* amount, not the
*prepared* amount (INV-3). Manual, needs `cast` + the funded wallet:

```bash
# 1. Prepare a LARGE payout (unauthenticated route) — capture draftId + payload + txHash
curl -s -X POST localhost:7051/unwraps/prepare \
  -H 'content-type: application/json' \
  -d '{"token":"<wZEPH addr>","destination":"<your ZPH addr>","amountWei":"100000000000000"}'   # 100 ZEPH

# 2. Burn only DUST against that same payload+nonce on the token contract
cast send <wZEPH addr> "burnWithData(uint256,bytes,bytes32)" 1 <payload> <nonce> \
  --private-key <funded key> --rpc-url localhost:8545                                              # 0.000000000001 ZEPH
```

**Pass condition:** the bridge **does NOT** pay out the prepared 100 ZEPH. The watcher relay throws
`unwrap relay blocked: burned … < prepared …` (the `burnCoversPayout` guard in
`packages/bridge/src/unwraps/ingest.ts`), the draft rolls back, and the destination receives **nothing**
beyond the dust's worth (or nothing at all). **Fail** = any payout larger than the dust burn.

---

## Leg B — Adversarial API (automated)

**Proves:** the unauthenticated surface rejects hostile input (INV-18/19). These are the
`ZB-SEC-013..017` adversarial probes, which now live in the scenario security suite
(`tests/scenario/security/test_unwrap_prepare.py`, `test_privileged_routes.py`).

```bash
make test-scenario SUITE=security                    # runs the adversarial /prepare + route-auth probes
```

| Check | Attack | Pass |
|---|---|---|
| ZB-SEC-013 | `/unwraps/prepare` amountWei=0 | HTTP 400 |
| ZB-SEC-014 | non-numeric / negative amount | HTTP 400 |
| ZB-SEC-015 | malformed Zephyr destination | no payout draft (non-200) |
| ZB-SEC-016 | missing token / destination | HTTP 400 |
| ZB-SEC-017 | GET `/reset/database`, `/debug/*`, `/admin/reset` | none return 200 |

**Manual extras** (not yet automated — do by hand or extend the suite):
- Point the **web** at a mock API returning a hostile burn payload / spender address — HIGH-3/4 client
  decode + spender-pin must block (INV: Boundary A). Needs the web-side decode fix (PLAN 2.2/2.3) first.
- Double-claim the same voucher twice — second must fail (`usedZephyrTx`, proven in the forge suite).
- Replay a stale SSE stream — must not produce a duplicate record.

**Pass condition:** every `ZB-SEC-013..017` is `PASS` (not `BLOCKED` — that means the stack was down).

---

## Leg C — Load / DoS

**Proves:** the bridge degrades gracefully under contention; no Postgres connection exhaustion or
input-contention drain (MED cluster).

```bash
make test-edge-stress                                # L5.5 — LOAD + TIME + PRIV
# ad-hoc prepare spam (input contention on the unauthenticated route):
seq 1 200 | xargs -P20 -I{} curl -s -X POST localhost:7051/unwraps/prepare \
  -H 'content-type: application/json' \
  -d '{"token":"<wZEPH addr>","destination":"<ZPH addr>","amountWei":"1000000000000"}' >/dev/null
```

Also: open many concurrent SSE subscribers (`/unwraps/:from/stream`) and watch Postgres connection
count; fire rapid claim/burn cycles.

**Pass condition:** API stays responsive, no 5xx storm, no unbounded wallet-input commitment from
prepare spam (this is *why* `UNWRAP_MAX_AMOUNT_WEI` + the eventual prepare-auth fix matter — PLAN 1.1).

---

## Leg D — Deployment dry-run

**Proves:** a fresh deploy is locked down (INV-18, config hygiene).

```bash
make dev-reset-hard && make dev-setup && make dev     # rebuild from a clean post-init state
```

Then verify on the running stack:
- **Dev flags OFF:** no `NEXT_PUBLIC_*` debug/reset toggles enabled on the testnet host.
- **CORS not `*`** on the API.
- **No debug routes reachable** (re-run ZB-SEC-017).
- **Secrets not exposed:** `BRIDGE_PK`, `CEX_PK` not visible in `ps aux` / Procfile command strings /
  logs (MED-9). Check: `ps aux | grep -E 'PK=|PRIVATE_KEY' || echo clean`.
- If feasible, an **EVM reorg simulation** on the Anvil side to exercise INV-11/12 (the watcher must not
  pay out on a reorged-away burn) — note this is the highest-value test still missing on a real chain.

**Pass condition:** all of the above hold; capture the output in `reports/deploy-dryrun-<date>.md`.

---

## Release gate

This runbook feeds the gate in [`STATE-OF-THE-BRIDGE.md`](./STATE-OF-THE-BRIDGE.md) §6 /
[INVARIANTS](./INVARIANTS.md). Ship for real value only when Leg A.x is **blocked**, Leg B is **all
PASS**, Leg C shows graceful degradation, Leg D is clean, **and** the finality legs (INV-11/12/13) have
been re-verified on Sepolia — not just devnet.
