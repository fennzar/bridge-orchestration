# Testing

Quick reference for the Zephyr Bridge test suite. Every `make test-*` is self-contained — it handles its own state (resets, setup, startup). Any tier can run in isolation, in any order.

## Quick Commands

| Command | What it does | Time |
|---------|-------------|------|
| `make precheck` | T1: Environment readiness (repos, binaries, .env) | instant |
| `make test-infra` | T2: Infrastructure health (Docker, wallets, chain) | ~2 min |
| `make test-ops` | T3: Basic operations (transfers, oracle, RR mode) | ~2 min |
| `make test-bridge` | T4A: Bridge suite (health + wrap/unwrap flows) | ~10 min |
| `make test-engine` | T4B: Engine strategy tests (332 tests) | ~5 min |
| `make test-e2e` | T5: Full system tests (placeholder) | — |
| `make test-all` | All tiers in order | ~20 min |
| `make test-edge` | Edge-case framework (automated checks) | ~10+ min |
| `make status` | Health check all services | instant |

## Tier Structure

```
Tier   Name          When            What it proves
─────────────────────────────────────────────────────────────────────────
T1     precheck      pre dev-init    Environment ready (repos, bins, env)
T2     test-infra    post dev-init   Infrastructure comes up healthy
T3     test-ops      post dev-init   Basic operations work (funds, oracle)
T4A    test-bridge   post dev-setup  Bridge works (wrap, unwrap, all assets)
T4B    test-engine   post dev-setup  Engine strategies (332 unit tests)
T5     test-e2e      post dev-setup  Full system (engine arb execution)
```

## Self-Contained Tests

Each tier handles its own prerequisites via `scripts/test-gate.sh`:

| Tier | Gate behaviour |
|------|---------------|
| `precheck` | No state management — pure file/binary checks |
| `test-infra`, `test-ops` | dev-reset-hard → start Docker infra → open wallets |
| `test-bridge`, `test-engine`, `test-e2e` | If no addresses.json: dev-reset-hard → dev-test-setup (full deploy + seed). Otherwise: dev-reset → make dev |

**CI/non-interactive:** All prompts auto-accept when `CI=1` or when stdin is not a TTY.

### Why `dev-test-setup.sh` exists

`dev-test-setup.sh` is a frozen copy of `dev-setup.sh`. It provides a stable, repeatable setup that tests depend on, regardless of how `dev-setup.sh` evolves (different pool sizes, new contracts, etc.).

Key differences from `dev-setup.sh`:
- On **success**: leaves the stack running (tests need it)
- On **failure**: stops everything (same as `dev-setup.sh`)
- Writes marker `config/.test-setup-done` on completion

Run it directly: `make dev-test-setup`

## Test Counts

| Tier | Tests | Mutates | Details |
|------|------:|---------|---------|
| **T1 Precheck** | 5 | No | .env, repos, Docker, binaries, snapshot |
| **T2 Infra** | 10 | No | Docker services, wallets, chain, oracle, mining |
| **T3 Ops** | 3 | Yes (with restore) | Transfer, oracle control, RR mode |
| **T4A Bridge** | 33 | Some | 28 health + 5 flow tests (wrap/unwrap) |
| **T4B Engine** | 332 | No | External runner (12 modules) |
| **T5 E2E** | 0 | — | Placeholder |
| **Edge** | 168 | Mixed | [00-edge-case-scope.md](./00-edge-case-scope.md) |

## Where to Start

- **Fresh environment** — `make precheck` (verify repos/binaries/env)
- **After dev-init** — `make test-infra` (verify infrastructure)
- **After dev-setup** — `make test-bridge` (verify bridge works)
- **After changes** — `make test-bridge` (exercises full bridge pipeline)
- **Full validation** — `make test-all` (all tiers, each self-contained)
- **Engine strategies** — `make test-engine` (332 unit tests)
- **Deep edge cases** — `make test-edge-execute` (automated edge-case checks)

## Running Specific Tests

```bash
# By test ID
./scripts/run-tests.py INFRA-01 WRAP-01

# By tier
./scripts/run-tests.py --tier precheck
./scripts/run-tests.py --tier infra --tier ops     # multiple tiers

# Edge by category
./scripts/run-l5-tests.py --execute --category SEC --verbose

# Edge by sublevel
./scripts/run-l5-tests.py --execute --sublevel L5.1 --verbose

# Engine by module
python3 scripts/engine_tests/runner.py --module arb_gates

# List available tests
./scripts/run-tests.py --list
./scripts/run-l5-tests.py --list
python3 scripts/engine_tests/runner.py --list

# Verbose output
./scripts/run-tests.py --verbose
make test-engine-verbose
```

## Edge Categories

168 tests across 16 categories, grouped into 6 sublevels:

| Sublevel | Make target | Categories | Tests |
|----------|------------|------------|------:|
| **L5.1** Security & Contracts | `make test-edge-sec` | SEC, SC | 24 |
| **L5.2** Runtime & Consistency | `make test-edge-runtime` | CONS, RR, CONC, SEED, ARB | 58 |
| **L5.3** Infra & Watchers | `make test-edge-infra` | WATCH, CONF, REC | 32 |
| **L5.4** Asset & DEX | `make test-edge-asset` | ASSET, DEX | 20 |
| **L5.5** Privacy & Load | `make test-edge-stress` | PRIV, LOAD, TIME | 22 |
| **L5.6** Frontend | `make test-edge-fe` | FE | 12 |

| Category | Count | Description |
|----------|------:|-------------|
| SEC | 12 | Bridge security (signatures, replay, authorization) |
| SC | 12 | Smart contract edge cases (overflow, reentrancy) |
| CONC | 10 | Concurrency and race conditions |
| REC | 10 | Failure recovery (retries, partial state) |
| CONS | 10 | Data consistency (cross-chain, DB vs chain) |
| RR | 8 | Reserve ratio mode boundaries |
| WATCH | 12 | Watcher reliability (missed blocks, reconnect) |
| ASSET | 10 | Multi-asset interactions |
| DEX | 10 | DEX edge cases (slippage, pool drain) |
| TIME | 8 | Timeout and deadline handling |
| CONF | 10 | Configuration errors |
| LOAD | 8 | Load and stress testing |
| PRIV | 6 | Privacy leak detection |
| FE | 12 | Frontend edge cases |
| SEED | 8 | Seeding verification (automated) |
| ARB | 22 | Engine arbitrage integration (automated) |

## Documentation Index

| File | Purpose |
|------|---------|
| [README.md](./README.md) | This file — testing quick reference |
| [01-overview.md](./01-overview.md) | Master test doc: test specs, checkpoint state |
| [02-infra-checklist.md](./02-infra-checklist.md) | Quick infrastructure verification checklist |
| [03-bridge-scenarios.md](./03-bridge-scenarios.md) | Bridge wrap/unwrap test flows (API + UI) |
| [04-full-stack-scenarios.md](./04-full-stack-scenarios.md) | DEX, engine, admin, faucets, SSE |
| [05-devnet-scenarios.md](./05-devnet-scenarios.md) | DEVNET mode, RR transitions, oracle control |
| [06-engine-strategies.md](./06-engine-strategies.md) | Strategy-specific evaluation tests |
| [08-edge-framework.md](./08-edge-framework.md) | Edge execution framework and browser lane workflow |
| [00-edge-case-scope.md](./00-edge-case-scope.md) | Full edge-case catalog (168 tests) |
| [engine-test-scope.md](./engine-test-scope.md) | Engine test cases (332 tests, 12 modules) |
