<!-- Auto-generated from route meta exports. Do not edit manually. -->
<!-- Regenerate: make docs-dashboard -->

# Dashboard API Reference

Base URL: `http://localhost:7100`

## Contents

- [Status](#status)
  - [App Processes](#app-processes) — `GET /api/apps`
  - [Mine EVM Block](#mine-evm-block) — `POST /api/evm/mine`
  - [EVM State](#evm-state) — `GET /api/evm`
  - [Container Logs](#container-logs) — `GET /api/infra/:name/logs`
  - [Infrastructure](#infrastructure) — `GET /api/infra`
  - [System Status](#system-status) — `GET /api/status`
- [Chain](#chain)
  - [Save Checkpoint](#save-checkpoint) — `POST /api/chain/checkpoint`
  - [Mining Control](#mining-control) — `POST /api/chain/mining`
  - [Oracle Price & Mode](#oracle-price-mode) — `GET, POST /api/chain/oracle`
  - [Pop Blocks](#pop-blocks) — `POST /api/chain/pop`
  - [Rescan Wallets](#rescan-wallets) — `POST /api/chain/rescan`
  - [Chain State](#chain-state) — `GET /api/chain`
  - [Set Scenario](#set-scenario) — `POST /api/chain/scenario`
  - [Transfer Funds](#transfer-funds) — `POST /api/chain/transfer`
- [Operations](#operations)
  - [Deploy Contracts](#deploy-contracts) — `POST /api/deploy`
  - [Orderbook Control](#orderbook-control) — `GET, POST /api/orderbook`
  - [Reset Environment](#reset-environment) — `POST /api/reset`
  - [Seed Liquidity](#seed-liquidity) — `POST /api/seed`
  - [Sync Env Files](#sync-env-files) — `POST /api/sync-env`
- [Testing](#testing)
  - [Abort Test Run](#abort-test-run) — `POST /api/tests/abort`
  - [Test Catalog](#test-catalog) — `GET /api/tests`
  - [Run Tests](#run-tests) — `POST /api/tests/run`
- [Apps](#apps)
  - [Restart Process](#restart-process) — `POST /api/apps/:name/command`
  - [Stop All Apps](#stop-all-apps) — `POST /api/apps/stop`

---

## Status

### App Processes

`GET` `/api/apps`

Status of all Overmind-managed app processes with recent log lines for running processes.

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `processes` | `AppStatus[]` | Yes | Status and recent logs of each app process |
| `timestamp` | `string` | Yes | ISO 8601 timestamp |

**Example:**

```bash
curl localhost:7100/api/apps
```

---

### Mine EVM Block

`POST` `/api/evm/mine`

Mine one or more blocks on Anvil (local EVM only).

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `blocks` | `number` | No | Number of blocks to mine (default: 1) |

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `success` | `boolean` | Yes | Whether mining succeeded |

**Example:**

```bash
curl -X POST localhost:7100/api/evm/mine -H 'Content-Type: application/json' -d '{"blocks":1}'
```

---

### EVM State

`GET` `/api/evm`

Full EVM state: chain info, key accounts, deployed tokens (with supply), contracts, Uniswap V4 pool prices/liquidity, engine wallet balances, and seeding status.

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `env` | `string` | Yes | EVM environment (devnet, testnet, mainnet) |
| `chainId` | `number | null` | Yes | Chain ID |
| `blockNumber` | `number | null` | Yes | Latest block number |
| `networkName` | `string` | Yes | Human-readable network name |
| `rpcUrl` | `string` | Yes | RPC URL (masked) |
| `accounts` | `EvmAccountInfo[]` | Yes | Key accounts with ETH balances |
| `tokens` | `EvmTokenInfo[]` | Yes | Deployed tokens with total supply |
| `contracts` | `EvmContractInfo[]` | Yes | Deployed contract addresses |
| `pools` | `EvmPoolInfo[]` | Yes | Uniswap V4 pool state (price, liquidity) |
| `engineWallet` | `{ address, ethBalance, tokenBalances }` | No | Engine wallet EVM balances |
| `seedingStatus` | `"not_seeded" | "partial" | "seeded"` | Yes | Liquidity seeding status |
| `timestamp` | `string` | Yes | ISO 8601 timestamp |

**Example:**

```bash
curl localhost:7100/api/evm
```

---

### Container Logs

`GET` `/api/infra/:name/logs`

Fetch recent log lines from a Docker container by service name.

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `logs` | `string[]` | Yes | Recent log lines from the container |

**Example:**

```bash
curl localhost:7100/api/infra/zephyr-node1/logs
```

---

### Infrastructure

`GET` `/api/infra`

Detailed status of all Docker containers including per-service RPC data (daemon height, wallet balances, oracle price, Anvil block number).

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `containers` | `ContainerStatus[]` | Yes | Status of each Docker service with RPC details (height, mining, balance, price, blockNumber) |
| `timestamp` | `string` | Yes | ISO 8601 timestamp |

**Example:**

```bash
curl localhost:7100/api/infra
```

---

### System Status

`GET` `/api/status`

High-level system status including lifecycle state, infrastructure/app counts, and chain vitals (height, oracle price, mining, checkpoint).

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `lifecycle` | `"stopped" | "initializing" | "infra-only" | "degraded" | "running"` | Yes | Current system lifecycle state |
| `infraSummary` | `{ running: number, total: number }` | Yes | Docker container counts |
| `appsSummary` | `{ running: number, healthy: number, total: number }` | Yes | Overmind process counts with health status |
| `chain` | `{ height, oraclePrice, anvilBlock, checkpoint, miningActive }` | Yes | Chain vitals |
| `timestamp` | `string` | Yes | ISO 8601 timestamp |

**Example:**

```bash
curl localhost:7100/api/status
```

---

## Chain

### Save Checkpoint

`POST` `/api/chain/checkpoint`

Save the current chain height as the checkpoint for fast resets.

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `success` | `boolean` | Yes | Whether checkpoint was saved |
| `height` | `number` | Yes | Saved chain height |

**Example:**

```bash
curl -X POST localhost:7100/api/chain/checkpoint
```

---

### Mining Control

`POST` `/api/chain/mining`

Start or stop mining on the primary Zephyr node.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `action` | `"start" | "stop"` | Yes | Mining action |
| `threads` | `number` | No | Number of mining threads (default: 1) |

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `success` | `boolean` | Yes | Whether the operation succeeded |
| `result` | `object` | No | RPC result from the daemon |

**Example:**

```bash
curl -X POST localhost:7100/api/chain/mining -H 'Content-Type: application/json' -d '{"action":"start","threads":1}'

curl -X POST localhost:7100/api/chain/mining -H 'Content-Type: application/json' -d '{"action":"stop"}'
```

---

### Oracle Price & Mode

`GET` `POST` `/api/chain/oracle`

Get or set the fake oracle price and mode (DEVNET only).

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `price` | `number` | No | New price in USD (e.g. 15.00) |
| `action` | `string` | No | Action to perform: 'set-mode' |
| `mode` | `string` | No | Oracle mode: 'manual' or 'mirror' (with action: 'set-mode') |

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `price` | `number | null` | No | Current oracle price in USD (GET) |
| `mode` | `string` | No | Current oracle mode: 'manual' or 'mirror' (GET) |
| `mirrorSpot` | `number` | No | Mainnet spot price when in mirror mode (GET) |
| `mirrorLastFetch` | `string` | No | Last mirror fetch timestamp (GET) |
| `success` | `boolean` | No | Whether the action succeeded (POST) |

**Example:**

```bash
curl localhost:7100/api/chain/oracle

curl -X POST localhost:7100/api/chain/oracle -H 'Content-Type: application/json' -d '{"price":15.00}'

curl -X POST localhost:7100/api/chain/oracle -H 'Content-Type: application/json' -d '{"action":"set-mode","mode":"mirror"}'
```

---

### Pop Blocks

`POST` `/api/chain/pop`

Pop (revert) blocks from both Zephyr nodes. Used for chain resets.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `blocks` | `number` | Yes | Number of blocks to pop (1-1000) |

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `success` | `boolean` | Yes | Whether blocks were popped |
| `blocksPopped` | `number` | Yes | Number of blocks reverted |
| `newHeight` | `number | null` | Yes | Chain height after pop |

**Example:**

```bash
curl -X POST localhost:7100/api/chain/pop -H 'Content-Type: application/json' -d '{"blocks":10}'
```

---

### Rescan Wallets

`POST` `/api/chain/rescan`

Trigger a blockchain rescan on one or all Zephyr wallets to refresh balances.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `wallet` | `string` | Yes | Wallet name (gov, miner, test, bridge, engine) or 'all' |

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `success` | `boolean` | Yes | Whether all rescans succeeded |
| `results` | `{ wallet, success, error? }[]` | Yes | Per-wallet rescan results |

**Example:**

```bash
curl -X POST localhost:7100/api/chain/rescan -H 'Content-Type: application/json' -d '{"wallet":"all"}'
```

---

### Chain State

`GET` `/api/chain`

Comprehensive Zephyr chain state including node sync status, mining info, wallet balances, oracle price, reserve protocol data, and checkpoint info.

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `nodes` | `{ node1: NodeInfo, node2: NodeInfo }` | Yes | Sync status of both Zephyr nodes |
| `mining` | `{ active, threads?, speed? }` | Yes | Mining status on primary node |
| `checkpoint` | `{ current, saved }` | Yes | Current and saved checkpoint heights |
| `oracle` | `{ price, mode, mirrorSpot?, mirrorLastFetch? }` | Yes | Oracle price in USD with mode (manual/mirror) |
| `wallets` | `WalletBalance[]` | Yes | All wallet addresses and multi-asset balances (ZPH, ZSD, ZRS, ZYS) |
| `reserve` | `ReserveInfo` | No | Zephyr reserve protocol state (ratios, assets, liabilities) |
| `timestamp` | `string` | Yes | ISO 8601 timestamp |

**Example:**

```bash
curl localhost:7100/api/chain
```

---

### Set Scenario

`POST` `/api/chain/scenario`

Apply a predefined scenario preset that sets oracle price and orderbook spread. Presets: normal, defensive, crisis, recovery, high-rr, volatility.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `scenario` | `string` | Yes | Preset name (normal, defensive, crisis, recovery, high-rr, volatility) |

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `success` | `boolean` | Yes | Whether both price and spread were set |
| `scenario` | `string` | Yes | Applied preset name |
| `price` | `number` | Yes | Oracle price set (USD) |
| `spreadBps` | `number` | Yes | Orderbook spread set (basis points) |

**Example:**

```bash
curl -X POST localhost:7100/api/chain/scenario -H 'Content-Type: application/json' -d '{"scenario":"crisis"}'
```

---

### Transfer Funds

`POST` `/api/chain/transfer`

Transfer assets between wallets or convert between asset types (ZPH↔ZSD, ZPH↔ZRS, ZSD↔ZYS).

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `fromWallet` | `string` | Yes | Source wallet (gov, miner, test, bridge, engine) |
| `toWallet` | `string` | No | Destination wallet name (for same-asset transfers to known wallets) |
| `toAddress` | `string` | No | Destination Zephyr address (for same-asset transfers to arbitrary addresses) |
| `amount` | `number` | Yes | Amount to transfer |
| `sourceAsset` | `string` | Yes | Source asset (ZPH, ZSD, ZRS, ZYS) |
| `destAsset` | `string` | Yes | Destination asset (same for transfer, different for conversion) |

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `success` | `boolean` | Yes | Whether the transfer succeeded |
| `txHash` | `string` | No | Transaction hash |

**Example:**

```bash
curl -X POST localhost:7100/api/chain/transfer -H 'Content-Type: application/json' -d '{"fromWallet":"gov","toWallet":"engine","amount":100,"sourceAsset":"ZPH","destAsset":"ZPH"}'
```

---

## Operations

### Deploy Contracts

`POST` `SSE` `/api/deploy`

Deploy EVM contracts to Anvil. Streams deployment progress via SSE.

**Response:** SSE stream

**Example:**

```bash
curl -N -X POST localhost:7100/api/deploy
```

---

### Orderbook Control

`GET` `POST` `/api/orderbook`

Get fake orderbook state or set the bid/ask spread (DEVNET only).

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `spreadBps` | `number` | Yes | Spread in basis points (e.g. 50 = 0.5%) |

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `success` | `boolean` | Yes | Whether the operation succeeded |
| `spreadBps` | `number` | No | Confirmed spread in basis points (POST) |
| `oraclePriceUsd` | `number` | No | Current oracle price in USD (GET) |
| `bestBid` | `number` | No | Current best bid price (GET) |
| `bestAsk` | `number` | No | Current best ask price (GET) |
| `spread` | `number` | No | Absolute spread (GET) |

**Example:**

```bash
curl localhost:7100/api/orderbook

curl -X POST localhost:7100/api/orderbook -H 'Content-Type: application/json' -d '{"spreadBps":50}'
```

---

### Reset Environment

`POST` `SSE` `/api/reset`

Reset environment layers to post-init state. Streams progress via SSE. Scope: full (all layers), zephyr, evm, or db.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `scope` | `string` | No | Reset scope: full (default), zephyr, evm, db |

**Response:** SSE stream

**Example:**

```bash
curl -N -X POST localhost:7100/api/reset -H 'Content-Type: application/json' -d '{"scope":"full"}'

curl -N -X POST localhost:7100/api/reset -H 'Content-Type: application/json' -d '{"scope":"evm"}'
```

---

### Seed Liquidity

`POST` `SSE` `/api/seed`

Seed liquidity through the full bridge wrap flow: fund engine wallet, convert assets, bridge wrap, claim tokens, add pool liquidity. Streams progress via SSE.

**Response:** SSE stream

**Example:**

```bash
curl -N -X POST localhost:7100/api/seed
```

---

### Sync Env Files

`POST` `/api/sync-env`

Sync the root .env file to sub-repo .env files (bridge, engine, etc.).

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `success` | `boolean` | Yes | Whether the sync succeeded |
| `output` | `string` | Yes | Combined stdout/stderr from the sync script |

**Example:**

```bash
curl -X POST localhost:7100/api/sync-env
```

---

## Testing

### Abort Test Run

`POST` `/api/tests/abort`

Abort a running test execution by its run ID.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `runId` | `string` | Yes | The run ID returned by the test/run SSE start event |

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `success` | `boolean` | Yes | Whether the run was aborted |
| `message` | `string` | Yes | Confirmation message |

**Example:**

```bash
curl -X POST localhost:7100/api/tests/abort -H 'Content-Type: application/json' -d '{"runId":"run-123456789-abc1234"}'
```

---

### Test Catalog

`GET` `/api/tests`

List all available L1-L5 tests with their IDs, names, levels, and categories.

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `tests` | `TestInfo[]` | Yes | All available tests with id, name, level, category, sublevel |
| `summary` | `{ L1, L2, L3, L4, L5, total }` | Yes | Test counts per level |

**Example:**

```bash
curl localhost:7100/api/tests
```

---

### Run Tests

`POST` `SSE` `/api/tests/run`

Execute tests and stream results via SSE. Supports running by test IDs, level, L5 sublevel, or category.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `testIds` | `string[]` | No | Specific test IDs to run |
| `level` | `string` | No | Test level: L1, L2, L3, L4, L5, or all |
| `sublevel` | `string` | No | L5 sublevel (e.g. L5.1, L5.2) |
| `category` | `string` | No | L5 category filter (e.g. SEC, RR) |

**Response:** SSE stream

**Example:**

```bash
curl -N -X POST localhost:7100/api/tests/run -H 'Content-Type: application/json' -d '{"level":"L1"}'
```

---

## Apps

### Restart Process

`POST` `/api/apps/:name/command`

Restart an Overmind-managed app process by name.

**Request body:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `command` | `"restart"` | Yes | Only 'restart' is supported |

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `success` | `boolean` | Yes | Whether the process was restarted |

**Example:**

```bash
curl -X POST localhost:7100/api/apps/bridge-api/command -H 'Content-Type: application/json' -d '{"command":"restart"}'
```

---

### Stop All Apps

`POST` `/api/apps/stop`

Stop all Overmind-managed app processes.

**Response:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `success` | `boolean` | Yes | Whether all processes were stopped |

**Example:**

```bash
curl -X POST localhost:7100/api/apps/stop
```

---

*24 endpoints documented.*
