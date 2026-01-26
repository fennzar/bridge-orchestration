# Orchestrator Testing Checklist

## Overview
This checklist verifies the bridge orchestration layer works correctly - scripts, infrastructure, and environment setup.

> **Edge-case scope:** This checklist is the primary target for `ZB-CONF` scenarios in [00-edge-case-scope.md](./00-edge-case-scope.md).
>
> **Runner:** Use `make test-l5` (or `./scripts/run-l5-tests.py`) for L5 planning/lint.
>
> **TBC note:** Any scenario marked `SCOPED-TBC` in the scope catalog still needs command-level runbook guidance before execution.

## Prerequisites

### ✅ System Requirements
- [ ] Verify all dependencies installed: `./scripts/verify.sh`
- [ ] Check disk space (need ~30GB for Zephyr data)
- [ ] Confirm all repos cloned in correct $ROOT structure
- [ ] Verify .env file exists and has correct paths

### ✅ Binary Verification
- [ ] zephyrd binary exists at $ZEPHYR_BIN_PATH/zephyrd
- [ ] zephyr-wallet-rpc binary exists at $ZEPHYR_BIN_PATH/zephyr-wallet-rpc
- [ ] Foundry installed: `forge --version` and `anvil --version`
- [ ] Docker running: `docker ps`

## Setup Scripts

### ✅ Initial Setup (`make build && make dev-init`)
- [ ] `make build` completes without errors (builds Docker images and DEVNET binaries)
- [ ] `make dev-init` starts fresh DEVNET and initializes all infrastructure
- [ ] Creates all required directories (zephyr-data, zephyr-wallets)
- [ ] Initializes Zephyr LMDB data (if available)
- [ ] Creates wallet files (.keys and cache)
- [ ] Initializes PostgreSQL database
- [ ] Configures Redis

### ✅ Infrastructure Setup (`make dev` or `make dev-init`)
- [ ] Docker containers start: Redis, PostgreSQL, Anvil
- [ ] Redis accessible on port 6379: `redis-cli ping`
- [ ] PostgreSQL accessible on port 5432
- [ ] Anvil accessible on port 8545
- [ ] Database initialized with tables

### ✅ Zephyr Setup (part of `make dev-init`)
- [ ] ~~LMDB data initialized or existing data found~~ (DEPRECATED: mainnet-fork only)
- [ ] Wallet files created (localmining, localbridge, localexchange, localtestuser)
- [ ] All wallets have .keys files (~1.7KB each)
- [ ] Can start zephyrd without errors
- [ ] Can connect wallet RPC to daemon

### ✅ App Setup (`make dev-apps`)
- [ ] zephyr-bridge dependencies installed (pnpm install)
- [ ] zephyr-bridge-engine dependencies installed (pnpm install)
- [ ] status-dashboard dependencies installed (pnpm install)
- [ ] Environment variables synced to all repos

## Service Management

### ✅ Starting Services (`make dev`)
- [ ] `make dev` runs without errors
- [ ] Docker Compose infra starts successfully
- [ ] Overmind starts app processes successfully
- [ ] All configured processes start (use `APPS=` to select groups, e.g. `make dev APPS=bridge`)
- [ ] No processes immediately crash

### ✅ Process Health Check (`make status`)
- [ ] zephyr-node1 status: Running, height increasing
- [ ] zephyr-node2 status: Running, height matches node1
- [ ] wallet-mining status: Running, connected to node1
- [ ] wallet-bridge status: Running, connected to node2
- [ ] wallet-exchange status: Running, connected to node2
- [ ] wallet-testuser status: Running, connected to node2 (if enabled)
- [ ] Redis status: Running
- [ ] PostgreSQL status: Running
- [ ] Anvil status: Running
- [ ] bridge-web status: Running (if enabled)
- [ ] engine-web status: Running (if enabled)
- [ ] status-dashboard status: Running

### ✅ Stopping Services (`make dev-stop`)
- [ ] `make dev-stop` completes gracefully
- [ ] All Zephyr processes killed
- [ ] Docker containers stopped
- [ ] No zombie processes left

### ✅ Service Interactions
- [ ] Infra logs: `make logs SERVICE=<svc>` or `docker compose logs <svc>`
- [ ] App process logs: `overmind connect <process>` (Ctrl-B D to detach)
- [ ] Can restart individual app process: `overmind restart <process>`
- [ ] Processes restart correctly after crash

## Zephyr Operations

### ✅ Daemon Functionality
- [ ] Node1 RPC responds: `curl http://localhost:47767/json_rpc -d '{"jsonrpc":"2.0","id":"0","method":"get_info"}'` *(DEVNET port; mainnet-fork port 48081 is DEPRECATED)*
- [ ] Node2 RPC responds: `curl http://localhost:47867/json_rpc -d '{"jsonrpc":"2.0","id":"0","method":"get_info"}'` *(DEVNET port; mainnet-fork port 17867 is DEPRECATED)*
- [ ] Both nodes at same height
- [ ] Can get reserve info: method `get_reserve_info`
- [ ] Pricing records present in blocks

### ✅ Wallet Functionality
- [ ] Mining wallet responds: `curl http://localhost:48767/json_rpc -d '{"jsonrpc":"2.0","id":"0","method":"get_address"}'` *(DEVNET port; mainnet-fork port 17776 is DEPRECATED)*
- [ ] Bridge wallet responds on port 48768 *(DEVNET; mainnet-fork port 17777 is DEPRECATED)*
- [ ] Can query balances for all asset types (ZPH, ZSD, ZRS, ZYS)
- [ ] Wallet heights match daemon heights

### ✅ Mining Operations
- [ ] Can start mining via wallet RPC
- [ ] Blocks are mined (height increases)
- [ ] Mining rewards appear in wallet balance
- [ ] Can stop mining
- [ ] Status Dashboard mining controls work (if available)

### ✅ Asset Transfers
- [ ] ZPH transfer between wallets works
- [ ] Transfer confirms after 60 blocks
- [ ] Balance updates correctly in both wallets

### ✅ Asset Conversions
- [ ] ZPH → ZRS conversion works (mint reserve)
- [ ] Converted ZRS appears in balance after unlock
- [ ] Can query conversion transaction on daemon
- [ ] Transaction shows amount_burnt and amount_minted fields

## EVM Operations

### ✅ Anvil (Local EVM)
- [ ] Anvil accessible: `cast block-number --rpc-url http://localhost:8545`
- [ ] Can deploy contracts
- [ ] Can query contract state
- [ ] Can send transactions
- [ ] Accounts have ETH balance

### ✅ Contract Deployment (./scripts/deploy-contracts.sh)
- [ ] Script runs without errors
- [ ] All contracts deploy successfully
- [ ] Addresses written to config/addresses.local.json
- [ ] Can verify deployment by reading contract address

### ✅ Token Contracts
- [ ] wZEPH deployed and readable
- [ ] wZSD deployed and readable
- [ ] wZRS deployed and readable
- [ ] wZYS deployed and readable
- [ ] Mock USDC deployed
- [ ] Mock USDT deployed

### ✅ Uniswap V4 Contracts
- [ ] PoolManager deployed
- [ ] Router contracts deployed
- [ ] Pools created and initialized

## Environment & Configuration

### ✅ Environment Variables
- [ ] .env file has all required variables
- [ ] Can sync env to repos: `./scripts/sync-env.sh`
- [ ] Synced env files match master .env
- [ ] No sensitive data in git (check .gitignore)

### ✅ Configuration Files
- [ ] config/addresses.local.json exists after deployment
- [ ] config/wallets.json has correct structure
- [ ] ~~Procfile has all expected processes~~ (DEPRECATED: mainnet-fork Procfile has been removed)
- [ ] Procfile.dev has all expected DEVNET app processes
- [ ] `APPS=` parameter controls which app groups start (e.g. `make dev APPS=bridge,engine`)

## Reset Operations

### ✅ Reset Zephyr (DEPRECATED: ./scripts/reset-zephyr.sh — use `make dev-reset` instead)
- [ ] ~~Stops Zephyr processes~~ (DEPRECATED: mainnet-fork only)
- [ ] ~~Backs up existing data (if configured)~~ (DEPRECATED)
- [ ] ~~Clears Zephyr data directories~~ (DEPRECATED)
- [ ] ~~Reinitializes LMDB data~~ (DEPRECATED)
- [ ] ~~Recreates wallet files~~ (DEPRECATED)

### ✅ Reset EVM (`make dev-reset-evm` or `./scripts/reset-evm.sh`)
- [ ] Wipes Anvil state file (`/data/anvil-state.json`)
- [ ] Restarts Anvil container
- [ ] Redeploys all contracts
- [ ] Engine database reset

### ✅ Full Coordinated Reset (`make dev-reset` or `./scripts/dev-reset.sh`)
- [ ] Stops Overmind apps (if running)
- [ ] Pops Zephyr blocks to checkpoint on both nodes
- [ ] Rescans wallets, restarts mining
- [ ] Wipes Anvil state + restarts container + redeploys contracts
- [ ] Force-resets Postgres databases (bridge + engine)
- [ ] Flushes Redis
- [ ] Restarts Overmind apps (if they were running)
- [ ] All layers in sync, ready for fresh test

### ✅ Scoped Resets
- [ ] `make dev-reset-zephyr` — Zephyr chain only (pop to checkpoint)
- [ ] `make dev-reset-evm` — Anvil wipe + contract redeploy only
- [ ] `make dev-reset-db` — Postgres + Redis only

## Status Dashboard

### ✅ Dashboard Access
- [ ] Dashboard accessible at http://localhost:7100
- [ ] Shows all services with correct status
- [ ] Can view process details
- [ ] Real-time updates work

### ✅ Process Controls (if implemented)
- [ ] Can start mining from dashboard
- [ ] Can stop mining from dashboard
- [ ] Can view terminal output
- [ ] Can execute commands on processes

## Bridge Application

### ✅ Bridge Web Access
- [ ] Bridge UI accessible at http://localhost:7050
- [ ] Can connect to backend
- [ ] Dashboard loads without errors

### ✅ Engine Access
- [ ] Engine UI accessible at http://localhost:7000
- [ ] Can connect to backend
- [ ] Dashboard loads without errors

## DEVNET Mode (Recommended)

### ✅ DEVNET First Start
- [ ] `make build` completes (builds Docker images and DEVNET binaries)
- [ ] `make dev-init` starts fresh DEVNET (~5-6 min)
- [ ] Fake oracle responds: `curl http://127.0.0.1:5555/status`
- [ ] Fake orderbook responds: `curl http://127.0.0.1:5556/status`
- [ ] Checkpoint saved automatically at post-init height
- [ ] Can check checkpoint: `make dev-checkpoint`

### ✅ DEVNET Reset (Use Between Tests)
- [ ] `make status` shows current vs checkpoint height
- [ ] `make dev-reset` completes in ~30 seconds
- [ ] Zephyr blocks popped back to checkpoint height
- [ ] Wallets rescanned, mining restarted
- [ ] Anvil wiped and contracts redeployed
- [ ] Postgres databases force-reset
- [ ] Redis flushed
- [ ] All layers in sync, ready for next test

### ✅ DEVNET Oracle Control
- [ ] `make set-price PRICE=15.00` sets normal price
- [ ] `make set-price PRICE=0.40` triggers crisis mode
- [ ] Fake orderbook tracks oracle price changes
- [ ] Engine sees updated prices

### ✅ DEVNET Workflow
- [ ] First time: `make dev-init` (~5-6 min)
- [ ] Between tests: `make dev-reset` (~30 sec)
- [ ] Use reset as default for repeatable test state

## Common Issues

### ✅ Troubleshooting
- [ ] Know how to check infra logs: `make logs SERVICE=<svc>` or `docker compose logs <svc>`
- [ ] Know how to check app logs: `overmind connect <process>` (Ctrl-B D to detach)
- [ ] Know how to restart crashed process
- [ ] Know how to fix "daemon is busy" (restart daemon)
- [ ] Know wallet file locations (/zephyr-wallets/)
- [ ] Know how to check if services are listening on ports
- [ ] Can access PostgreSQL: `psql -h localhost -U bridge -d bridge`
- [ ] Can access Redis: `redis-cli`

## Documentation

### ✅ Documentation Review
- [ ] README.md has quick start instructions
- [ ] README.md has quick reference and port table
- [ ] dev.md covers full setup
- [ ] All doc links work (no broken references)
- [ ] Documentation matches current implementation

<!-- L5-CATALOG-START -->
## L5 Integrated Edge-Case Catalog

This section fully integrates the scoped ZB edge-case tests that belong in this runbook.

| Total | SCOPED-READY | SCOPED-EXPAND | SCOPED-TBC |
|---:|---:|---:|---:|
| 10 | 0 | 4 | 6 |

Tests marked `SCOPED-TBC` are intentionally included now and require additional runbook detail in a follow-up pass.

### 11. Configuration Errors (10)

| ID | Test | Priority | Severity | Runbook Status | Integration Action |
|---|---|---|---|---|---|
| `ZB-CONF-001` | Wrong Zephyr daemon RPC port | P0 | High | `SCOPED-EXPAND` | Expand nearby scenario with explicit edge assertions. |
| `ZB-CONF-002` | Wrong wallet RPC port for gov wallet (unwrap fails) | P0 | High | `SCOPED-TBC` | Add detailed runbook steps (TBC). |
| `ZB-CONF-003` | Wrong Anvil WS URL (watcher-evm) | P0 | Critical | `SCOPED-EXPAND` | Expand nearby scenario with explicit edge assertions. |
| `ZB-CONF-004` | Wrong token addresses served by /bridge/tokens | P0 | Critical | `SCOPED-TBC` | Add detailed runbook steps (TBC). |
| `ZB-CONF-005` | Wrong decimals configuration on frontend for wrapped tokens | P0 | High | `SCOPED-TBC` | Add detailed runbook steps (TBC). |
| `ZB-CONF-006` | Fake oracle unreachable due to Docker network namespace changes | P1 | Medium | `SCOPED-TBC` | Add detailed runbook steps (TBC). |
| `ZB-CONF-007` | Missing admin token env var / rotated token | P2 | Low | `SCOPED-TBC` | Add detailed runbook steps (TBC). |
| `ZB-CONF-008` | Postgres schema mismatch / migration drift | P0 | High | `SCOPED-EXPAND` | Expand nearby scenario with explicit edge assertions. |
| `ZB-CONF-009` | Engine MEXC configuration absent or invalid | P0 | High | `SCOPED-TBC` | Add detailed runbook steps (TBC). |
| `ZB-CONF-010` | Wrong RR thresholds configured in engine | P0 | High | `SCOPED-EXPAND` | Expand nearby scenario with explicit edge assertions. |

<!-- L5-CATALOG-END -->
