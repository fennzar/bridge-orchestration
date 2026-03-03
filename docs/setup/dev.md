# Zephyr Bridge Stack - DEVNET Development Environment

## Quick Start

```bash
# One-time setup (interactive — prereqs, clone, deps, artifacts, keygen)
make setup

# First time setup (staged — each step stops when done)
make dev-init                          # Base Zephyr devnet (~4 min)
make dev-setup                         # Bridge wallets + contracts + seed (~4 min)
make dev                               # Start the stack (~10 sec)
# Blockscout block explorer starts by default at http://localhost:4000
# To skip: make dev EXPLORER=0

# Between tests
make dev-reset && make dev             # Reset to post-setup state + restart (~15 sec)

# Stop everything (data preserved for next `make dev`)
make dev-stop

# Delete everything (containers, volumes, images)
make dev-delete
```

The setup is staged: `dev-init` creates the base Zephyr chain, `dev-setup` adds bridge infrastructure on top, and `dev` just starts. Each init/setup/reset command stops everything when done — `make dev` is always the start command.

## Selective App Startup

Don't need the full stack? Use `APPS=` to start only what you're working on:

```bash
make dev APPS=bridge              # Bridge only (bridge-web, bridge-api, bridge-watchers)
make dev APPS=engine              # Engine only (engine-web, engine-watchers)
make dev APPS=bridge,engine       # Bridge + engine, no dashboard
make dev APPS=bridge,dashboard    # Bridge + dashboard
```

Infrastructure (Docker Compose) always starts fully regardless of `APPS=`. Blockscout is separate — use `EXPLORER=0` to skip it.

## Daily Workflow

```bash
make status                            # Pipeline stage, persisted state, all services
make dev-reset && make dev             # Reset to post-setup state + restart
make dev-reset-hard && make dev-setup && make dev  # Reset to post-init + re-setup + start
make set-price PRICE=0.40              # Trigger crisis mode
make set-scenario SCENARIO=defensive   # Presets: normal, defensive, crisis, recovery, high-rr, volatility
make fund WALLET=test AMOUNT=1000 ASSET=ZPH
make logs SERVICE=zephyr-node1         # Docker container logs
overmind connect bridge-api -s .overmind-dev.sock  # App process logs (Ctrl-B D to detach)
```

## Prerequisites

| Tool | Version | Installation |
|------|---------|--------------|
| Node.js | 22+ LTS | `nvm install 22` |
| pnpm | 9.x | `npm install -g pnpm` |
| Foundry | latest stable | `curl -L https://foundry.paradigm.xyz \| bash && foundryup` |
| Docker + Compose | latest | `apt install docker.io docker-compose-plugin` |
| Overmind | latest | [GitHub releases](https://github.com/DarthSim/overmind#installation) |
| tmux | any | `sudo apt install tmux` (required by Overmind) |

```bash
make status              # Check environment and service health
```

## Architecture

Three-layer stack:

- **Docker Compose** (`make dev-infra`): Zephyr nodes, wallets, oracle, orderbook, Redis, Postgres, Anvil
- **Blockscout** (Docker, explorer profile): Block explorer at :4000 — on by default, `EXPLORER=0` to skip
- **Overmind** (`make dev-apps`): bridge-web, bridge-api, bridge-watchers, engine-web, engine-watchers, dashboard

`make dev` starts all three. `make dev-stop` stops all three.

## Ports

| Service | Port | Notes |
|---------|------|-------|
| Dashboard | 7100 | Status web UI |
| Bridge Web UI | 7050 | Next.js frontend |
| Bridge API | 7051 | Express backend |
| Engine | 7000 | Strategy engine |
| Redis | 6380 | Mapped from container 6379 |
| Anvil (EVM) | 8545 | Local EVM chain |
| Zephyr Node 1 | 47767 | Primary daemon |
| Zephyr Node 2 | 47867 | Mining/secondary |
| Gov Wallet | 48769 | Main funds |
| Miner Wallet | 48767 | Mining rewards |
| Test Wallet | 48768 | User transactions |
| Bridge Wallet | 48770 | Bridge operator |
| Fake Oracle | 5555 | Controllable price |
| Fake Orderbook | 5556 | Simulated CEX |
| Blockscout | 4000 | Block explorer (`EXPLORER=0` to skip) |

---

# Reference

Everything below is for understanding what's happening under the hood. You don't need any of this for normal development — `make dev` handles it all.

## What Each Command Does

### `make dev-init` — Base Zephyr devnet, then stop

Wipes everything (volumes, images), rebuilds Docker images, bootstraps a fresh Zephyr chain with gov/miner/test wallets and minted assets. No bridge/engine wallets, no EVM contracts. **Stops when done.**

### `make dev-setup` — Bridge infrastructure, then stop

Requires `dev-init`. Creates bridge/engine wallets, deploys EVM contracts, seeds liquidity through the full bridge wrap flow, saves Anvil snapshot. **Stops when done.**

### `make dev` — Start the stack

Just starts. Checks prerequisites (checkpoint + addresses.json), starts Docker infra + Blockscout + Overmind apps. Blockscout starts unless `EXPLORER=0`. Fast and predictable.

### `make dev-explorer` — Start Blockscout standalone

Starts Blockscout containers (DB, backend, frontend, proxy) when infra is already running. Useful if you started with `EXPLORER=0` and want to add the explorer later.

### `make dev-stop` — Stop the stack

Stops Overmind apps and Docker containers. Volumes persist — `make dev` picks up where you left off.

### `make dev-reset` — Reset to post-setup state, then stop

Pops Zephyr to checkpoint, wipes Anvil, resets DBs + Redis + Blockscout. Ready for `make dev`. **Stops when done.**

### `make dev-reset-hard` — Reset to post-init state, then stop

Restores Zephyr LMDB from init snapshots, wipes Anvil + addresses. Ready for `make dev-setup`. **Stops when done.**

### `make dev-delete` — Full wipe

Stops everything and deletes all containers, volumes, and Docker images. Clean slate — run `make dev-init` to start over.

## Zephyr Artifacts

Zephyr Docker images (daemon, oracle, devnet-init) build automatically from the Zephyr repo via Docker Compose on `make dev-init`. No vendored copies are needed in bridge-orch.

Binaries must be pre-built in `$ZEPHYR_REPO_PATH`:
```bash
cd ../zephyr && tools/fresh-devnet/run.sh build
```

The Zephyr CLI is used directly from `$ZEPHYR_REPO_PATH/tools/zephyr-cli/cli`.

## Repository Structure

```
$ROOT/
├── zephyr/                    # Core protocol (C++ daemon + wallet)
├── zephyr-bridge/             # Bridge operator console (Next.js)
├── zephyr-bridge-engine/      # Trading/arb engine (Next.js + workers)
├── zephyr-eth-foundry/        # Smart contracts (Solidity/Foundry)
└── bridge-orchestration/      # This repo
```

## Databases

Managed by Docker Compose. Created automatically on first `docker compose up`.

| Database | User | Password | Purpose |
|----------|------|----------|---------|
| `zephyrbridge_dev` | `zephyr` | (from `POSTGRES_PASSWORD` in `.env`) | Bridge app |
| `zephyr_bridge_arb` | `zephyr` | (from `POSTGRES_PASSWORD` in `.env`) | Engine |
| `blockscout` | `blockscout` | `blockscout` | Blockscout explorer (auto-wiped on reset) |

Redis runs in Docker on host port 6380 (container 6379, DB 6).

## EVM Contracts

Deployed automatically by `make dev-setup` via `./scripts/deploy-contracts.sh`. Includes:
- Mock stablecoins (USDC, USDT)
- Wrapped Zephyr tokens (wZEPH, wZSD, wZRS, wZYS)
- Uniswap V4 stack (PoolManager, routers)
- Liquidity pools (USDT-USDC, wZSD-USDT, wZYS-wZSD, wZEPH-wZSD, wZRS-wZEPH)

Addresses saved to `config/addresses.local.json`.

> This project uses a **generated mnemonic** (`EVM_DEV_MNEMONIC` in `.env`, created by `make setup` or `make keygen`), NOT the default Foundry mnemonic. See [metamask.md](../reference/metamask.md) for MetaMask setup.

## Zephyr Wallets

All managed by Docker Compose, started automatically.

| Wallet | Purpose | Port |
|--------|---------|------|
| Gov Wallet | Main funds, bridge operations | 48769 |
| Miner Wallet | Mining rewards | 48767 |
| Test Wallet | User wrap/unwrap testing | 48768 |
| Bridge Wallet | Bridge operator | 48770 |

Fund distribution is handled by `make dev-init` (base wallets) and `make dev-setup` (bridge/engine wallets + seeding). For manual funding:
```bash
$ZEPHYR_CLI send gov test 1000        # Send 1000 ZPH
$ZEPHYR_CLI send gov test 100 ZSD     # Send 100 ZSD
```

## Reset Procedures

```bash
make dev-reset                         # Reset to post-setup state (~15 sec) — use between tests
make dev-reset-hard                    # Reset to post-init state (~10 sec) — after changing EVM contracts
make dev-delete                        # Delete everything (containers, volumes, images)
```

`make dev-reset` pops Zephyr to checkpoint, wipes Anvil, resets DBs + Redis. Ready for `make dev`.

`make dev-reset-hard` restores Zephyr LMDB from init snapshots, wipes Anvil, removes addresses.json. Ready for `make dev-setup`.

`make dev-delete` removes containers, volumes, and images. You'll need `make dev-init` to start over.

## Manual Bridge Setup

> `make dev` handles this automatically. Manual steps are for reference only.

```bash
cd $ROOT/zephyr-bridge
npm install
cp .env.example .env.local
# Edit .env.local (see below)
npx prisma migrate dev

# UI only
npm run dev
# UI + all listeners
BOOTSTRAP_ZEPHYR_LISTENER=1 BOOTSTRAP_CLAIM_WATCHER=1 BOOTSTRAP_UNWRAP_WATCHER=1 npm run dev
```

Key `.env.local` variables:
```bash
BRIDGE_ENV=local
NEXT_PUBLIC_BRIDGE_ENV=local
EVM_RPC_HTTP=http://127.0.0.1:8545
REDIS_HOST=localhost
REDIS_PORT=6380
REDIS_DB=6
ZEPH_WALLET_RPC_PORT=48769
DATABASE_URL=postgresql://zephyr:$POSTGRES_PASSWORD@localhost:5432/zephyrbridge_dev
```

## Manual Engine Setup

> `make dev` handles this automatically. Manual steps are for reference only.

```bash
cd $ROOT/zephyr-bridge-engine
pnpm install
cp .env.example .env
# Edit .env (see below)
pnpm db:generate && pnpm db:migrate

pnpm worker:run     # Watchers only
pnpm dev:web        # Dashboard only
```

Key `.env` variables:
```bash
ZEPHYR_ENV=local
RPC_URL_LOCAL=http://127.0.0.1:8545
ZEPHYR_D_RPC_URL=http://127.0.0.1:47767
MEXC_PAPER=true
DATABASE_URL=postgresql://zephyr:$POSTGRES_PASSWORD@localhost:5432/zephyr_bridge_arb
```

## Manual Contract Deployment

> `make dev-setup` handles this automatically via `./scripts/deploy-contracts.sh`.

```bash
cd $ROOT/zephyr-eth-foundry
export RPC_URL=http://127.0.0.1:8545
export DEPLOYER_KEY=$DEPLOYER_PRIVATE_KEY   # From .env (generated by make keygen)
./scripts/deploy_all_test_env1.sh
```

## Startup Order

> Handled automatically by `make dev-init` / `make dev-setup` / `make dev`.

1. Redis, PostgreSQL
2. Anvil
3. Zephyr nodes + wallets
4. Deploy contracts (`dev-setup` only)
5. Bridge + Engine apps
6. Seed liquidity (`dev-setup` only)

## Configuration Sync

The `.env` file is the master config. Run `./scripts/sync-env.sh` to propagate to sub-repos.

Cross-repo sync requirements:

| Source | Destination | Data |
|--------|-------------|------|
| `zephyr-eth-foundry/.forge-snapshots/addresses.json` | `zephyr-bridge/config/addresses.local.json` | Contract addresses |
| Anvil mnemonic | All `.env` files | Same accounts/keys |
| Zephyr bridge wallet address | `bridge:accounts` Redis mapping | EVM address -> Zephyr pubkey |

Variables that must match across bridge and engine:
```bash
BRIDGE_ENV / ZEPHYR_ENV           # local | sepolia | mainnet
EVM_RPC_HTTP / RPC_URL_<ENV>      # Same RPC endpoint
EVM_CHAIN_ID                      # 31337 | 11155111 | 1
ZEPH_WALLET_RPC_PORT              # 48770 for DEVNET (bridge wallet)
```

## EVM Wallet Accounts

| Index | Role | Notes |
|-------|------|-------|
| 0 | Deployer | Contract deployments, admin |
| 1 | Bridge Signer | Signs vouchers (BRIDGE_PK) |
| 2 | Faucet Signer | Optional mock token minting |
| 3-9 | Test Users | Wrap/unwrap flows |

Local (Anvil): Pre-funded with 10,000 ETH each.

## Multi-Environment Testing

The stack can target different EVM environments while sharing the same Zephyr chain.

| Environment | EVM Chain | Use Case |
|-------------|-----------|----------|
| Local | Anvil (31337) | Day-to-day development |
| Sepolia | Sepolia testnet (11155111) | Integration testing |
| Mainnet | Ethereum (1) | Production |

Each environment needs a **separate bridge wallet** to avoid state confusion.

### Sepolia Setup

```bash
# Separate bridge wallet
./zephyr-wallet-rpc --rpc-bind-port 17780 --wallet-file sepoliabridge --password "" \
  --disable-rpc-login --trusted-daemon

# Deploy contracts
cd $ROOT/zephyr-eth-foundry
RPC_URL=https://eth-sepolia.g.alchemy.com/v2/<KEY> DEPLOYER_KEY=<key> ./scripts/deploy_all_test_env1.sh
```

Bridge `.env.local` for Sepolia:
```bash
BRIDGE_ENV=sepolia
NEXT_PUBLIC_BRIDGE_ENV=sepolia
EVM_RPC_HTTP=https://eth-sepolia.g.alchemy.com/v2/<KEY>
EVM_CHAIN_ID=11155111
ZEPH_WALLET_RPC_PORT=17780
```

### Mainnet Notes

- Real funds at risk — no state resets
- `BRIDGE_PK` should NOT be in env files — use secure key management
- Contract upgrades require careful planning

## Known Pain Points

- ~~Manual startup sequence with 10+ terminals~~ (solved: `make dev`)
- ~~No single command to start/stop/reset~~ (solved: `make dev` / `make dev-stop` / `make dev-reset`)
- Config files must be manually synchronized across repos (`make sync-env` helps)
- ~~State persistence is fragile across restarts~~ (solved: Anvil `--state` flag persists EVM state)
- Test user EVM <-> Zephyr address mapping requires manual bridge account setup
- MetaMask is clunky for rapid multi-account testing
