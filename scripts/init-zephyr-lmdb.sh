#!/bin/bash
set -euo pipefail

# ===========================================
# DEPRECATED - Mainnet-Fork Only
# ===========================================
# This script is for mainnet-fork mode which is deprecated.
# Use DEVNET mode instead: make dev-init
# ===========================================

# ===========================================
# Initialize Zephyr LMDB from Source
# ===========================================
# Copies LMDB from a synced mainnet node (default: ~/.zephyr/lmdb)
# to create the split chain for testing.

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

# Load environment safely (handles unquoted values like mnemonics)
source "$SCRIPT_DIR/lib/env.sh"
if ! load_env "$ORCH_DIR/.env"; then
    log_error ".env file not found. Copy .env.example to .env first."
    exit 1
fi

# Defaults
SOURCE_LMDB="${ZEPHYR_SOURCE_LMDB:-$HOME/.zephyr/lmdb}"
DATA_DIR="${ZEPHYR_DATA_DIR:-$ORCH_DIR/../zephyr-data}"
SNAPSHOT_DIR="${ZEPHYR_SNAPSHOT_DIR:-$ORCH_DIR/snapshots/zephyr}"

echo "==========================================="
echo "  Initialize Zephyr LMDB"
echo "==========================================="
echo ""
echo "Source LMDB:    $SOURCE_LMDB"
echo "Data Dir:       $DATA_DIR"
echo "Snapshot Dir:   $SNAPSHOT_DIR"
echo ""

# Check source exists
if [ ! -d "$SOURCE_LMDB" ]; then
    log_error "Source LMDB not found at: $SOURCE_LMDB"
    log_info "Either sync a mainnet node to ~/.zephyr or set ZEPHYR_SOURCE_LMDB in .env"
    exit 1
fi

# Check size
SOURCE_SIZE=$(du -sh "$SOURCE_LMDB" | cut -f1)
log_info "Source LMDB size: $SOURCE_SIZE"

# Confirm
echo ""
log_warn "This will copy the LMDB to create:"
log_warn "  - $DATA_DIR/node1/lmdb"
log_warn "  - $DATA_DIR/node2/lmdb"
log_warn "  - $SNAPSHOT_DIR/node1-lmdb-split (for resets)"
log_warn "  - $SNAPSHOT_DIR/node2-lmdb-split (for resets)"
echo ""
log_warn "Total disk space needed: ~${SOURCE_SIZE} x 4 = ~44GB"
echo ""

read -p "Continue? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "Cancelled"
    exit 0
fi

# Create directories
mkdir -p "$DATA_DIR/node1"
mkdir -p "$DATA_DIR/node2"
mkdir -p "$SNAPSHOT_DIR"

# Check if Zephyr is running
if pgrep -f "zephyrd" > /dev/null; then
    log_error "Zephyr daemon is running. Please stop it first."
    exit 1
fi

# Copy to node directories
log_info "Copying LMDB to node1 (this may take a while)..."
rm -rf "$DATA_DIR/node1/lmdb"
cp -r "$SOURCE_LMDB" "$DATA_DIR/node1/lmdb"
log_success "Node 1 LMDB ready"

log_info "Copying LMDB to node2..."
rm -rf "$DATA_DIR/node2/lmdb"
cp -r "$SOURCE_LMDB" "$DATA_DIR/node2/lmdb"
log_success "Node 2 LMDB ready"

# Create snapshots for reset capability
log_info "Creating snapshot for node1..."
rm -rf "$SNAPSHOT_DIR/node1-lmdb-split"
cp -r "$DATA_DIR/node1/lmdb" "$SNAPSHOT_DIR/node1-lmdb-split"
log_success "Node 1 snapshot ready"

log_info "Creating snapshot for node2..."
rm -rf "$SNAPSHOT_DIR/node2-lmdb-split"
cp -r "$DATA_DIR/node2/lmdb" "$SNAPSHOT_DIR/node2-lmdb-split"
log_success "Node 2 snapshot ready"

echo ""
echo "==========================================="
echo "  LMDB Initialization Complete"
echo "==========================================="
echo ""
echo "Directory sizes:"
du -sh "$DATA_DIR/node1/lmdb"
du -sh "$DATA_DIR/node2/lmdb"
du -sh "$SNAPSHOT_DIR/node1-lmdb-split"
du -sh "$SNAPSHOT_DIR/node2-lmdb-split"
echo ""
log_success "Ready to start Zephyr nodes with ./scripts/dev.sh"
