# Zephyr Bridge Stack - Testnet V2 (Production Build Mode)

Same infrastructure as dev mode (Docker Compose for infra, Overmind for apps), but apps run from production builds (`pnpm build` -> `pnpm start`) instead of hot-reload dev mode.

Uses a separate Procfile (`Procfile.prod`) and Overmind socket (`.overmind-prod.sock`). Cannot coexist with `make dev` — stop one before starting the other.

> For Sepolia pre-mainnet validation, see [testnet-v3.md](./testnet-v3.md).

## Quick Start

```bash
# 1. First time setup (same as dev — make setup includes keygen)
make testnet-v2-init                 # Base Zephyr devnet (~4 min)
make testnet-v2-setup                # Bridge infra + contracts + seed (~4 min)

# 2. Build all apps for production
make testnet-v2-build

# 3. Start the stack
make testnet-v2                      # All services
make testnet-v2 APPS=bridge          # Bridge only
make testnet-v2 APPS=bridge,engine   # Bridge + engine
```

## What's Different from Dev

| Aspect | Dev (`make dev`) | Testnet V2 (`make testnet-v2`) |
|--------|-----------------|-------------------------------|
| Procfile | `Procfile.dev` (hot-reload) | `Procfile.prod` (production builds) |
| Bridge web | `pnpm dev:web` | `pnpm start:web` |
| Bridge API | `pnpm dev:api` | `pnpm start:api` |
| Bridge watchers | `pnpm dev:watchers` | `pnpm run "/^start:watcher:.*/"` |
| Engine web | `pnpm --dir apps/web dev` | `pnpm start:web` |
| Dashboard | `pnpm dev` | `pnpm start` |
| Overmind socket | `.overmind-dev.sock` | `.overmind-prod.sock` |
| Build step | None (hot-reload) | `make testnet-v2-build` required |

Infrastructure (Docker Compose), ports, volumes, and env file (`.env`) are all identical.

## Make Targets

```bash
# Lifecycle (mirrors dev commands)
make testnet-v2-init                 # Base Zephyr devnet, then stop
make testnet-v2-setup                # Bridge infra on top, then stop
make testnet-v2-build                # Build all apps (pnpm build)
make testnet-v2                      # Start the stack
make testnet-v2 APPS=bridge          # Start specific app groups
make testnet-v2-stop                 # Stop everything (preserves data)

# Reset
make testnet-v2-reset                # Reset to post-setup state, then stop
make testnet-v2-reset-hard           # Reset to post-init state, then stop

# Cleanup
make testnet-v2-delete               # Delete everything (containers, volumes)
make testnet-v2-logs SERVICE=x       # Tail logs
```

## Default Workflow

```bash
# First time:
make testnet-v2-init && make testnet-v2-setup
make testnet-v2-build && make testnet-v2

# Between tests:
make testnet-v2-reset && make testnet-v2

# After code changes:
make testnet-v2-build && make testnet-v2

# After changing EVM contracts:
make testnet-v2-reset-hard && make testnet-v2-setup
make testnet-v2-build && make testnet-v2

# Done for the day:
make testnet-v2-stop

# Next day:
make testnet-v2
```

## Ports

Same as dev mode — all services run on localhost:

| Service | Port |
|---------|------|
| Bridge Web UI | 7050 |
| Bridge API | 7051 |
| Engine | 7000 |
| Dashboard | 7100 |
| Anvil (EVM) | 8545 |
| Blockscout | 4000 |

## Troubleshooting

**Apps won't start / "module not found":**
- Run `make testnet-v2-build` first — production mode requires build output.

**Bridge web shows blank page:**
- The `.next` build directory must exist. If it was cleaned (e.g. by `make dev-reset`), rebuild with `make testnet-v2-build`.
- Note: `make testnet-v2-reset` preserves the `.next` directory automatically.

**Switching between dev and testnet-v2:**
- Stop the current mode first (`make dev-stop` or `make testnet-v2-stop`).
- They share the same Docker infrastructure but use different Overmind sockets.
