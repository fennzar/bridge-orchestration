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
# 1. Clone this repo + all sibling repos
mkdir ~/zephyr-dev && cd ~/zephyr-dev
git clone git@github.com:fennzar/bridge-orchestration.git
cd bridge-orchestration
./scripts/clone-repos.sh               # Check prereqs, clone repos, install deps

# 2. Generate keys + configure paths
make keygen                            # Generate fresh keys → .env
# Edit .env: set ROOT to your parent dir (e.g. /home/you/zephyr-dev)
#            set PATH to include your node/pnpm/foundry bins
./scripts/sync-zephyr-artifacts.sh     # Vendor Zephyr binaries (once)

# 3. Init + setup (first time only)
make dev-init                          # Base Zephyr devnet (~4 min)
make dev-setup                         # Deploy contracts + seed liquidity (~4 min)

# 4. Start
make dev                               # Start the stack (~10 sec)

# 5. Between tests
make dev-reset && make dev             # Reset to post-setup state + restart

# 6. Stop
make dev-stop
```

UIs: [Dashboard](http://localhost:7100) | [Bridge](http://localhost:7050) | [Engine](http://localhost:7000)

> **DEVNET is the only supported mode.** It provides controllable oracle prices, fast resets, and consistent state. Mainnet-fork mode is deprecated. See [05-devnet-scenarios.md](./docs/testing/05-devnet-scenarios.md).

## Prerequisites

Run `make status` to check your environment. Required:

| Tool | Version | Installation |
|------|---------|--------------|
| Node.js | 22+ | `nvm install 22` |
| pnpm | 9.x | `npm install -g pnpm` |
| Docker | latest | `sudo apt install docker.io` |
| Foundry | latest | `curl -L https://foundry.paradigm.xyz \| bash && foundryup` |
| Overmind | latest | [GitHub releases](https://github.com/DarthSim/overmind#installation) |
| tmux | any | `sudo apt install tmux` |

Plus Zephyr binaries built from the `zephyr` repository.

## Clone Repos

All sibling repos can be cloned and set up in one step:

```bash
./scripts/clone-repos.sh
```

The script runs three phases:

1. **Check prerequisites** — verifies all tools above are installed, exits early if any are missing
2. **Clone repos** — clones into the parent directory (skips existing)
3. **Install dependencies** — `forge install` for contracts, `pnpm install` for JS/TS repos

| Local Directory | Repository | Deps |
|-----------------|------------|------|
| `zephyr-eth-foundry/` | `git@github.com:fennzar/zephyr-uniswap-v4-foundry.git` | `forge install` |
| `zephyr-bridge/` | `git@github.com:fennzar/zephyr-bridge.git` | `pnpm install` |
| `zephyr-bridge-engine/` | `git@github.com:fennzar/zephyr-bridge-engine.git` | `pnpm install` |
| `zephyr/` | `https://github.com/ZephyrProtocol/zephyr` | C++ (see below) |

The script also prints system dependency install commands for building the Zephyr daemon from source (Ubuntu/Debian, Arch, Fedora, openSUSE, macOS).

## Make Targets

| Target | Purpose |
|--------|---------|
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
| `make keygen` | Generate fresh EVM keys + secrets, write to .env |
| `make deploy-contracts` | Deploy all EVM contracts to Anvil |
| `make sync-env` | Sync .env to sub-repos |
| `make clean` | Remove all containers and volumes |

### Legacy Scripts (still available)

| Script | Purpose |
|--------|---------|
| `sync-env.sh` | Generate repo-specific .env files from master config |
| `deploy-contracts.sh` | Deploy all contracts to Anvil |
| `devnet.sh` | Unified DEVNET commands (save, restore, fund, etc.) |

## Configuration

The `.env` file is the **master configuration**. Key variables:

| Variable | Purpose |
|----------|---------|
| `ROOT` | Parent directory containing all bridge repos |
| `BRIDGE_ENV` | Environment: local, sepolia, mainnet |
| `EVM_DEV_MNEMONIC` | Mnemonic for Anvil accounts (generated by `make keygen`) |
| `ZEPHYR_BIN_PATH` | Path to Zephyr binaries |
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

The test chain **splits from mainnet** (preserving oracle history). This is required because oracle pricing data must be present in chain history.

### Mining

Mining is started automatically during `make dev-init`. To control manually:

```bash
# Mining is managed by Docker Compose containers
# Use the Zephyr CLI for direct wallet operations:
$ZEPHYR_CLI balances
$ZEPHYR_CLI price
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
# Bridge tests
cd ../zephyr-bridge && pnpm test

# Engine tests
cd ../zephyr-bridge-engine && pnpm test

# Foundry tests
cd ../zephyr-eth-foundry && forge test

# E2E tests
make test
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
- **[01-overview.md](./docs/testing/01-overview.md)** - Master test document (L1-L4 levels, test index)
- **[02-infra-checklist.md](./docs/testing/02-infra-checklist.md)** - Quick infrastructure verification
- **[03-bridge-scenarios.md](./docs/testing/03-bridge-scenarios.md)** - Wrap/unwrap test flows (API + UI)
- **[04-full-stack-scenarios.md](./docs/testing/04-full-stack-scenarios.md)** - DEX, engine, admin, faucets, SSE
- **[05-devnet-scenarios.md](./docs/testing/05-devnet-scenarios.md)** - DEVNET mode, RR transitions, oracle control

### Reference
- **[implementation-coverage.md](./docs/reference/implementation-coverage.md)** - Component implementation status
- **[zephyr-tips.md](./docs/reference/zephyr-tips.md)** - Wallet ops, conversions, gotchas
- **[bridge-testnet-v2-update.md](./docs/reference/bridge-testnet-v2-update.md)** - Testnet v2 technical update
