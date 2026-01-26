#!/bin/bash
set -euo pipefail

# ===========================================
# DEPRECATED - Mainnet-Fork Only
# ===========================================
# This script is for mainnet-fork mode which is deprecated.
# Use DEVNET mode instead: make dev-init
# ===========================================

# ===========================================
# Setup Zephyr (LMDB, Wallets)
# ===========================================
# Initializes Zephyr chain data and creates wallets.
# Run setup-infra.sh first.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

echo "==========================================="
echo "  Zephyr Setup"
echo "==========================================="
echo ""

# Load environment
source "$SCRIPT_DIR/lib/env.sh"
if ! load_env "$ORCH_DIR/.env"; then
    log_error ".env not found"
    exit 1
fi

# Check Zephyr binaries
if [ ! -x "${ZEPHYR_BIN_PATH}/zephyrd" ]; then
    log_error "Zephyr daemon not found at ${ZEPHYR_BIN_PATH}"
    exit 1
fi

# Ensure directories exist
mkdir -p "$ZEPHYR_DATA_DIR/node1"
mkdir -p "$ZEPHYR_DATA_DIR/node2"
mkdir -p "$ZEPHYR_WALLET_DIR"

# ---------------------------------------------
# Initialize LMDB from Mainnet
# ---------------------------------------------
if [ -d "$ZEPHYR_DATA_DIR/node1/lmdb" ] && [ -f "$ZEPHYR_DATA_DIR/node1/lmdb/data.mdb" ]; then
    log_info "Zephyr LMDB already initialized"
else
    if [ -d "${ZEPHYR_SOURCE_LMDB:-}" ] && [ -f "${ZEPHYR_SOURCE_LMDB}/data.mdb" ]; then
        log_info "Initializing Zephyr LMDB from mainnet..."
        "$SCRIPT_DIR/init-zephyr-lmdb.sh"
    else
        log_warn "No mainnet LMDB found at ${ZEPHYR_SOURCE_LMDB:-\$HOME/.zephyr/lmdb}"
        log_warn "You'll need to sync mainnet first or copy LMDB manually"
        log_warn "To sync: ${ZEPHYR_BIN_PATH}/zephyrd --data-dir ~/.zephyr"
    fi
fi

# ---------------------------------------------
# Create Wallets
# ---------------------------------------------
log_info "Creating Zephyr wallets..."
cd "$ZEPHYR_BIN_PATH"

create_wallet() {
    local name=$1
    local wallet_path="$ZEPHYR_WALLET_DIR/$name"

    if [ -f "$wallet_path" ]; then
        log_info "Wallet $name already exists"
        return 0
    fi

    log_info "Creating wallet: $name"
    # Create wallet non-interactively with English mnemonic
    ./zephyr-wallet-cli \
        --generate-new-wallet "$wallet_path" \
        --password "" \
        --mnemonic-language English \
        --log-level 0 \
        --command "exit" 2>/dev/null || {
            log_error "Failed to create wallet: $name"
            return 1
        }
    log_success "Created wallet: $name"
}

create_wallet "localbridge"
create_wallet "localexchange"
create_wallet "localtestuser"
create_wallet "localmining"

echo ""
log_success "Zephyr setup complete!"
echo ""
echo "Wallets created in: $ZEPHYR_WALLET_DIR"
echo "Chain data in: $ZEPHYR_DATA_DIR"
echo ""
echo "To start Zephyr nodes:"
echo "  overmind start -l zephyr-node1,zephyr-node2"
echo ""
