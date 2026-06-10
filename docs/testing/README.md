# Bridge Test Framework

The bridge is a custodial Zephyr↔EVM system that holds real money. This framework tests **what a
functional bridge must guarantee** — the money-critical *properties* — not code units or API shapes.
Every test pins a row in the release-gate ledger and is written as the *correct* behavior; where the
system has a hole, the test is **red today** and tagged, so a run renders the holes as a worklist.

> **This repo owns the cross-stack tests.** The big-picture, money-path, and engine↔market-dynamics
> scenarios live here. Sibling repos keep only a thin sanity tier for local iteration (forge custody
> tests, engine/bridge unit specs); the orchestration repo's ledger harvests their results.

## The two sources of truth

Everything is grounded in two **code-verified** documents — treat all other testing prose as
reference, not authority:

- **[`docs/security/INVARIANTS.md`](../security/INVARIANTS.md)** — the money-critical ledger
  **INV-1..19**. This *is* the release gate: the bridge is releasable when every row is green.
- **[`docs/protocol/zephyr-reference.md`](../protocol/zephyr-reference.md)** — the code-verified
  Zephyr protocol (RR gates, mint/redeem rules, decimals, pricing). The market tests assert the
  engine against *this*, not against re-encoded constants.

The full enumerated catalog — every test id → invariant → layer → expected status — is
**[`tests/CATALOG.md`](../../tests/CATALOG.md)** (the single test SoT).

## Organized by runner × invariant

| Layer | Runner | Lives in | Stack? | Proves |
|---|---|---|---|---|
| **CONTRACT** | forge | `zephyr-eth-foundry/test/` | no | custody/crypto on-chain (INV-1,5,6,8,9,10) |
| **LOGIC — engine** | vitest | `zephyr-bridge-engine/tests/` | no | decision fns + **protocol-conformance** (engine model vs Zephyr SoT) |
| **LOGIC — bridge** | node:test | `zephyr-bridge/packages/**` | no | money-math + confirmation primitives (INV-3,6,11) |
| **SCENARIO** | pytest | `tests/scenario/` | **yes** (`make dev`) | the heart: money-path E2E, engine↔market dynamics, security, resilience |
| **UI** | Playwright | `tests/e2e/` | yes + browser | thin human-style wrap/unwrap/swap/LP (Phase 3, manual) |
| **REPORT** | `scripts/invariant-report.py` | here | aggregates | renders the INV-1..19 ledger |

## Red/green — the KNOWN-GAP model

A test asserts the *correct* behavior. Today many of those behaviors are holes, so the test is
**red** — and that red is the signal, not a failure of the suite:

- **GREEN** — invariant held here.
- **KNOWN-GAP** (`@known_gap` / `it.fails` / `_gap` in the name) — a real hole; red today, on the
  worklist, **non-fatal** to the gate.
- **ACCEPTED** (`@accepted_risk`) — an owner-accepted, documented deviation (amber); never fatal.
- **REGRESSION** — an *untagged* failure → **fatal** (fix it or tag it).
- **UNEXPECTED-PASS** — a known-gap that started passing → **fatal**: the fix landed, promote the
  INVARIANTS.md row to HELD and drop the marker.

So the gate is simply: **no regressions, no silent fixes.** Closing a known-gap (separate work,
Phase 2) is how an INV row goes from red to green.

### How a test declares its invariant

The ledger is generated from the live tests, so each test self-declares — no hand-kept mapping:

- **pytest**: `@pytest.mark.inv("INV-14")` (+ `@known_gap(inv=..., reason=...)` for a gap).
- **vitest**: an `[INV-NN]` tag in the test title; known-gaps use `it.fails` **and** an `[gap]` tag (an `it.fails` *without* `[gap]` silently reads GREEN-while-open — always pair them).
- **node:test**: an `[INV-NN]` tag in the test **title** string (+ `[gap]` in the title for a known-gap).
- **forge**: a `/// INV-N` NatSpec comment above the test fn (Solidity fn names can't hold tags); known-gaps use a `KNOWNGAP_` fn name or a `[gap]` NatSpec tag.

`scripts/invariant-report.py` reads these, buckets each INV by the **worst** status across every
layer that pinned it, and prints the gate.

## Running it

```bash
make test-report          # ← the north star: the INV-1..19 release-gate ledger
make test                 # deterministic layers + ledger (no live stack): contract + logic + report
make test-contract        # forge custody/crypto invariants
make test-logic           # engine vitest + bridge node:test
make test-scenario        # the live E2E suite — needs `make dev` up first
make test-ui              # thin Playwright (needs stack + Chrome/MetaMask; manual, Phase 3)
```

Scenario selectors: `make test-scenario SUITE=market` · `INV=INV-14` · `ASSET=ZSD` · `ARGS="-k name"`.

`make test-report` rolls up every layer it can — the engine vitest conformance and bridge node:test
and forge contract layers run live; the scenario rows come from the **last** scenario run
(`tests/scenario/.report/scenario.json`), so run `make test-scenario` against a live stack first to
refresh them. The forge layer is default-on because it is the only place INV-1/5/8/9/10
(custody + crypto) are pinned — `ARGS=--no-forge` drops it (and honestly widens the UNCOVERED set)
only where the foundry toolchain is unavailable.

> **⚠ Footgun — never run `make test-report` after a _filtered_ scenario run.** Each `pytest`
> invocation **overwrites** `tests/scenario/.report/scenario.json` (it does not merge), and the
> report does **not** re-run scenario. So `make test-scenario SUITE=flows` followed by
> `make test-report` leaves the scenario-only pins (INV-7, INV-18) reading **UNKNOWN** in the
> ledger — a false gap, not a real one. Always run the **full** `make test-scenario` (no `SUITE=` /
> `INV=` filter) immediately before `make test-report`.

### SCENARIO isolation

Scenario tests are markered for safe, repeatable runs against `make dev`:

- `@needs_stack` — skipped (not red) when core services are down, so a no-stack run stays clean.
- `@needs_reset` — mutates Zephyr chain state (mining/conversions); the operator runs these isolated
  and `make dev-reset`s between them. EVM-only tests use the `anvil_snapshot` fixture (snapshot →
  revert) and `clean_market` (restore oracle + spread) for cheap per-test isolation.

## Adding a test

1. Pick the invariant from `INVARIANTS.md` and the layer (what *runner* can prove it).
2. Write the **negative**/correct-behavior assertion first; confirm it's red where the hole is.
3. Tag it (above) so it rolls into the ledger. Add the row to `tests/CATALOG.md`.
4. A green that should be red, or a red that should be green, means the catalog/ledger and reality
   disagree — reconcile, don't paper over.
