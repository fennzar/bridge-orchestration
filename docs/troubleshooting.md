# Troubleshooting

Quick reference for common issues across the bridge stack. Organized by where you'll hit them.

---

## Setup & Prerequisites

### Docker Permission Denied

**Symptoms:** `Got permission denied while trying to connect to the Docker daemon socket`

**Fix:**
```bash
sudo usermod -aG docker $USER
newgrp docker
```

### Foundry / Cast / Anvil Not Found

**Symptoms:** `command not found: forge` or `command not found: cast`

**Fix:**
```bash
curl -L https://foundry.paradigm.xyz | bash
~/.foundry/bin/foundryup
export PATH="$HOME/.foundry/bin:$PATH"
```

Add the PATH export to your shell profile (`~/.bashrc` or `~/.zshrc`).

### Prerequisites Check Failed

Run `make status` to see which services and dependencies are missing, then `make precheck` for a detailed environment readiness report.

---

## Zephyr Daemon & Wallets

### Daemon is Busy

**Symptoms:**
- Wallet RPC calls return `{"code": -3, "message": "daemon is busy"}`
- Watchers log repeated retries for `get_reserve_info` or `get_transfers`
- `make dev-setup` hangs during liquidity seeding

**Cause:** The Zephyr daemon is single-threaded for certain operations. When multiple services (watchers, engine, seeder) hit it simultaneously, it returns "busy". Also commonly triggered after starting or stopping mining.

**Fix:**
- Usually resolves itself within 15-30 seconds (services have built-in exponential backoff)
- If persistent, restart the daemon: `docker compose restart zephyr-node1 zephyr-node2` and wait ~15 seconds

**Prevention:** Keep mining threads low (2-4) during setup and testing. High-thread mining (`--threads 8`) makes contention worse.

### Wallet Balance Shows Only ZPH

**Symptoms:** `get_balance` returns only the ZPH balance, missing ZSD/ZRS/ZYS.

**Cause:** The `get_balance` RPC requires `all_assets: true` to return all asset types. Without it, only ZPH is returned.

**Fix:**
```bash
curl -s http://127.0.0.1:48770/json_rpc \
  -d '{"jsonrpc":"2.0","id":"0","method":"get_balance","params":{"all_assets":true}}' \
  -H 'Content-Type: application/json' | jq '.result.balances'
```

### Mining Returns "Failed, Wrong Address"

**Symptoms:** `start_mining` returns an error about wrong address.

**Cause:** The `start_mining` daemon REST endpoint requires `miner_address` in the request body.

**Fix:**
```bash
# Get the miner wallet address
MINER_ADDR=$(curl -s http://127.0.0.1:48767/json_rpc \
  -d '{"jsonrpc":"2.0","id":"0","method":"get_address"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['address'])")

# Start mining with the address
curl -s http://127.0.0.1:47867/start_mining \
  -H 'Content-Type: application/json' \
  -d "{\"do_background_mining\":false,\"threads_count\":4,\"miner_address\":\"$MINER_ADDR\"}"
```

Note: `start_mining` and `stop_mining` are daemon REST endpoints (port 47867 or 47767), not wallet JSON-RPC endpoints (port 48767).

### Asset Conversion Fails With "Invalid TX Type"

**Symptoms:** Conversion transactions fail silently or return errors.

**Cause:** Mixing V1 and V2 asset names. Zephyr has two naming schemes that must not be mixed:
- **V1:** `ZEPH`, `ZEPHUSD`, `ZEPHRSV`, `ZYIELD`
- **V2:** `ZPH`, `ZSD`, `ZRS`, `ZYS`

**Fix:** Always use V2 names (`ZPH`, `ZSD`, `ZRS`, `ZYS`) consistently. The conversion RPC uses `source_asset` and `destination_asset` parameters (not `asset_type` or `dest_asset`).

### Reserve Ratio Too Low for Conversions

Not all conversions are available at all times. The reserve ratio governs what's allowed:

| Conversion | Requires | Notes |
|------------|----------|-------|
| ZPH to ZSD | RR >= 4.0 | Mint stable |
| ZPH to ZRS | None | Always allowed |
| ZSD to ZPH | None | Redeem stable |
| ZRS to ZPH | RR >= 2.0 | Redeem reserve |
| ZSD to ZYS | None | Mint yield |
| ZYS to ZSD | None | Redeem yield |

Check the current reserve ratio with `make set-price` (displays current state) or via the Zephyr CLI: `$ZEPHYR_CLI reserve_info`.

---

## EVM / Anvil

### Stale EVM Data on Devnet

**Symptoms:**
- Engine logs: `[Engine] EVM data stale (240s old)`
- Engine skips evaluation cycles

**Cause:** On devnet, if no EVM transactions occur, Anvil doesn't produce new blocks. The EVM watcher only updates its "last scanned" timestamp when it processes new blocks.

**Fix:** Force a block:
```bash
cast rpc evm_mine --rpc-url http://127.0.0.1:8545
```

### Anvil Not Responding

**Fix:**
```bash
docker ps | grep anvil
docker compose restart orch-anvil
```

### "Nonce Too Low"

**Cause:** Common after Anvil reset. The client's cached nonce is higher than what Anvil expects.

**Fix:** Check the current nonce and retry:
```bash
cast nonce $DEPLOYER_ADDR --rpc-url http://127.0.0.1:8545
```

### Contracts Not Found After Reset

After `make dev-reset-hard` or any Anvil state change, contracts need redeploying:
```bash
make dev-setup   # Handles deploy + sync automatically
```

If you only need to redeploy without a full setup:
```bash
./scripts/deploy-contracts.sh
./scripts/sync-env.sh
```

### Anvil State Issues (General)

```bash
# Reset to post-setup state (restores Anvil snapshot + resets Zephyr chain):
make dev-reset && make dev

# Reset to post-init state (wipes Anvil, re-deploy contracts):
make dev-reset-hard && make dev-setup && make dev

# Nuclear wipe (destroys everything):
make dev-delete && make dev-init && make dev-setup && make dev
```

---

## Bridge (Web, API, Watchers)

### Bridge API Not Healthy

**Symptoms:** `make dev-setup` hangs at "Waiting for bridge-api health" or `curl http://127.0.0.1:7051/health` fails.

**Fix:**
1. Check if the process is running: `overmind status -s .overmind-dev.sock`
2. Attach to the process for logs: `overmind connect bridge-api -s .overmind-dev.sock` (Ctrl-B D to detach)
3. If crash-looping, check for port conflicts: `lsof -i :7051`
4. Restart: `overmind restart bridge-api -s .overmind-dev.sock`

### Wrap Claims Not Appearing

After sending ZEPH to the bridge subaddress, claims may take time to appear. The bridge watcher needs to detect the deposit and the transaction needs sufficient confirmations.

**Check:**
```bash
# Check watcher is running
overmind status -s .overmind-dev.sock

# Check claims for an address
curl -s http://127.0.0.1:7051/claims/<evm-address> | jq
```

If claims are stuck, check the bridge watcher logs via `overmind connect bridge-watchers`.

---

## Engine

### Engine Auto-Execute Blocked

**Symptoms:**
- `[Engine] [arb] Plan did not meet auto-execute criteria`
- `[arbitrage] Blocking auto-execute: spot/MA spread too wide`

**Cause:** The arb strategy blocks automated trades when the oracle spot price and moving average (SMA) diverge by more than 500 basis points (5%). This prevents executing against stale pricing.

**Fix:** Align the oracle price and MA:
```bash
make set-ma-mode MA_MODE=manual
make set-ma MA=1.55
make set-price PRICE=1.55
```

Note: SMA takes time to catch up in `ema` or `mirror` modes. Use `manual` mode for isolated testing.

### Engine Not Seeing Price Changes

1. Check the fake orderbook is tracking the oracle:
   ```bash
   curl -s http://127.0.0.1:5556/status | jq '.oraclePriceUsd'
   ```
2. Verify FAKE_ORDERBOOK is enabled in the engine env
3. Restart engine watchers: `overmind restart engine-watchers -s .overmind-dev.sock`

### Fake Oracle Not Responding

```bash
make status                         # Check service health
make logs SERVICE=fake-oracle       # Check Docker logs
```

### Mode Not Transitioning (Devnet)

Reserve ratio transitions depend on total supply. A fresh devnet has minimal supply, so the RR calculation may not change as expected. Mine blocks to increase supply and allow transitions.

---

## Infrastructure

### Docker Services Won't Start

```bash
# Check what's running
docker compose ps

# Check for port conflicts
docker compose logs <service-name> 2>&1 | tail -20

# Restart a specific service
docker compose restart <service-name>
```

### Overmind Process Crash-Looping

**Symptoms:** `make status` shows a process as "crash-looping" or the port isn't responding.

**Fix:**
1. Attach to the process: `overmind connect <process> -s .overmind-dev.sock`
2. Check for errors in the output
3. Restart: `overmind restart <process> -s .overmind-dev.sock`

To read recent process output non-interactively:
```bash
tmux capture-pane -p -t "bridge-orchestration:<process>" | tail -100
```

### Switching Between Dev and Testnet-V2

Stop the current mode first. They share Docker infrastructure but use different Overmind sockets.

```bash
make dev-stop          # Before switching to testnet-v2
make testnet-v2-stop   # Before switching to dev
```

---

## Testnet V2

### Apps Won't Start / "Module Not Found"

`make testnet-v2` auto-builds, but if builds are stale:
```bash
make testnet-v2-stop && make testnet-v2
```

### Bridge Web Shows Wrong Host/IP

`NEXT_PUBLIC_*` vars are baked at build time. After changing `PUBLIC_HOST` in `.env`, run `make testnet-v2` to trigger a rebuild with the new values.

---

## Testnet V3 (Sepolia)

### Caddy Won't Start / TLS Errors

- Verify domain DNS points to your server
- Ports 80 and 443 must be open (no other reverse proxy in front)
- Check Caddy logs: `make testnet-v3-logs SERVICE=caddy`

### Sepolia RPC Errors

- Verify `EVM_RPC_HTTP` and `EVM_RPC_WS` in `env/.env.testnet-v3`
- Check rate limits on your RPC provider

### Bridge Watchers Not Connecting

Check Zephyr node health first, then bridge-watchers:
```bash
make testnet-v3-logs SERVICE=zephyr-node1
make testnet-v3-logs SERVICE=bridge-watchers
```
