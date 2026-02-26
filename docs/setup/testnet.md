# Zephyr Bridge Stack - Testnet V2 (Anvil)

Deploys the bridge stack with a local Anvil EVM chain, containerized apps, Caddy TLS, and Blockscout block explorer. Full control over EVM state with aggressive resets.

> For Sepolia pre-mainnet validation, see [testnet-v3.md](./testnet-v3.md).

## Quick Start

```bash
# 1. Build all images (infra + app containers)
make testnet-v2-build

# 2. Configure environment
cp env/.env.testnet-v2.example env/.env.testnet-v2
# Edit env/.env.testnet-v2 — fill in domain, keys

# 3. Start the stack (Anvil + apps + Blockscout)
make testnet-v2-up                    # All services
make testnet-v2-up APPS=bridge        # Bridge only
make testnet-v2-up APPS=bridge,engine # Bridge + engine
```

## What's Different from Dev

| Aspect | Dev (`make dev`) | Testnet V2 (`make testnet-v2-up`) |
|--------|-----------------|----------------------------------|
| EVM chain | Anvil (local, chain 31337) | Anvil (remote, chain 31337) |
| Apps run via | Overmind (native, hot-reload) | Docker containers |
| TLS | None (http://localhost) | Caddy + Let's Encrypt |
| Ports | All exposed on localhost | Internal only, Caddy on 80/443 |
| Env file | `.env` (root) | `env/.env.testnet-v2` |
| Explorer | Blockscout (opt-out via `EXPLORER=0`) | Blockscout (always-on) |

## Environment Matrix

| Env | EVM Chain | Apps Run Via | Explorer | Make Targets |
|-----|-----------|-------------|----------|--------------|
| **Dev** | Anvil (local) | Overmind (hot-reload) | Blockscout (opt-out) | `make dev` |
| **Testnet V2** | Anvil (remote) | Docker containers | Blockscout (always-on) | `make testnet-v2-*` |
| **Testnet V3** | Sepolia RPC | Docker containers | Etherscan (external) | `make testnet-v3-*` |

## Prerequisites

Everything from the [dev setup](./dev.md) plus:

- A server with ports 80/443 open (for Caddy TLS)
- A domain pointing to the server (e.g. `bridge.example.com`)
- Subdomains: `engine.`, `status.`, `explorer.` pointing to same server

## Configuration

Copy and fill in the testnet V2 env file:

```bash
cp env/.env.testnet-v2.example env/.env.testnet-v2
```

Key values to set:

```bash
# Domain (Caddy uses this for Let's Encrypt)
DOMAIN=bridge.example.com

# Keys (from make keygen or generate your own)
DEPLOYER_ADDRESS=0x...
DEPLOYER_PRIVATE_KEY=0x...
BRIDGE_SIGNER_ADDRESS=0x...
BRIDGE_PK=0x...

# Blockscout (uses domain-based URLs via Caddy)
BLOCKSCOUT_API_HOST=explorer.bridge.example.com
BLOCKSCOUT_API_PROTOCOL=https
```

Infrastructure variables (Redis, Postgres, Zephyr, Anvil) use Docker service names and don't need changing.

## Make Targets

```bash
make testnet-v2-build                    # Build all images (infra + apps)
make testnet-v2-up                       # Start full stack + Blockscout
make testnet-v2-up APPS=bridge           # Bridge services only + Blockscout
make testnet-v2-up APPS=bridge,engine    # Bridge + engine + Blockscout
make testnet-v2-down                     # Stop everything
make testnet-v2-logs SERVICE=bridge-api  # Tail container logs
```

## Architecture

```
                    Internet
                       |
                   +-------+
                   | Caddy  |  :80/:443 (Let's Encrypt)
                   +---+---+
          +------------+------------+-----------+
          |            |            |           |
    bridge.domain  engine.domain  status.   explorer.
          |            |          domain    domain
    +-----+-----+  +--+--+    +------+  +----------+
    |bridge-web |  |eng- |    |dash- |  |blockscout |
    |bridge-api |  |ine  |    |board |  |proxy      |
    |bridge-    |  |     |    |      |  |  +API     |
    |watchers   |  |     |    |      |  |  +frontend|
    +-----+-----+  +--+--+    +------+  +----+-----+
          |            |                      |
    +-----+------------+----------------------+--+
    |  Anvil / Redis / Postgres                  |
    |  Zephyr Nodes/Wallets                      |
    |  Fake Oracle/Orderbook                     |
    |  Blockscout DB                             |
    +--------------------------------------------+
```

### Compose Profiles

| Profile | Services |
|---------|----------|
| `bridge` | bridge-web, bridge-api, bridge-watchers, caddy |
| `engine` | engine-web, engine-watchers |
| `full` | All of the above + dashboard |
| `explorer` | Blockscout (always included in V2) |
| `init` | devnet-init container (first-time setup) |

### URLs (with Caddy)

| Service | URL |
|---------|-----|
| Bridge UI | `https://bridge.example.com` |
| Bridge API | `https://bridge.example.com/api/*` |
| Engine | `https://engine.bridge.example.com` |
| Dashboard | `https://status.bridge.example.com` |
| Explorer | `https://explorer.bridge.example.com` |

## Updating

```bash
# Rebuild app images after code changes
make testnet-v2-build

# Restart with new images
make testnet-v2-down && make testnet-v2-up
```

## Troubleshooting

**Caddy won't start / TLS errors:**
- Verify domain DNS points to this server (including `explorer.` subdomain)
- Ports 80 and 443 must be open (no other reverse proxy in front)
- Check Caddy logs: `make testnet-v2-logs SERVICE=caddy`

**Blockscout not indexing:**
- Ensure Anvil is healthy: `make testnet-v2-logs SERVICE=anvil`
- Check Blockscout backend logs: `make testnet-v2-logs SERVICE=blockscout-backend`
- Blockscout needs a few minutes to index existing blocks on first start

**Bridge watchers not connecting:**
- Zephyr nodes must be healthy first: `make testnet-v2-logs SERVICE=zephyr-node1`
- Check bridge-watchers logs: `make testnet-v2-logs SERVICE=bridge-watchers`
