#!/bin/bash
set -euo pipefail

# ===========================================
# DEPRECATED - Mainnet-Fork Only
# ===========================================
# This script is for mainnet-fork mode which is deprecated.
# Use DEVNET mode instead: make dev-checkpoint
# ===========================================

# ===========================================
# Zephyr Bridge Stack - Create Zephyr Snapshots
# ===========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Load environment safely (handles unquoted values like mnemonics)
source "$SCRIPT_DIR/lib/env.sh"
load_env "$ORCH_DIR/.env" 2>/dev/null || true

echo "==========================================="
echo "  Create Zephyr LMDB Snapshots"
echo "==========================================="
echo ""

# Check that Zephyr nodes are NOT running
if pgrep -f "zephyrd.*--data-dir" > /dev/null; then
    log_error "Zephyr nodes are running. Stop them first:"
    log_error "  ./scripts/stop.sh"
    exit 1
fi

# Check that LMDB directories exist
if [ ! -d "$ZEPHYR_DATA_DIR/node1/lmdb" ]; then
    log_error "Node 1 LMDB not found at $ZEPHYR_DATA_DIR/node1/lmdb"
    log_info "You need to:"
    log_info "  1. Sync a Zephyr node to mainnet (or copy from existing)"
    log_info "  2. Copy the lmdb directory to $ZEPHYR_DATA_DIR/node1/lmdb"
    exit 1
fi

if [ ! -d "$ZEPHYR_DATA_DIR/node2/lmdb" ]; then
    log_error "Node 2 LMDB not found at $ZEPHYR_DATA_DIR/node2/lmdb"
    exit 1
fi

# Get current chain height (approximate from file size or ask user)
echo "Current LMDB directories:"
du -sh "$ZEPHYR_DATA_DIR/node1/lmdb"
du -sh "$ZEPHYR_DATA_DIR/node2/lmdb"
echo ""

log_warn "This will create snapshots of the current LMDB state."
log_warn "Make sure the chain is at the desired split point!"
echo ""
read -p "Continue? [y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    log_info "Cancelled"
    exit 0
fi

# Create snapshots
log_info "Creating node1 snapshot..."
rm -rf "$ZEPHYR_SNAPSHOT_DIR/node1-lmdb-split"
cp -r "$ZEPHYR_DATA_DIR/node1/lmdb" "$ZEPHYR_SNAPSHOT_DIR/node1-lmdb-split"
log_success "Node 1 snapshot created"

log_info "Creating node2 snapshot..."
rm -rf "$ZEPHYR_SNAPSHOT_DIR/node2-lmdb-split"
cp -r "$ZEPHYR_DATA_DIR/node2/lmdb" "$ZEPHYR_SNAPSHOT_DIR/node2-lmdb-split"
log_success "Node 2 snapshot created"

echo ""
echo "Snapshot sizes:"
du -sh "$ZEPHYR_SNAPSHOT_DIR/node1-lmdb-split"
du -sh "$ZEPHYR_SNAPSHOT_DIR/node2-lmdb-split"

echo ""
log_success "Snapshots created at $ZEPHYR_SNAPSHOT_DIR"
log_info "These will be used by ./scripts/reset.sh to restore the chain"
