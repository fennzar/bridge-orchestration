# Plan: Event-Driven Bridge Watcher (Replace 5s Polling)

## Problem

The Zephyr watcher (`watcher-zephyr`) polls `get_transfers` every 5 seconds. This is wasteful:
- 12 RPC calls/min to the bridge wallet, regardless of whether anything happened
- Adds latency (up to 5s) before deposits are detected
- Wallet RPC is single-threaded — polling competes with other operations

## Available Notification Mechanisms

### Option A: ZMQ Pub/Sub (daemon) — Recommended

The Zephyr daemon has a built-in ZMQ XPUB socket (`--zmq-pub` flag) that publishes:

| Topic | Fires When | Payload |
|-------|-----------|---------|
| `json-minimal-chain_main` | New block added | `{first_height, first_prev_id, ids: [hash...]}` |
| `json-full-chain_main` | New block added | Full block data |
| `json-minimal-txpool_add` | Tx enters mempool | `[{id, blob_size, weight, fee}]` |
| `json-full-txpool_add` | Tx enters mempool | Full tx data |
| `json-full-miner_data` | New block (mining template) | Mining template data |

Message format is `topic_name:JSON` (colon-separated prefix).

**Current status:** The daemon exposes `--zmq-rpc-bind-port=47768` (REP socket for RPC), but `--zmq-pub` is **not configured**. These are separate sockets — pub needs its own port.

**Pros:**
- True push: zero overhead between events
- Fires on both new blocks AND new mempool txs
- Standard ZMQ — well-supported in Node.js (`zeromq` v6)
- Already built into the daemon, just needs enabling
- Can subscribe to specific topics (only chain_main, or txpool too)

**Cons:**
- Requires adding `--zmq-pub` flag to daemon config
- Adds a Node.js native dependency (`zeromq` requires libzmq)
- ZMQ is daemon-level — sees ALL txs, not just bridge wallet deposits
- Need fallback polling anyway (ZMQ connection loss)

### Option B: `--tx-notify` (wallet-rpc)

The wallet-rpc supports `--tx-notify "command %s"` which spawns a process for each incoming tx, replacing `%s` with the tx hash.

**Pros:**
- Wallet-level: only fires for txs TO the bridge wallet (pre-filtered)
- Built-in, no extra dependencies

**Cons:**
- Shell command only — no HTTP, no IPC. Must spawn a process per tx
- In Docker: the wallet container needs the notify target reachable (volume-mount a script, or curl to an HTTP endpoint)
- Process spawning overhead per tx
- No block notifications (can't update confirmations without separate mechanism)
- Awkward to wire up in containerized setup

### Option C: `--block-notify` (daemon)

The daemon supports `--block-notify "command %s"` which spawns a process for each new block.

**Pros:**
- Simple wake-up signal
- One call per block (not per tx)

**Cons:**
- Same shell-command-only limitation as `--tx-notify`
- Same Docker wiring issues
- No mempool notifications (deposits detected only after block inclusion)

### Option D: Hybrid — ZMQ wake-up + poll on demand

Use ZMQ `json-minimal-chain_main` as a wake-up signal, then do a single `get_transfers` call. Fall back to slow polling (30-60s) if ZMQ goes silent.

**This is the recommended approach.**

## Recommended Design: ZMQ Wake-Up + On-Demand Poll

### Architecture

```
Zephyr Daemon (node1)
  │
  ├── :47767  JSON-RPC (existing)
  ├── :47768  ZMQ REP/RPC (existing)
  └── :47769  ZMQ PUB (NEW — needs --zmq-pub flag)
        │
        ▼
  Watcher subscribes to:
    - json-minimal-chain_main  (new block → check transfers)
    - json-minimal-txpool_add  (new mempool tx → early detection)
        │
        ▼
  On event: call get_transfers() once
  Fallback: poll every 30-60s if no ZMQ event received
```

### Watcher Flow (New)

```
1. Connect ZMQ SUB to tcp://zephyr-node1:47769
2. Subscribe to "json-minimal-chain_main" and "json-minimal-txpool_add"
3. Enter event loop:
   a. Wait for ZMQ message OR 30s timeout
   b. On chain_main → parse height from message, call get_transfers(min_height)
   c. On txpool_add → call get_transfers() for pending/pool txs
   d. On timeout → poll get_transfers() as fallback (same as today, but 30s not 5s)
   e. Process transfers, update confirmations, sign claims
4. On ZMQ disconnect → fall back to 5s polling until reconnected
```

### Why Both Topics?

- **`chain_main`**: Fires when a block is mined. This is when confirmations increment. Essential.
- **`txpool_add`**: Fires when a tx enters the mempool. This gives early visibility — the watcher can show "pending (0 confirmations)" in the UI immediately, before the tx is mined into a block. Optional but nice for UX.

### Confirmation Updates

Currently the watcher re-checks ALL recent transfers every 5s to update confirmation counts. With ZMQ:
- Each `chain_main` event includes the new block height
- The watcher knows confirmations for all tracked txs increased by 1
- Can update confirmation counts in-memory without re-fetching `get_transfers`
- Only needs `get_transfers` to discover NEW txs

This is a significant optimization — today we do `get_transfers` with 500-block lookback every 5s just to update confirmations.

## Changes Required

### 1. Daemon Config (`docker/compose.base.yml`)

Add `--zmq-pub` to zephyr-node1:

```yaml
zephyr-node1:
  command:
    # ... existing flags ...
    - "--zmq-pub=tcp://0.0.0.0:47769"
```

Expose port in `docker/compose.dev.yml`:
```yaml
zephyr-node1:
  ports:
    - "47769:47769"  # ZMQ PUB
```

### 2. Bridge Watcher (`apps/watcher-zephyr/src/index.ts`)

- Add `zeromq` dependency to the watcher package
- Create ZMQ subscriber that connects to `tcp://zephyr-node1:47769`
- Subscribe to `json-minimal-chain_main` and optionally `json-minimal-txpool_add`
- Replace the fixed 5s `setInterval` with an event-driven loop:
  - ZMQ message → immediate `get_transfers` + process
  - 30s timeout → fallback poll (same logic as today)
- Keep confirmation tracking in Redis (same as today)
- On ZMQ disconnect/error → fall back to 5s polling, attempt reconnect

### 3. Testnet V2 Config (`docker/compose.testnet-v2.yml`)

Same `--zmq-pub` flag addition. The containerized watcher connects via Docker network hostname (`zephyr-node1:47769`).

### 4. Environment Variables

New env vars for the watcher:
```
ZEPHYR_ZMQ_PUB_URL=tcp://zephyr-node1:47769   # ZMQ pub endpoint
ZEPHYR_POLL_FALLBACK_MS=30000                   # Fallback poll interval (30s)
```

## Migration Path

1. **Phase 1:** Add `--zmq-pub` to daemon config. No watcher changes. Verify ZMQ messages flow with a test subscriber.
2. **Phase 2:** Add ZMQ subscription to watcher alongside existing polling. ZMQ triggers immediate polls; interval stays as fallback.
3. **Phase 3:** Once proven stable, increase fallback interval from 5s to 30-60s.

Fully backward-compatible: if `ZEPHYR_ZMQ_PUB_URL` is not set, the watcher falls back to pure polling (current behavior).

## `zeromq` npm Package

The `zeromq` v6 package provides async iterators for subscriptions:

```typescript
import { Subscriber } from "zeromq";

const sock = new Subscriber();
sock.connect("tcp://zephyr-node1:47769");
sock.subscribe("json-minimal-chain_main");
sock.subscribe("json-minimal-txpool_add");

for await (const [topic, msg] of sock) {
  const topicStr = topic.toString();
  const payload = msg.toString();
  // Parse: "json-minimal-chain_main:{...}"
  const json = JSON.parse(payload);
  // Trigger get_transfers...
}
```

**Note:** `zeromq` v6 requires `libzmq` native library. In Docker containers this is already available (the Zephyr image includes `libzmq5`). For native Overmind processes, `libzmq-dev` must be installed on the host.

## Effort Estimate

| Task | Scope |
|------|-------|
| Add `--zmq-pub` to compose files | Trivial (2 lines) |
| Test ZMQ pub with standalone subscriber | Small (verify messages flow) |
| Add `zeromq` to watcher package | Small (npm install + native build) |
| Refactor watcher poll loop to event-driven | Medium (core logic change) |
| Fallback/reconnect logic | Small-Medium |
| Testing (devnet + testnet-v2) | Medium |

## Not In Scope

- Changing `--tx-notify` / `--block-notify` (shell-only, not useful in Docker)
- ZMQ for the EVM watcher (Anvil/Sepolia have their own event systems)
- ZMQ for unwrap flow (different watcher, different direction)
