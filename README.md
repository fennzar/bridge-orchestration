# Zephyr Bridge Stack Orchestration

Unified orchestration layer for the Zephyr bridge development environment.

## Overview

This folder coordinates all components of the bridge stack:
- **Infrastructure:** Redis, PostgreSQL, Anvil, Zephyr nodes, wallets, oracle (via Docker Compose)
- **Applications:** Bridge UI, Engine, Watchers (via Overmind/Procfile.dev)

For comprehensive documentation, see [dev.md](./docs/setup/dev.md).

## Directory Structure
 
```
$ROOT/                       # Parent dev folder (set in .env)
├── bridge-orchestration/    # This folder - orchestration layer
├── zephyr-bridge/           # Bridge operator console (Next.js, port 7050)
├── zephyr-bridge-engine/    # Arbitrage/market-making engine (Next.js, port 7000)
├── zephyr-eth-foundry/      # Solidity contracts (Foundry)
├── zephyr/                  # Zephyr daemon/wallet binaries (devnet branch)
├── zephyr-data/             # Zephyr chain data (node1, node2)
└── zephyr-wallets/          # Zephyr wallet files
```

## Zephyr-core devnet branch
`https://github.com/fennzar/zephyr/tree/fresh-devnet-bootstrap`

## Quick Start

```bash
# 1. Clone this repo + setup (includes keygen)
mkdir ~/zephyr-dev && cd ~/zephyr-dev
git clone git@github.com:fennzar/bridge-orchestration.git
cd bridge-orchestration
make setup                             # Interactive: prereqs, clone, deps, artifacts, keygen

# 2. Init + setup (first time only)
make dev-init                          # Base Zephyr devnet (~4 min)
make dev-setup                         # Deploy contracts + seed liquidity (~4 min)

# 3. Start
make dev                               # Start the stack (~10 sec)

# 4. Between tests
make dev-reset && make dev             # Reset to post-setup state + restart

# 5. Stop
make dev-stop
```

UIs: [Dashboard](http://localhost:7100) | [Bridge](http://localhost:7050) | [Engine](http://localhost:7000)

> **DEVNET is the only supported mode.** It provides controllable oracle prices, fast resets, and consistent state. Mainnet-fork mode is deprecated. See [05-devnet-scenarios.md](./docs/testing/05-devnet-scenarios.md).

## Prerequisites

`make setup` checks all prerequisites and offers to install missing ones interactively. Run `make status` to check your environment at any time.

| Tool | Version | Installation |
|------|---------|--------------|
| Node.js | 22+ | via nvm (setup offers to install) |
| pnpm | 9.x | `npm install -g pnpm` |
| Docker + Compose | latest | via `get.docker.com` |
| Foundry | latest | `curl -L https://foundry.paradigm.xyz \| bash && foundryup` |
| Overmind | latest | [GitHub releases](https://github.com/DarthSim/overmind#installation) |
| tmux | any | `sudo apt install tmux` |
| curl, jq, bc | any | `sudo apt install curl jq bc` |

Plus Zephyr binaries built from the `zephyr` repository (referenced via `$ZEPHYR_REPO_PATH`).

## Setup

All sibling repos can be cloned and set up interactively:

```bash
make setup
```

The script runs through these phases:

1. **Check prerequisites** — scans all 12 tools, shows a status matrix
2. **Interactive fix** — offers to install missing tools (apt batch, nvm, Docker, Foundry, Overmind)
3. **Clone repos** — parallel clones with animated progress (skips existing)
4. **Show branches** — displays current/remote branches, pauses to verify
5. **Install dependencies** — parallel `pnpm install` / `forge install` with spinners
6. **Zephyr build deps** — offers to install C++ build dependencies (Ubuntu/Debian)
7. **Verify Zephyr repo** — checks `$ZEPHYR_REPO_PATH` exists and has built binaries
8. **Key generation** — generates EVM keys + secrets, writes `.env` (idempotent, skips if already configured)

| Local Directory | Repository | Deps |
|-----------------|------------|------|
| `zephyr-eth-foundry/` | [fennzar/zephyr-uniswap-v4-foundry](https://github.com/fennzar/zephyr-uniswap-v4-foundry) | `forge install` |
| `zephyr-bridge/` | [fennzar/zephyr-bridge](https://github.com/fennzar/zephyr-bridge) | `pnpm install` |
| `zephyr-bridge-engine/` | [fennzar/zephyr-bridge-engine](https://github.com/fennzar/zephyr-bridge-engine) | `pnpm install` |
| `zephyr/` | [fennzar/zephyr](https://github.com/fennzar/zephyr) | C++ (build deps offered) |

The script is fully idempotent — safe to re-run at any time.

## Make Targets

| Target | Purpose |
|--------|---------|
| `make setup` | Interactive prereqs, clone repos, deps, Zephyr artifacts, keygen |
| `make keygen` | Regenerate EVM keys + secrets → .env (standalone, for key rotation) |
| `make dev-init` | Base Zephyr devnet, then stop (~4 min) |
| `make dev-setup` | Deploy contracts + seed liquidity, then stop (~4 min) |
| `make dev` | Start the stack (~10 sec) |
| `make dev APPS=bridge` | Start specific app groups (bridge, engine, dashboard) |
| `make dev-stop` | Stop everything (apps + infra) |
| `make dev-reset` | Reset to post-setup state, then stop (~15 sec) |
| `make dev-reset-hard` | Reset to post-init state, then stop (~10 sec) |
| `make dev-delete` | Delete everything (containers, volumes, images) |
| `make dev-checkpoint` | Save current height as checkpoint |
| `make build` | Build Docker images |
| `make status` | Check health of all services |
| `make logs SERVICE=x` | Tail logs for a Docker service |
| `make set-price PRICE=x` | Set fake oracle price |
| `make set-scenario SCENARIO=x` | Quick presets: normal, defensive, crisis |
| `make fund WALLET=x AMOUNT=x ASSET=x` | Transfer funds between wallets |
| `make keygen` | Regenerate EVM keys (standalone, included in `make setup`) |
| `make deploy-contracts` | Deploy all EVM contracts to Anvil |
| `make sync-env` | Sync .env to sub-repos |
| `make testnet-v2` | Sync + build + start (production builds) |
| `make testnet-v2-init` | Init base devnet (same as dev-init) |
| `make testnet-v2-setup` | Setup bridge infra |
| `make testnet-v2-stop` | Stop testnet-v2 stack |
| `make testnet-v2-reset` | Reset to post-setup state |
| `make clean` | Remove all containers and volumes |

### Supporting Scripts

| Script | Purpose |
|--------|---------|
| `sync-env.sh` | Generate repo-specific .env files from master config |
| `deploy-contracts.sh` | Deploy all contracts to Anvil |
| `dev-reset.sh` | Coordinated state reset (delegates chain ops to Zephyr `devnet.sh`) |

## Configuration

The `.env` file is the **master configuration**. Key variables:

| Variable | Purpose |
|----------|---------|
| `ROOT` | Parent directory containing all bridge repos |
| `BRIDGE_ENV` | Environment: local, sepolia, mainnet |
| `EVM_DEV_MNEMONIC` | Mnemonic for Anvil accounts (generated by `make keygen`) |
| `ZEPHYR_REPO_PATH` | Path to Zephyr repository (binaries + CLI + compose) |
| `OVERMIND_FORMATION` | Which processes to start (or use `APPS=` parameter) |

Run `./scripts/sync-env.sh` to propagate changes to:
- `zephyr-bridge/.env.local`
- `zephyr-bridge-engine/.env`

## Infrastructure

### Docker Compose (Infrastructure)

All Zephyr infrastructure runs in Docker Compose:

```bash
make dev-infra                # Start Docker infrastructure only
make logs SERVICE=zephyr-node1  # View container logs
make status                   # Health check all services
```

| Container | Port | Purpose |
|-----------|------|---------|
| `redis` | 6380→6379 | Bridge state cache (DB 6) |
| `postgres` | 5432 | Persistent storage for both apps |
| `anvil` | 8545 | Local EVM chain |
| `zephyr-node1` | 47767 | Primary Zephyr daemon |
| `zephyr-node2` | 47867 | Mining/secondary node |
| `wallet-gov` | 48769 | Governance wallet RPC |
| `wallet-miner` | 48767 | Mining wallet RPC |
| `wallet-test` | 48768 | Test user wallet RPC |
| `fake-oracle` | 5555 | Controllable price oracle |
| `fake-orderbook` | 5556 | Simulated CEX orderbook |

### Overmind (App Processes)

App processes run natively via `Procfile.dev`:

| Process | Port | Description |
|---------|------|-------------|
| `bridge-web` | 7050 | Bridge UI + API |
| `bridge-watchers` | - | Zephyr/EVM/Uniswap watchers |
| `engine-web` | 7000 | Engine dashboard |
| `engine-watchers` | - | MEXC/EVM/Zephyr watchers |
| `status-dashboard` | 7100 | Stack status dashboard |

```bash
make dev-apps                  # Start all app processes via Overmind
make dev-apps APPS=bridge      # Start only bridge processes (bridge-web, bridge-api, bridge-watchers)
make dev-apps APPS=engine      # Start only engine processes (engine-web, engine-watchers)
make dev-apps APPS=bridge,engine  # Bridge + engine (no dashboard)
overmind connect bridge-web    # Attach to app logs (Ctrl-B D to detach)
```

## Contract Deployment

The `deploy-contracts.sh` script deploys:
1. Mock USD tokens (USDC, USDT)
2. Wrapped Zephyr tokens (wZEPH, wZSD, wZRS, wZYS)
3. Uniswap V4 stack (PoolManager, routers)
4. Liquidity pools (USDT-USDC, wZSD-USDT, wZYS-wZSD, wZEPH-wZSD, wZRS-wZEPH)

Deployed addresses are saved to `config/addresses.local.json`.

## Zephyr Chain

DEVNET creates a fresh genesis chain with controllable oracle prices and fast resets.

### Zephyr CLI

Direct wallet operations via `$ZEPHYR_REPO_PATH/tools/zephyr-cli/cli`:

```bash
$ZEPHYR_CLI balances
$ZEPHYR_CLI price
$ZEPHYR_CLI send gov test 1000
```

## URLs When Running

| Service | URL | Notes |
|---------|-----|-------|
| Status Dashboard | http://localhost:7100 | |
| Bridge UI | http://localhost:7050 | |
| Bridge Admin | http://localhost:7050/admin | |
| Engine Dashboard | http://localhost:7000 | |
| Anvil RPC | http://127.0.0.1:8545 | |
| Zephyr RPC (DEVNET) | http://127.0.0.1:47767 | |

## Testing

```bash
# T1: Environment readiness (instant, no infra)
make precheck

# T2: Infrastructure health (post dev-init, ~2 min)
make test-infra

# T3: Basic operations — transfers, oracle, RR mode (~2 min)
make test-ops

# T4A: Bridge health + flows — contracts, APIs, wrap/unwrap (~10 min)
make test-bridge

# T4B: Engine strategy tests (332 tests, ~5 min)
make test-engine

# All tiers in order
make test-all

# Repo unit tests
cd ../zephyr-bridge && pnpm test
cd ../zephyr-bridge-engine && pnpm test
cd ../zephyr-eth-foundry && forge test
```

## Common Issues

### Docker Permission Denied
```bash
sudo usermod -aG docker $USER
newgrp docker
```

### Foundry Not Found
```bash
curl -L https://foundry.paradigm.xyz | bash
~/.foundry/bin/foundryup
export PATH="$HOME/.foundry/bin:$PATH"
```

### Anvil State Issues
```bash
# Reset to post-setup state (restores Anvil snapshot + pops Zephyr chain):
make dev-reset && make dev

# Reset to post-init state (wipes Anvil, need to re-deploy contracts):
make dev-reset-hard && make dev-setup && make dev

# Nuclear option (destroys everything):
make dev-delete
```

### Prerequisites Check Failed
```bash
# Run status check to see all issues:
make status
```

## More Documentation

### Setup
- **[dev.md](./docs/setup/dev.md)** - Local DEVNET development setup
- **[testnet-v2.md](./docs/setup/testnet-v2.md)** - Testnet V2 (production build mode)
- **[testnet-v3.md](./docs/setup/testnet-v3.md)** - Testnet V3 (Sepolia)
- **[evm-wallets.md](./docs/reference/evm-wallets.md)** - EVM wallet tooling, Anvil accounts, Cast CLI
- **[metamask.md](./docs/reference/metamask.md)** - MetaMask test wallet (seed, accounts, funding)

### Testing
- **[Testing README](./docs/testing/README.md)** - Quick reference: commands, test levels, where to start
- **[01-overview.md](./docs/testing/01-overview.md)** - Master test document (L1-L4 levels, test index)
- **[02-infra-checklist.md](./docs/testing/02-infra-checklist.md)** - Quick infrastructure verification
- **[03-bridge-scenarios.md](./docs/testing/03-bridge-scenarios.md)** - Wrap/unwrap test flows (API + UI)
- **[04-full-stack-scenarios.md](./docs/testing/04-full-stack-scenarios.md)** - DEX, engine, admin, faucets, SSE
- **[05-devnet-scenarios.md](./docs/testing/05-devnet-scenarios.md)** - DEVNET mode, RR transitions, oracle control

### Reference
- **[implementation-coverage.md](./docs/reference/implementation-coverage.md)** - Component implementation status
- **[zephyr-tips.md](./docs/reference/zephyr-tips.md)** - Wallet ops, conversions, gotchas
- **[bridge-testnet-v2-update.md](./docs/reference/bridge-testnet-v2-update.md)** - Testnet v2 technical update
