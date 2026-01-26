# Zephyr Bridge Stack - DEVNET Development Environment

## Quick Start

```bash
# One-time prerequisites
cp .env.example .env                   # Review ROOT path
./scripts/sync-zephyr-artifacts.sh     # Vendor Zephyr binaries (once, or after Zephyr repo updates)

# Start (auto-inits on first run — builds, inits chain, deploys, starts everything)
make dev                               # ~5 min first time, ~10s after

# Between tests (~30 sec)
make dev-reset                         # Reset all layers to post-init state

# Stop everything (data preserved for next `make dev`)
make dev-stop

# Delete everything (containers, volumes, images)
make dev-delete
```

That's it. `make dev` handles everything: on first run it builds Docker images, starts infrastructure, bootstraps the Zephyr chain, deploys EVM contracts, pushes DB schemas, and starts apps. On subsequent runs it just starts infra + apps. You do not need to run `docker compose`, deploy scripts, or DB migrations manually.

## Selective App Startup

Don't need the full stack? Use `APPS=` to start only what you're working on:

```bash
make dev APPS=bridge              # Bridge only (bridge-web, bridge-api, bridge-watchers)
make dev APPS=engine              # Engine only (engine-web, engine-watchers)
make dev APPS=bridge,engine       # Bridge + engine, no dashboard
make dev APPS=bridge,dashboard    # Bridge + dashboard
```

Infrastructure (Docker Compose) always starts fully regardless of `APPS=`.

## Daily Workflow

```bash
make status                            # Health check (containers, processes, chain heights)
make dev-reset                         # Reset all layers to post-init state
make dev-reset-zephyr                  # Zephyr chain only
make dev-reset-evm                     # Anvil + contracts only
make dev-reset-db                      # Postgres + Redis only
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
./scripts/verify.sh      # Automated prerequisite check
```

## Architecture

Two-layer stack:

- **Docker Compose** (`make dev-infra`): Zephyr nodes, wallets, oracle, orderbook, Redis, Postgres, Anvil
- **Overmind** (`make dev-apps`): bridge-web, bridge-api, bridge-watchers, engine-web, engine-watchers, dashboard

`make dev` starts both. `make dev-stop` stops both.

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

---

# Reference

Everything below is for understanding what's happening under the hood. You don't need any of this for normal development — `make dev` handles it all.

## What `make dev` Does

1. Builds Docker images if missing (checks for `zephyr-devnet` image)
2. Starts Docker Compose infrastructure (Redis, Postgres, Anvil, Zephyr nodes, wallets, oracle, orderbook)
3. **If first run** (no checkpoint found):
   - Runs `devnet-init` container — bootstraps fresh Zephyr chain, creates wallets, funds them, starts mining, saves checkpoint
   - Wipes Anvil state + deploys all EVM contracts (mock tokens, wrapped Zephyr tokens, Uniswap V4 pools)
   - Pushes Prisma DB schemas for bridge and engine
4. Starts Overmind app processes

On subsequent runs, steps 1 and 3 are skipped — it just starts infra + apps.

## What `make dev-init` Does

Nuclear option — stops everything, destroys all Docker volumes (chain data, DBs, Redis, Anvil state), rebuilds images, then runs the full initialization sequence unconditionally: starts infrastructure, bootstraps Zephyr chain, deploys EVM contracts, pushes DB schemas, starts apps.

## What `make dev-delete` Does

Stops everything and deletes all containers, volumes, and built Docker images. Does not rebuild or restart anything — leaves a completely clean slate. Run `make dev-init` afterward to set up from scratch.

## Sync Zephyr Artifacts

Required once after cloning (and again when the Zephyr repo updates):

```bash
# Requires ../zephyr or ZEPHYR_REPO_PATH in .env
./scripts/sync-zephyr-artifacts.sh
```

Copies into this repo:
- **Devnet binaries** (`zephyrd`, `zephyr-wallet-rpc`) -> `docker/zephyr/bin/`
- **Fake oracle files** (`server.js`, PEM keys) -> `docker/fake-oracle/`
- **Fresh-devnet tooling** -> `tools/fresh-devnet/`
- **Zephyr CLI** -> `tools/zephyr-cli/`

Binaries (~34MB each) are gitignored. Use `--force` to overwrite, `--no-build` to skip C++ compilation.

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
| `zephyrbridge_dev` | `zephyr` | `zephyr` | Bridge app |
| `zephyr_bridge_arb` | `zephyr` | `zephyr` | Engine |

Redis runs in Docker on host port 6380 (container 6379, DB 6).

## EVM Contracts

Deployed automatically by `make dev-init` via `./scripts/deploy-contracts.sh`. Includes:
- Mock stablecoins (USDC, USDT)
- Wrapped Zephyr tokens (wZEPH, wZSD, wZRS, wZYS)
- Uniswap V4 stack (PoolManager, routers)
- Liquidity pools (USDT-USDC, wZSD-USDT, wZYS-wZSD, wZEPH-wZSD, wZRS-wZEPH)

Addresses saved to `config/addresses.local.json`.

> This project uses a **custom mnemonic** (`EVM_DEV_MNEMONIC` in `.env`), NOT the default Foundry mnemonic. See [metamask.md](../reference/metamask.md) for actual accounts.

## Zephyr Wallets

All managed by Docker Compose, started automatically.

| Wallet | Purpose | Port |
|--------|---------|------|
| Gov Wallet | Main funds, bridge operations | 48769 |
| Miner Wallet | Mining rewards | 48767 |
| Test Wallet | User wrap/unwrap testing | 48768 |
| Bridge Wallet | Bridge operator | 48770 |

Fund distribution is handled by `make dev-init`. For manual funding:
```bash
$ZEPHYR_CLI send gov test 1000        # Send 1000 ZPH
$ZEPHYR_CLI send gov test 100 ZSD     # Send 100 ZSD
```

## Reset Procedures

```bash
make dev-reset                         # Full coordinated reset (~30 sec) — use between tests
make dev-reset-zephyr                  # Zephyr only: pop blocks to checkpoint
make dev-reset-evm                     # EVM only: wipe Anvil state + redeploy contracts
make dev-reset-db                      # DB only: Postgres force-reset + Redis flush
make dev-init                          # Full fresh init (~5 min) — nuclear option
make dev-delete                        # Delete everything, no rebuild
```

`make dev-reset` coordinates all layers: Zephyr chain pop + Anvil wipe + contract redeploy + DB reset + Redis flush. Use scoped variants when you only need to reset one layer.

`make dev-delete` is for when you want to free disk space or start completely from zero. It removes containers, volumes, and built images. You'll need `make dev-init` to use the stack again afterward.

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
DATABASE_URL=postgresql://zephyr:zephyr@localhost:5432/zephyrbridge_dev
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
DATABASE_URL=postgresql://zephyr:zephyr@localhost:5432/zephyr_bridge_arb
```

## Manual Contract Deployment

> `make dev-init` handles this automatically via `make deploy-contracts`.

```bash
cd $ROOT/zephyr-eth-foundry
export RPC_URL=http://127.0.0.1:8545
export DEPLOYER_KEY=0x860875f05874e1ac2207f147a7a3e2a13d66520936cb598528e9104f2d5ec990
./scripts/deploy_all_test_env1.sh
```

## Startup Order

> Handled automatically by `make dev-init` / `make dev`.

1. Redis, PostgreSQL
2. Anvil
3. Deploy contracts (if fresh)
4. Zephyr Node 2 (primary), Node 1 (peer)
5. Zephyr Wallets (after nodes sync)
6. Bridge (after infra ready)
7. Engine (after bridge)

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
