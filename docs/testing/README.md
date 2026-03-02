# Testing

Quick reference for the Zephyr Bridge test suite. For detailed test specs, see the docs linked below.

## Quick Commands

| Command | What it does |
|---------|-------------|
| `make precheck` | Pre-setup gate — is infra ready for dev-setup? (~2 min) |
| `make smoke` | Post-setup health — are apps + contracts working? (~2 min, read-only) |
| `make test` | Integration tests — does the bridge work? (~8-12 min, moves funds) |
| `make test-seed` | Seed verification — is the stack bootstrapped? (~2 min) |
| `make test-all` | All tiers: precheck + smoke + integration + seed |
| `make test-engine` | Engine strategy tests (332 tests) |
| `make test-edge` | Edge-case framework (automated checks) |
| `make status` | Health check all services |
| `make dev-reset && make dev` | Reset to clean state between test runs |
| `make set-price PRICE=x` | Change oracle price for RR testing |

## Test Tiers

| Tier | Purpose | Mutates | Time | Command | Details |
|------|---------|---------|------|---------|---------|
| **Precheck** | Pre-setup gate: infra ready for dev-setup | Some | ~2 min | `make precheck` | 13 tests (10 read-only + 3 state-mutating with restore) |
| **Smoke** | Post-setup health: apps + contracts working | No | ~2 min | `make smoke` | 19 read-only health probes |
| **Integration** | Bridge flows: wrap, unwrap, wallet creation | Yes | ~8-12 min | `make test` | 5 tests exercising real fund movement |
| **Seed** | Stack fully bootstrapped (pools, inventory) | No | ~2 min | `make test-seed` | 9 verification checks |
| **Engine** | Strategy unit tests (332) | No | ~5 min | `make test-engine` | [engine-test-scope.md](./engine-test-scope.md) |
| **Edge** | Security, race conditions, chaos | Mixed | ~10+ min | `make test-edge` | [00-edge-case-scope.md](./00-edge-case-scope.md), [08-edge-framework.md](./08-edge-framework.md) |

## Where to Start

- **Before dev-setup** — `make precheck` (verify infra is ready)
- **After dev-setup** — `make smoke` (verify apps + contracts are working)
- **After changes** — `make test` (exercises wrap/unwrap pipeline)
- **Full validation** — `make test-all` (precheck + smoke + integration + seed)
- **Deep edge cases** — `make test-edge-execute` (automated edge-case checks)
- **Engine strategies** — `make test-engine` (332 unit tests)

## Running Specific Tests

```bash
# By test ID
./scripts/run-tests.py INFRA-01 WRAP-01

# By tier
make precheck                        # or test, test-seed
./scripts/run-tests.py --tier precheck --tier seed  # multiple tiers

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
