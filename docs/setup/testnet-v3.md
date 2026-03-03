# Zephyr Bridge Stack - Testnet V3 (Sepolia)

Deploys the bridge stack with Sepolia as the EVM chain for pre-mainnet validation. No local Anvil — contracts must be deployed to Sepolia separately.

> For Anvil-based testing with full EVM control, see [testnet-v2.md](./testnet-v2.md) (Testnet V2).

## Quick Start

```bash
# 1. Build all images (infra + app containers)
make testnet-v3-build

# 2. Configure environment
cp env/.env.testnet-v3.example env/.env.testnet-v3
# Edit env/.env.testnet-v3 — fill in Sepolia RPC, keys, domain

# 3. Init Zephyr DEVNET chain (first time only)
make testnet-v3-up PROFILE=init
# Wait for init to complete, then:
make testnet-v3-down

# 4. Deploy EVM contracts to Sepolia
cd $ROOT/zephyr-eth-foundry
RPC_URL=<sepolia-rpc> DEPLOYER_KEY=<key> ./scripts/deploy_all_test_env1.sh

# 5. Start the stack
make testnet-v3-up                       # All services (default: --profile full)
make testnet-v3-up APPS=bridge           # Bridge only
make testnet-v3-up APPS=bridge,engine    # Bridge + engine
```

## What's Different from Dev

| Aspect | Dev (`make dev`) | Testnet V3 (`make testnet-v3-up`) |
|--------|-----------------|----------------------------------|
| EVM chain | Anvil (local, chain 31337) | Sepolia (chain 11155111) |
| Apps run via | Overmind (native, hot-reload) | Docker containers |
| TLS | None (http://localhost) | Caddy + Let's Encrypt |
| Ports | All exposed on localhost | Internal only, Caddy on 80/443 |
| Env file | `.env` (root) | `env/.env.testnet-v3` |
| Contract deploy | Automatic (`make dev-init`) | Manual (Sepolia, costs gas) |

Zephyr infrastructure is the same — DEVNET nodes, fake oracle, fake orderbook. The difference is apps are containerized and EVM points to Sepolia.

## Prerequisites

Everything from the [dev setup](./dev.md) plus:

- A server with ports 80/443 open (for Caddy TLS)
- A domain pointing to the server (e.g. `bridge.example.com`)
- Sepolia RPC endpoint (Infura, Alchemy, etc.)
- Sepolia ETH for deployer + bridge signer accounts
- Deployed contracts on Sepolia

## Configuration

Copy and fill in the testnet V3 env file:

```bash
cp env/.env.testnet-v3.example env/.env.testnet-v3
```

Key values to set:

```bash
# Domain (Caddy uses this for Let's Encrypt)
DOMAIN=bridge.example.com

# Sepolia RPC
EVM_RPC_HTTP=https://sepolia.infura.io/v3/YOUR_KEY
EVM_RPC_WS=wss://sepolia.infura.io/ws/v3/YOUR_KEY
EVM_CHAIN_ID=11155111

# Keys (generate your own!)
DEPLOYER_ADDRESS=0x...
DEPLOYER_PRIVATE_KEY=0x...
BRIDGE_SIGNER_ADDRESS=0x...
BRIDGE_PK=0x...

# WalletConnect (required for frontend)
NEXT_PUBLIC_WALLETCONNECT_PROJECT_ID=your-project-id
```

Infrastructure variables (Redis, Postgres, Zephyr) use Docker service names and don't need changing.

## Make Targets

```bash
make testnet-v3-build                    # Build all images (infra + apps)
make testnet-v3-up                       # Start full stack (--profile full)
make testnet-v3-up APPS=bridge           # Bridge services only
make testnet-v3-up APPS=bridge,engine    # Bridge + engine
make testnet-v3-up PROFILE=full          # Explicit profile
make testnet-v3-down                     # Stop everything
make testnet-v3-logs SERVICE=bridge-api  # Tail container logs
```

## Architecture

```
                    Internet
                       |
                   +-------+
                   | Caddy  |  :80/:443 (Let's Encrypt)
                   +---+---+
          +------------+------------+
          |            |            |
    bridge.domain  engine.domain  status.domain
          |            |            |
    +-----+-----+  +--+--+    +---+---+
    |bridge-web |  |eng- |    |dash-  |
    |bridge-api |  |ine  |    |board  |
    |bridge-    |  |     |    |       |
    |watchers   |  |     |    |       |
    +-----+-----+  +--+--+    +------+
          |            |
    +-----+------------+--------+
    |  Redis / Postgres         |
    |  Zephyr Nodes/Wallets     |
    |  Fake Oracle/Orderbook    |
    +---------------------------+
           |
     Sepolia RPC (external)
```

### Compose Profiles

| Profile | Services |
|---------|----------|
| `bridge` | bridge-web, bridge-api, bridge-watchers, caddy |
| `engine` | engine-web, engine-watchers |
| `full` | All of the above + dashboard |
| `init` | devnet-init container (first-time setup) |

### URLs (with Caddy)

| Service | URL |
|---------|-----|
| Bridge UI | `https://bridge.example.com` |
| Bridge API | `https://bridge.example.com/api/*` |
| Engine | `https://engine.bridge.example.com` |
| Dashboard | `https://status.bridge.example.com` |

## Deploy Contracts to Sepolia

Contracts must be deployed to Sepolia separately (not automated like dev). This costs Sepolia ETH.

```bash
cd $ROOT/zephyr-eth-foundry
export RPC_URL=https://sepolia.infura.io/v3/YOUR_KEY
export DEPLOYER_KEY=0x...your-sepolia-funded-key...
./scripts/deploy_all_test_env1.sh
```

Update `env/.env.testnet-v3` with the deployed contract addresses if needed.

> Fund the deployer account with Sepolia ETH first: [sepoliafaucet.com](https://sepoliafaucet.com/), [Alchemy faucet](https://www.alchemy.com/faucets/ethereum-sepolia)

## Init Zephyr Chain

The Zephyr DEVNET chain needs to be initialized once (same as dev, but via compose profile):

```bash
# Start infra + run init container
make testnet-v3-up PROFILE=init

# Watch init progress
make testnet-v3-logs SERVICE=devnet-init

# After init completes, bring everything down and start normally
make testnet-v3-down
make testnet-v3-up
```

## Updating

```bash
# Rebuild app images after code changes
make testnet-v3-build

# Restart with new images
make testnet-v3-down && make testnet-v3-up
```

## Troubleshooting

**Caddy won't start / TLS errors:**
- Verify domain DNS points to this server
- Ports 80 and 443 must be open (no other reverse proxy in front)
- Check Caddy logs: `make testnet-v3-logs SERVICE=caddy`

**Sepolia RPC errors:**
- Verify `EVM_RPC_HTTP` and `EVM_RPC_WS` in `env/.env.testnet-v3`
- Check rate limits on your RPC provider

**Bridge watchers not connecting:**
- Zephyr nodes must be healthy first: `make testnet-v3-logs SERVICE=zephyr-node1`
- Check bridge-watchers logs: `make testnet-v3-logs SERVICE=bridge-watchers`
