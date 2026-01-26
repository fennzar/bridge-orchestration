# Mainnet Fork Environment (DEPRECATED)

> **This mode is deprecated.** Use DEVNET mode (`make dev-init`) instead. This document is kept for historical reference only.

Mainnet-fork mode splits from the real Zephyr mainnet at a specific block height, preserving oracle pricing history. It requires 22GB+ LMDB data and runs Zephyr nodes/wallets natively (not in Docker).

---

## Why Split Chain, Not Genesis Chain

The Zephyr test chain is **not** started from genesis. Instead, it's a **split from mainnet** at a point after the last hard fork (HF).

**Reasons:**
- Oracle pricing records exist in chain history and are required for protocol operations
- Oracle calls reference historical data that must be present
- Starting from genesis would require modifying HF block heights (complex, error-prone)
- Split chain preserves all necessary protocol state while allowing isolated testing

**Implications:**
- Initial setup requires syncing or copying mainnet data up to split point
- The LMDB database files (`node1/lmdb`, `node2/lmdb`) contain real chain history
- Resets restore from a snapshot of the split point, not genesis
- Mining continues from the split height on an isolated fork

---

## Initial Setup: Creating the Split

```bash
# One-time setup: Sync mainnet data to a point after the last HF
# Option 1: Sync a fresh node to current height, then copy
./zephyrd --data-dir mainnet-sync
# Wait for sync to complete...
# Stop the node

# Option 2: Copy from an existing synced node
cp -r /path/to/synced/mainnet/lmdb ./node1/lmdb
cp -r /path/to/synced/mainnet/lmdb ./node2/lmdb
```

---

## Snapshot Management

Keep a clean snapshot of the LMDB state at the split point for resets:

```bash
# Create snapshot (after initial sync, before any test transactions)
mkdir -p $ROOT/zephyr-snapshots
cp -r node1/lmdb $ROOT/zephyr-snapshots/node1-lmdb-split
cp -r node2/lmdb $ROOT/zephyr-snapshots/node2-lmdb-split

# Reset to clean split state
rm -rf node1/lmdb node2/lmdb
cp -r $ROOT/zephyr-snapshots/node1-lmdb-split node1/lmdb
cp -r $ROOT/zephyr-snapshots/node2-lmdb-split node2/lmdb
```

---

## Running Nodes

### Node 2 (Primary/Mining)

```bash
cd $ROOT/zephyr

MONERO_RANDOMX_UMASK=8 ./zephyrd \
  --data-dir node2 \
  --disable-dns-checkpoints \
  --add-exclusive-node 127.0.0.1:48080 \
  --fixed-difficulty 100 \
  --block-notify "/bin/node $ROOT/zephyr-bridge/lib/zephyr/scripts/blocknotify.js %s"
```

### Node 1 (Peer)

```bash
MONERO_RANDOMX_UMASK=8 ./zephyrd \
  --data-dir node1 \
  --p2p-bind-ip 127.0.0.1 \
  --p2p-bind-port 48080 \
  --rpc-bind-port 48081 \
  --zmq-rpc-bind-port 48082 \
  --add-exclusive-node 127.0.0.1:17868 \
  --disable-dns-checkpoints \
  --fixed-difficulty 100
```

### Notes on Split Chain Operation

- `--add-exclusive-node` ensures nodes only talk to each other (isolated from mainnet)
- `--disable-dns-checkpoints` prevents nodes from trying to sync with mainnet
- `--fixed-difficulty 100` allows fast block mining for testing
- Chain will diverge from mainnet immediately upon mining the first block
- Oracle pricing data from before the split remains valid and accessible

---

## Wallets

### Bridge Wallet

```bash
# Create new wallet (first time only)
./zephyr-wallet-cli --generate-new-wallet localbridge --password ""

# Start wallet RPC
./zephyr-wallet-rpc \
  --rpc-bind-port 17777 \
  --wallet-file localbridge \
  --password "" \
  --disable-rpc-login \
  --trusted-daemon \
  --tx-notify "/bin/node $ROOT/zephyr-bridge/lib/zephyr/scripts/txnotify.js %s"
```

### Mining Wallet (generates test funds)

```bash
./zephyr-wallet-cli --wallet-file localmining --password ""
# Use: start_mining <threads>
```

---

## Legacy Ports

| Service | Port | Notes |
|---------|------|-------|
| Node 1 RPC | 48081 | Primary daemon |
| Node 2 P2P | 17868 | Mining/secondary |
| Bridge Wallet | 17777 | Wallet RPC |
| Mining Wallet | (CLI) | Interactive |
| Exchange Wallet | (CLI) | Interactive |
| Test User Wallet | (CLI) | Interactive |

---

## Legacy .env Variables

These variables were used in mainnet-fork mode and are now commented out in `.env.example`:

```bash
ZEPHYR_CHAIN_MODE=mainnet-fork
ZEPHYR_BIN_PATH=${ROOT}/zephyr/build/Linux/master/release/bin
ZEPHYR_DATA_DIR=${ROOT}/zephyr-data
ZEPHYR_WALLET_DIR=${ROOT}/zephyr-wallets
ZEPHYR_SOURCE_LMDB=${HOME}/.zephyr/lmdb
```

---

## Hard Reset (fresh start)

```bash
# 1. Stop all services (all terminals)

# 2. Reset Zephyr chain to split point
cd $ROOT/zephyr
rm -rf node1/lmdb node2/lmdb
cp -r $ROOT/zephyr-snapshots/node1-lmdb-split node1/lmdb
cp -r $ROOT/zephyr-snapshots/node2-lmdb-split node2/lmdb

# 3. Reset Zephyr wallets (create fresh wallets)
rm -rf localbridge* sepoliabridge* localexchange* localtestuser* localmining*
./zephyr-wallet-cli --generate-new-wallet localbridge --password ""
./zephyr-wallet-cli --generate-new-wallet localexchange --password ""
./zephyr-wallet-cli --generate-new-wallet localtestuser --password ""
./zephyr-wallet-cli --generate-new-wallet localmining --password ""

# 4. Reset Bridge Redis
cd $ROOT/zephyr-bridge
npm run reset:redis:flush -- --yes

# 5. Reset Anvil state and redeploy
cd $ROOT/zephyr-eth-foundry
rm -f state.json
# Restart anvil in another terminal, then:
./scripts/deploy_all_test_env1.sh

# 6. Reset Engine database
cd $ROOT/zephyr-bridge-engine
pnpm db:reset

# 7. Fund wallets
# Start mining wallet, mine blocks to generate ZEPH
# Transfer to bridge, exchange, and test user wallets

# 8. Restart all services
```

## Zephyr-Only Reset (preserve EVM state)

When you only need to reset Zephyr side but keep EVM contracts/state:

```bash
# 1. Stop Zephyr nodes and wallets

# 2. Restore LMDB to split point
cd $ROOT/zephyr
rm -rf node1/lmdb node2/lmdb
cp -r $ROOT/zephyr-snapshots/node1-lmdb-split node1/lmdb
cp -r $ROOT/zephyr-snapshots/node2-lmdb-split node2/lmdb

# 3. Recreate wallets
rm -rf localbridge* localexchange* localtestuser*
./zephyr-wallet-cli --generate-new-wallet localbridge --password ""
# ... etc

# 4. Clear bridge Redis (Zephyr-related keys)
cd $ROOT/zephyr-bridge
npm run reset:redis  # Preserves bridge:accounts if needed

# 5. Re-fund wallets and restart
```

---

## Overmind Formation (Legacy)

In mainnet-fork mode, Zephyr nodes and wallets ran natively via Overmind (not Docker). The formation was:

```bash
OVERMIND_FORMATION=zephyr-node1=1,zephyr-node2=1,wallet-mining=1,wallet-bridge=1,wallet-exchange=1,wallet-testuser=1,bridge-web=1,bridge-api=1,bridge-watchers=1,engine-web=1,engine-watchers=1,status-dashboard=1
```

The legacy mainnet-fork Procfile has been removed. The formation above is preserved here for reference only.
