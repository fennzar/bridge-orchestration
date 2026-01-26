# Zephyr Bridge Stack - DEVNET Process Definitions for Overmind
#
# This Procfile is used with ./scripts/dev.sh --devnet
#
# IMPORTANT: The Zephyr DEVNET nodes and wallets are started by the
# fresh-devnet tool (in the Zephyr repo), NOT by this Procfile.
# This Procfile only starts the additional services needed for bridge testing.
#
# fresh-devnet provides:
#   - Fake oracle (port 5555)
#   - Node1 (RPC 47767), Node2 (RPC 47867)
#   - Gov wallet (48769), Miner wallet (48767), Test wallet (48768)
#   - Initial minted state (ZRS, ZSD, ZYS)
#
# This Procfile adds:
#   - Fake orderbook service
#   - Bridge app (web, api, watchers)
#   - Engine app (web, watchers)

# ===========================================
# Fake Orderbook Service
# ===========================================
# Provides MEXC-compatible API tracking the fake oracle price.
# Used by the engine for CEX market data in DEVNET mode.

fake-orderbook: cd $ORCHESTRATION_PATH/services/fake-orderbook && FAKE_ORDERBOOK_PORT=${FAKE_ORDERBOOK_PORT:-5556} FAKE_ORACLE_URL=http://127.0.0.1:${DEVNET_ORACLE_PORT:-5555} node index.js

# ===========================================
# Bridge Application (zephyr-bridge repo)
# ===========================================
# Note: Uses fresh-devnet's test wallet (port 48768) as the bridge wallet.
# The test wallet starts empty but can receive funds from gov wallet.

bridge-web: cd $BRIDGE_REPO_PATH && ZEPH_WALLET_RPC_PORT=48768 ZEPHYR_D_RPC_URL=http://127.0.0.1:47767 pnpm dev:web

bridge-api: cd $BRIDGE_REPO_PATH && ZEPH_WALLET_RPC_PORT=48768 ZEPHYR_D_RPC_URL=http://127.0.0.1:47767 pnpm dev:api

bridge-watchers: cd $BRIDGE_REPO_PATH && ZEPH_WALLET_RPC_PORT=48768 ZEPHYR_D_RPC_URL=http://127.0.0.1:47767 pnpm dev:watchers

# ===========================================
# Engine Application (zephyr-bridge-engine repo)
# ===========================================
# Uses fake orderbook for MEXC data, connects to DEVNET Zephyr node

engine-web: cd $ENGINE_REPO_PATH && ZEPHYR_D_RPC_URL=http://127.0.0.1:47767 FAKE_ORDERBOOK_ENABLED=true FAKE_ORDERBOOK_PORT=${FAKE_ORDERBOOK_PORT:-5556} pnpm --dir apps/web dev

engine-watchers: cd $ENGINE_REPO_PATH && ZEPHYR_D_RPC_URL=http://127.0.0.1:47767 FAKE_ORDERBOOK_ENABLED=true FAKE_ORDERBOOK_PORT=${FAKE_ORDERBOOK_PORT:-5556} pnpm dev:watchers

# ===========================================
# Status Dashboard (orchestration repo)
# ===========================================
# Web dashboard on port 7100 showing stack status

status-dashboard: cd $ORCHESTRATION_PATH/status-dashboard && ZEPHYR_CHAIN_MODE=devnet pnpm dev
