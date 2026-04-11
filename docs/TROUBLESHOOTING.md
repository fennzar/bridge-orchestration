# Troubleshooting Zephyr Bridge

This guide covers common issues encountered during development and testing of the Zephyr Bridge.

## Table of Contents
- [Daemon is Busy RPC Errors](#daemon-is-busy-rpc-errors)
- [Stale EVM Data in Engine](#stale-evm-data-in-engine)
- [Bridge Web/API Connection Issues](#bridge-webapi-connection-issues)
- [Engine Strategy Blocking Auto-Execute](#engine-strategy-blocking-auto-execute)

---

## Daemon is Busy RPC Errors

**Symptoms:**
- `PoolSeeder` fails with `Zephyrd RPC /json_rpc failed: 500 Daemon is busy`
- `watcher-zephyr` logs show repeated retries for `get_reserve_info` or `get_transfers`
- `make dev-setup` hangs or fails during liquidity seeding

**Cause:**
The Zephyr wallet RPC (managed by `zephyrd`) is single-threaded for certain operations. If multiple services (e.g., the Zephyr watcher, the EVM watcher, and the engine's pool seeder) all hit the wallet simultaneously, the daemon will return a "busy" status.

**Workaround / Solutions:**
1. **Wait and Retry:** All core services have built-in exponential backoff (e.g., `zephyr-bridge/packages/zephyr/src/rpc.ts`). Usually, the error will resolve itself within 15-30 seconds.
2. **Reduce Load:** If it persists, stop the heavy processes:
   ```bash
   # Stop the engine and watchers briefly
   make dev-stop
   # Manually run the seeder if it was the one failing
   ./scripts/seed-via-engine.sh
   # Restart the stack
   make dev
   ```
3. **Mining Interference:** High-thread mining (`mine start --threads 8`) can exacerbate this. Keep mining threads low (2-4) during initial setup.

---

## Stale EVM Data in Engine

**Symptoms:**
- Engine logs show: `[Engine] EVM data stale (240s old)`
- Engine skips cycles even when `autoExecute` is true.

**Cause:**
The engine requires EVM data (positions, pool states) to be fresh (typically < 120s). On devnet, if no transactions occur, `anvil` does not produce new blocks, and the `watcher-evm` does not update its "last scanned" timestamp in the database.

**Solution:**
Force a block to be mined on the EVM chain:
```bash
cast rpc evm_mine --rpc-url http://127.0.0.1:8545
```
Or start the miner if not running:
```bash
# In another terminal or via orchestration
tools/zephyr-cli/cli mine start --threads 2
```

---

## Bridge Web/API Connection Issues

**Symptoms:**
- `make test-bridge` fails with `INFRA-04: bridge_web is down`
- `localhost:7050` returns "Connection Refused"

**Cause:**
`overmind` might have failed to start the process, or a previous zombie process is holding the port.

**Solution:**
1. Check `overmind` status:
   ```bash
   overmind status
   ```
2. Kill all node processes and restart:
   ```bash
   pkill node
   make dev-stop
   make dev
   ```

---

## Engine Strategy Blocking Auto-Execute

**Symptoms:**
- `[Engine] [arb] Plan did not meet auto-execute criteria`
- `[arbitrage] Blocking auto-execute: spot/MA spread too wide`

**Cause:**
The Arbitrage strategy includes safety guards. If the Oracle's Spot price and Moving Average (SMA) deviate by more than 500 basis points (5%), the engine blocks automated trades to prevent "toxic flow" or executing against stale pricing.

**Solution:**
1. Check the spread via CLI:
   ```bash
   curl -s -X POST http://127.0.0.1:47767/json_rpc -d '{"jsonrpc":"2.0","id":"0","method":"get_reserve_info"}' | jq .result.pr
   ```
2. Manually align the oracle if testing:
   ```bash
   make set-ma-mode MA_MODE=manual
   make set-ma MA=1.55
   make set-price PRICE=1.55
   ```
   *Note: SMA takes time to catch up in other modes (ema/mirror), so `manual` is best for isolation tests.*
