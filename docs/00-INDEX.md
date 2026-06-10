---
title: Zephyr Bridge — Documentation Source of Truth (Index)
status: AUTHORITATIVE (navigation spine)
author: security review
date: 2026-06-10
audience: both (humans + agents)
---

# Zephyr Bridge — Documentation Source of Truth

The hub for everything Zephyr + the ETH bridge. Organized as a **hierarchy: start broad, drill to
technical depth.** Read top-down if you're new; jump to a leaf if you know what you want.

> **Trust note.** Most pre-2026-06 docs were written by lower-tier AI models and are **not reliable**.
> The pages under **§Security** and **§Protocol** below were ground-truth-verified against code on
> 2026-06-10 and supersede any conflicting older doc. Each carries a provenance header; if a doc
> lacks one, treat its claims as *unverified* until checked against code.

---

## Tier 0 — Start here (orientation)

| Doc | For | What it answers |
|---|---|---|
| [`security/STATE-OF-THE-BRIDGE.md`](./security/STATE-OF-THE-BRIDGE.md) | everyone, first | **Is it safe to ship? Where do things actually stand?** (read this first) |
| `../README.md` (hub) | operators | What the stack is, how to start it (`make dev`) |

## Tier 1 — Understand the system (concepts → architecture)

| Doc | Depth | Topic |
|---|---|---|
| [`protocol/zephyr-primer.md`](./protocol/zephyr-primer.md) | concept | Zephyr (Djed stablecoin + privacy), assets V1/V2, reserve ratio, oracle — the protocol facts the bridge depends on (start here) |
| [`protocol/zephyr-reference.md`](./protocol/zephyr-reference.md) | **mega reference** | The exhaustive protocol source-of-truth: lineage, all 4 assets, the exact 400/800/200% reserve gates, conversion pricing + fees, oracle, yield, the 2024–25 audit, bridge design — **code-verified** (`file:line`) |
| [`protocol/bridge-protocol.md`](./protocol/bridge-protocol.md) | spec | The wrap/claim/unwrap protocol: EIP-712 voucher, burn payload, decimals, state machines (code-cited) |
| `zephyr-bridge/docs/architecture.md` | technical | Bridge monorepo layers, dependency graph (secondary; predates CRIT-1) |
| `zephyr-bridge-engine/docs/architecture.md` | technical | Engine cycle, RR-adaptive behavior (secondary; see §Security for the disabled-controls caveat) |
| `zephyr-bridge/docs/data-model.md` | technical | Prisma schema, pub/sub channels |

## Tier 2 — Security (the release gate — **authoritative**)

| Doc | Topic |
|---|---|
| [`security/STATE-OF-THE-BRIDGE.md`](./security/STATE-OF-THE-BRIDGE.md) | Release-readiness verdict, what's sound, the CRITICAL, the HIGH cluster, release checklist |
| [`security/THREAT-MODEL.md`](./security/THREAT-MODEL.md) | Assets, actors, trust boundaries, attack scenarios, the 7 trust principles |
| [`security/INVARIANTS.md`](./security/INVARIANTS.md) | The money-critical invariant ledger + coverage status (this *is* the gate list) |
| [`security/FINDINGS.md`](./security/FINDINGS.md) | Full severity-ranked findings register with concrete fixes |

## Tier 3 — Build, operate, test

| Area | Docs |
|---|---|
| **Setup** | [`setup/dev.md`](./setup/dev.md) (DEVNET) · [`setup/testnet-v2.md`](./setup/testnet-v2.md) · [`setup/testnet-v3.md`](./setup/testnet-v3.md) (Sepolia) · [`setup/mainnet.md`](./setup/mainnet.md) |
| **Operate** | [`troubleshooting.md`](./troubleshooting.md) · `zephyr-bridge/docs/recovery-runbook.md` · ⚠️ **GAP:** signer-key compromise runbook (see PLAN Phase 3) |
| **Test** | [`testing/README.md`](./testing/README.md) (the framework: runner×invariant, red/green, `make test-*`) · [`../tests/CATALOG.md`](../tests/CATALOG.md) (test SoT) · [`security/INVARIANTS.md`](./security/INVARIANTS.md) (the INV-1..19 gate, `make test-report`) · [`security/stress-test-runbook.md`](./security/stress-test-runbook.md) (adversarial + load legs) |
| **Reference** | [`reference/zephyr-tips.md`](./reference/zephyr-tips.md) (wallet/RPC gotchas) · [`reference/evm-wallets.md`](./reference/evm-wallets.md) · [`reference/metamask.md`](./reference/metamask.md) · [`dashboard-api.md`](./dashboard-api.md) |

## Tier 4 — Plans & roadmap

| Doc | Topic |
|---|---|
| [`plans/bridge-hardening.md`](./plans/bridge-hardening.md) | Remediation + first-principles test rewrite + testnet-v2 stress plan (the path to release) |

---

## Per-repo authoritative references (the accurate ones)

Each sibling repo's own README is the authority for that repo:
- `zephyr-bridge/` — monorepo layout, conventions
- `zephyr-bridge-engine/` — engine orchestration, DB
- `zephyr-eth-foundry/` — contracts, deploy scripts, devnet addresses
- `zephyr/README.md` — the Zephyr protocol itself
- `next-explorer/` — explorer

## Doc-hygiene actions (recommended, not yet done)

These are *recommendations*; I did not delete/move existing files (avoiding churn during a security
review). Apply when convenient:
- **Archive (stale/superseded):** `reference/mainnet-fork-environment-deprecated.md`,
  `reference/bridge-testnet-v2-update.md`, `reference/implementation-coverage.md`,
  `reference/draft-bridge-engine-reference.md`, `zephyr-bridge/docs/uniswap-implementation-plan*.md`.
- **Add provenance headers** to surviving narrative docs (`zephyr-bridge/docs/*`,
  `zephyr-bridge-engine/docs/*`) so readers know who wrote them and when — the `/artifact-meta` skill
  does exactly this.
- **Flag** `zephyr-bridge-engine/docs/execution-and-risk.md` as describing *intended* behavior; the
  risk controls it documents are disabled-by-default in code (FINDINGS HIGH-5).

---

### Conventions for this doc tree
- **Provenance header** on every authoritative doc: `status`, `author`, `date`, and (for security
  docs) a verification legend. No header ⇒ unverified.
- **Cite code** (`file:line`) for any load-bearing claim. Prose without a citation is opinion.
- **Humans read top-down, agents grep leaves** — so each leaf is self-contained and links its peers.
