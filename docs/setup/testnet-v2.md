# Zephyr Bridge Stack - Testnet V2 (Production Build Mode)

Same infrastructure as dev mode (Docker Compose for infra, Overmind for apps), but apps run from production builds (`pnpm build` -> `pnpm start`) instead of hot-reload dev mode.

Uses a separate Procfile (`Procfile.prod`) and Overmind socket (`.overmind-prod.sock`). Cannot coexist with `make dev` — stop one before starting the other.

> For Sepolia pre-mainnet validation, see [testnet-v3.md](./testnet-v3.md).

## Quick Start

```bash
# 1. First time setup (same as dev — make setup includes keygen)
make testnet-v2-init                 # Base Zephyr devnet (~4 min)
make testnet-v2-setup                # Bridge infra + contracts + seed (~4 min)

# 2. Start the stack (auto-builds via turbo — cached when nothing changed)
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
| Build step | None (hot-reload) | Auto-builds on `make testnet-v2` (turbo-cached) |

Infrastructure (Docker Compose), ports, volumes, and env file (`.env`) are all identical.

## Make Targets

```bash
# Lifecycle (mirrors dev commands)
make testnet-v2-init                 # Base Zephyr devnet, then stop
make testnet-v2-setup                # Bridge infra on top, then stop
make testnet-v2                      # Sync env + build + start (turbo-cached)
make testnet-v2 APPS=bridge          # Start specific app groups
make testnet-v2-build                # Build only (no start)
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
make testnet-v2-init && make testnet-v2-setup && make testnet-v2

# Between tests:
make testnet-v2-reset && make testnet-v2

# After code changes (turbo rebuilds only what changed):
make testnet-v2

# After changing EVM contracts:
make testnet-v2-reset-hard && make testnet-v2-setup && make testnet-v2

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
| RPC Filter Proxy | 8546 |
| Blockscout | 4000 |

## Remote Server Deployment

When deploying testnet-v2 to a public-facing server, additional hardening is required. Anvil's RPC endpoint allows arbitrary code execution if exposed — see [Security: RPC Filter Proxy](#security-rpc-filter-proxy) below.

### Server Setup Checklist

1. **Firewall** — only expose SSH (22) and your reverse proxy (80/443). Block all app ports:
   ```bash
   ufw default deny incoming
   ufw allow 22/tcp
   ufw allow 'Nginx Full'    # or 80/tcp and 443/tcp
   ufw enable
   ```
   Never open 8545 (Anvil), 4000 (Blockscout), 7000/7050/7051/7100 (apps), or 47767 (Zephyr RPC) to the internet.

2. **Reverse proxy (nginx)** — terminate TLS and proxy to localhost services:
   ```nginx
   # Anvil EVM RPC — MUST go through the filter proxy (port 8546), never direct to 8545
   location = /rpc/evm {
       proxy_pass http://127.0.0.1:8546/;
       proxy_http_version 1.1;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
   }

   # Bridge API (supports SSE streams)
   location /api/ {
       proxy_pass http://127.0.0.1:7051/;
       proxy_buffering off;
       proxy_cache off;
       proxy_read_timeout 86400;
   }

   # Bridge UI (catch-all)
   location / {
       proxy_pass http://127.0.0.1:7050;
   }
   ```

3. **Environment overrides** — set these in `.env` before running `sync-env.sh`:
   ```bash
   PUBLIC_HOST=your-server-ip-or-domain
   PUBLIC_PROTOCOL=https
   NEXT_PUBLIC_ANVIL_RPC=https://your-domain.com/rpc/evm
   NEXT_PUBLIC_API_URL=https://your-domain.com/api
   NEXT_PUBLIC_ANVIL_EXPLORER_URL=http://your-server-ip:4000  # or omit if Blockscout is not exposed
   ```

4. **Start the stack** — same as local, plus the RPC filter runs automatically via Procfile:
   ```bash
   make testnet-v2-init && make testnet-v2-setup && make testnet-v2
   ```

### Security: RPC Filter Proxy

Foundry's Anvil is a development tool — it auto-signs transactions with dev accounts and supports cheatcodes like `vm.ffi()` that execute arbitrary shell commands on the host. **Exposing Anvil's RPC port (8545) to the internet allows full remote code execution.**

The `rpc-filter.mjs` proxy (managed by Overmind, listening on `127.0.0.1:8546`) sits between nginx and Anvil to allowlist only safe JSON-RPC methods:

| Allowed | Blocked |
|---------|---------|
| `eth_chainId`, `eth_blockNumber`, `eth_call`, `eth_getBalance`, `eth_getLogs`, etc. | `eth_sendTransaction` (Anvil auto-signs with dev keys) |
| `eth_sendRawTransaction` (wallet-signed, safe) | `anvil_*` (admin/cheatcode methods) |
| `eth_estimateGas`, `eth_gasPrice`, `eth_feeHistory` | `debug_*`, `evm_*` (state manipulation) |
| `net_version`, `web3_clientVersion` | Any unlisted method |

MetaMask and other wallets work normally — they use `eth_sendRawTransaction` which sends pre-signed transactions. The blocked method is `eth_sendTransaction`, which tells Anvil to sign with its own dev accounts (the exploit vector).

Blockscout's `/api/eth-rpc` endpoint also proxies to Anvil and is a secondary attack vector. Either don't expose Blockscout publicly, or firewall port 4000.

**The filter proxy runs as part of the Overmind Procfile** — no separate systemd service is needed. It starts and stops with the rest of the stack.

## Troubleshooting

**Apps won't start / "module not found":**
- `make testnet-v2` auto-builds, but if builds are stale, run `make testnet-v2-stop && make testnet-v2` to force a fresh sync + rebuild.

**Bridge web shows wrong host/IP:**
- `NEXT_PUBLIC_*` vars are baked at build time. After changing `PUBLIC_HOST` in `.env`, run `make testnet-v2` — the auto-build picks up the new values.
- Note: `make testnet-v2-reset` preserves the `.next` directory automatically.

**Switching between dev and testnet-v2:**
- Stop the current mode first (`make dev-stop` or `make testnet-v2-stop`).
- They share the same Docker infrastructure but use different Overmind sockets.
