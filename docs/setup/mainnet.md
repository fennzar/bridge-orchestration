# Zephyr Bridge Stack - Mainnet Deployment

> **Status: NOT READY.** The production compose file (`docker/compose.prod.yml`) is a skeleton. This doc outlines the target architecture and what needs to be completed before mainnet deployment.

## Target Architecture

Mainnet differs from dev/testnet in several critical ways:

| Aspect | Dev/Testnet | Mainnet |
|--------|------------|---------|
| Zephyr chain | DEVNET (fake, controllable) | Real mainnet |
| Zephyr nodes | 2 nodes (devnet mode) | 1 node (connects to real network) |
| Wallets | gov, miner, test | Bridge wallet only |
| Oracle | Fake (controllable) | None (real oracle in chain) |
| Orderbook | Fake (tracks oracle) | Real MEXC connection |
| EVM chain | Anvil / Sepolia | Ethereum mainnet (chain 1) |
| Funds | Test funds, no value | Real funds at risk |

## What Exists

- `docker/compose.prod.yml` — skeleton compose file
- App Dockerfiles — same as testnet (bridge, engine, dashboard)
- Caddy config — `Caddyfile.prod` needs to be created (copy from testnet)

## What's Missing

Before mainnet deployment:

1. **`docker/compose.prod.yml`** — complete the skeleton:
   - Health checks for mainnet Zephyr node
   - Proper restart policies
   - Resource limits
   - Logging configuration

2. **`docker/caddy/Caddyfile.prod`** — create from testnet template

3. **`env/.env.prod`** — production environment config:
   - `BRIDGE_ENV=mainnet`
   - `EVM_RPC_HTTP` pointing to mainnet RPC
   - `EVM_CHAIN_ID=1`
   - Bridge signer key (use secure key management, NOT env file)

4. **`zephyr-mainnet` Docker image** — mainnet Zephyr binaries (no `--devnet` flag)

5. **Make targets** — `prod-build`, `prod-up`, `prod-down` (mirror testnet targets)

6. **Monitoring** — health checks, alerting, log aggregation

7. **Key management** — `BRIDGE_PK` must NOT be in an env file. Use:
   - Docker secrets
   - HashiCorp Vault
   - AWS KMS / GCP KMS
   - Or hardware wallet signing

## Compose Structure (Current Skeleton)

```yaml
# Real mainnet node (no --devnet, no --fixed-difficulty)
zephyr-node1:
  image: zephyr-mainnet
  # Ports: p2p 18080, rpc 18081, zmq 18082

# Single bridge wallet (no gov/miner/test)
wallet-bridge:
  image: zephyr-mainnet
  # Port: 17777

# App containers (same images as testnet)
bridge-web, bridge-api, bridge-watchers
engine-web, engine-watchers  # (optional, can run on separate server)

# TLS
caddy  # Caddyfile.prod (needs to be created)
```

No fake services. No second node. No test wallets.

## Security Considerations

- Private keys must never be in env files or git
- Bridge wallet file must be backed up securely
- Zephyr node RPC must not be exposed publicly
- Database must use strong passwords and TLS
- Caddy/nginx must be the only public-facing service — firewall all app ports
- Engine (if deployed) should be on a separate server with its own security boundary
- **If using Anvil** (testnet only): the `rpc-filter.mjs` proxy is mandatory for public-facing deployments — see [testnet-v2.md](./testnet-v2.md#security-rpc-filter-proxy) for details on the attack vector and proxy setup
