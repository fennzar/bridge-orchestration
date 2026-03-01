# Testing

Quick reference for the Zephyr Bridge test suite. For detailed test specs, see the docs linked below.

## Quick Commands

| Command | What it does |
|---------|-------------|
| `make test` | Run all L1-L4 tests |
| `make test-l1` | Infrastructure checks (~2 min) |
| `make test-l2` | Component smoke tests (~5 min) |
| `make test-l5-execute` | L5 edge-case automated checks |
| `make test-engine` | Engine strategy tests (332 tests) |
| `make status` | Health check all services |
| `make dev-reset && make dev` | Reset to clean state between test runs |
| `make set-price PRICE=x` | Change oracle price for RR testing |

## Test Levels

| Level | Purpose | Time | Command | Details |
|-------|---------|------|---------|---------|
| **L1** | Services running, ports reachable | ~2 min | `make test-l1` | [01-overview.md](./01-overview.md#l1-infrastructure-tests) |
| **L2** | Basic functionality per component | ~5 min | `make test-l2` | [01-overview.md](./01-overview.md#l2-component-smoke-tests) |
| **L3** | Detailed feature testing | ~15 min | `make test-l3` | [03-bridge-scenarios.md](./03-bridge-scenarios.md), [04-full-stack-scenarios.md](./04-full-stack-scenarios.md) |
| **L4** | Cross-system E2E flows | ~30+ min | `make test-l4` | [05-devnet-scenarios.md](./05-devnet-scenarios.md), [06-engine-strategies.md](./06-engine-strategies.md) |
| **L5** | Edge cases, security, chaos | varies | `make test-l5-execute` | [00-edge-case-scope.md](./00-edge-case-scope.md), [08-edge-framework.md](./08-edge-framework.md) |
| **Engine** | Strategy unit tests (332) | ~2 min | `make test-engine` | [engine-test-scope.md](./engine-test-scope.md) |

## Where to Start

- **First time** — `make test-l1` (verify infra is healthy)
- **After changes** — `make test` (runs L1-L4)
- **Deep validation** — `make test-l5-execute` (automated edge-case checks)
- **Engine strategies** — `make test-engine` (332 unit tests)

## Running Specific Tests

```bash
# By test ID
./scripts/run-tests.py INFRA-01 SMOKE-01

# By level
make test-l1                          # or test-l2, test-l3, test-l4

# L5 by category
./scripts/run-l5-tests.py --execute --category SEC --verbose

# L5 by sublevel
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

## L5 Edge Categories

168 tests across 16 categories, grouped into 6 sublevels:

| Sublevel | Make target | Categories | Tests |
|----------|------------|------------|------:|
| **L5.1** Security & Contracts | `make test-l5-sec` | SEC, SC | 24 |
| **L5.2** Runtime & Consistency | `make test-l5-runtime` | CONS, RR, CONC, SEED, ARB | 58 |
| **L5.3** Infra & Watchers | `make test-l5-infra` | WATCH, CONF, REC | 32 |
| **L5.4** Asset & DEX | `make test-l5-asset` | ASSET, DEX | 20 |
| **L5.5** Privacy & Load | `make test-l5-stress` | PRIV, LOAD, TIME | 22 |
| **L5.6** Frontend | `make test-l5-fe` | FE | 12 |

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
| [01-overview.md](./01-overview.md) | Master test doc: L1-L4 specs, test IDs, checkpoint state |
| [02-infra-checklist.md](./02-infra-checklist.md) | Quick infrastructure verification checklist |
| [03-bridge-scenarios.md](./03-bridge-scenarios.md) | Bridge wrap/unwrap test flows (API + UI) |
| [04-full-stack-scenarios.md](./04-full-stack-scenarios.md) | DEX, engine, admin, faucets, SSE |
| [05-devnet-scenarios.md](./05-devnet-scenarios.md) | DEVNET mode, RR transitions, oracle control |
| [06-engine-strategies.md](./06-engine-strategies.md) | Strategy-specific evaluation tests |
| [08-edge-framework.md](./08-edge-framework.md) | L5 execution framework and browser lane workflow |
| [00-edge-case-scope.md](./00-edge-case-scope.md) | Full L5 edge-case catalog (168 tests) |
| [engine-test-scope.md](./engine-test-scope.md) | Engine test cases (332 tests, 12 modules) |
