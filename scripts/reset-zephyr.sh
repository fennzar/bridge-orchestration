#!/bin/bash
set -euo pipefail

# ===========================================
# DEPRECATED - Mainnet-Fork Only
# ===========================================
# This script is for mainnet-fork mode which is deprecated.
# Use DEVNET mode instead: make dev-reset
# ===========================================

# ===========================================
# Reset Zephyr Chain Only (preserve EVM state)
# ===========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

# Load environment safely (handles unquoted values like mnemonics)
source "$SCRIPT_DIR/lib/env.sh"
load_env "$ORCH_DIR/.env" || { echo "Error: .env not found"; exit 1; }

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

echo "==========================================="
echo "  Reset Zephyr Chain (EVM state preserved)"
echo "==========================================="
echo ""

# Stop Zephyr processes
log_info "Stopping Zephyr processes..."
pkill -f "zephyrd.*--data-dir" 2>/dev/null || true
pkill -f "zephyr-wallet-rpc" 2>/dev/null || true
sleep 2

# Restore LMDB
if [ -d "$ZEPHYR_SNAPSHOT_DIR/node1-lmdb-split" ]; then
    log_info "Restoring LMDB from snapshot..."
    rm -rf "$ZEPHYR_DATA_DIR/node1/lmdb"
    rm -rf "$ZEPHYR_DATA_DIR/node2/lmdb"
    cp -r "$ZEPHYR_SNAPSHOT_DIR/node1-lmdb-split" "$ZEPHYR_DATA_DIR/node1/lmdb"
    cp -r "$ZEPHYR_SNAPSHOT_DIR/node2-lmdb-split" "$ZEPHYR_DATA_DIR/node2/lmdb"
    log_success "LMDB restored"
else
    log_warn "No LMDB snapshot found. Run ./scripts/init-zephyr-lmdb.sh first."
fi

# Recreate wallets
log_info "Recreating Zephyr wallets..."
cd "$ZEPHYR_BIN_PATH"
rm -f "$ZEPHYR_WALLET_DIR/localbridge"* 2>/dev/null || true
rm -f "$ZEPHYR_WALLET_DIR/localexchange"* 2>/dev/null || true
rm -f "$ZEPHYR_WALLET_DIR/localtestuser"* 2>/dev/null || true
rm -f "$ZEPHYR_WALLET_DIR/localmining"* 2>/dev/null || true

./zephyr-wallet-cli --generate-new-wallet "$ZEPHYR_WALLET_DIR/localbridge" --password "" --command "exit"
./zephyr-wallet-cli --generate-new-wallet "$ZEPHYR_WALLET_DIR/localexchange" --password "" --command "exit"
./zephyr-wallet-cli --generate-new-wallet "$ZEPHYR_WALLET_DIR/localtestuser" --password "" --command "exit"
./zephyr-wallet-cli --generate-new-wallet "$ZEPHYR_WALLET_DIR/localmining" --password "" --command "exit"
log_success "Wallets recreated"

# Clear Zephyr-related Redis keys
log_info "Clearing Zephyr-related Redis keys..."
cd "$BRIDGE_REPO_PATH"
npm run reset:redis 2>/dev/null || redis-cli -n ${REDIS_DB:-6} FLUSHDB

echo ""
log_success "Zephyr reset complete. EVM state preserved."
log_info "Restart with: ./scripts/dev.sh"
