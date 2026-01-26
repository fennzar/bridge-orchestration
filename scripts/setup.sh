#!/bin/bash
set -euo pipefail

# ===========================================
# Zephyr Bridge Stack - Full Setup
# ===========================================
# Runs all setup scripts in sequence.
# For partial setup, run individual scripts:
#   ./scripts/setup-infra.sh  - Docker, contracts
#   ./scripts/setup-zephyr.sh - LMDB, wallets
#   ./scripts/setup-apps.sh   - App dependencies, migrations

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }

echo "==========================================="
echo "  Zephyr Bridge Stack - Full Setup"
echo "==========================================="
echo ""

# Create .env if missing
if [ ! -f "$ORCH_DIR/.env" ]; then
    if [ -f "$ORCH_DIR/.env.example" ]; then
        log_info "Creating .env from .env.example..."
        cp "$ORCH_DIR/.env.example" "$ORCH_DIR/.env"
        echo ""
        echo "IMPORTANT: Edit $ORCH_DIR/.env and set ROOT to your dev folder path"
        echo "Then re-run this script."
        echo ""
        exit 1
    else
        echo "Error: .env.example not found"
        exit 1
    fi
fi

# Run setup scripts in order
"$SCRIPT_DIR/setup-infra.sh"
echo ""

"$SCRIPT_DIR/setup-zephyr.sh"
echo ""

"$SCRIPT_DIR/setup-apps.sh"
echo ""

echo "==========================================="
log_success "Full Setup Complete!"
echo "==========================================="
echo ""
echo "Start the stack:"
echo "  ./scripts/dev.sh"
echo ""
echo "Or start specific components:"
echo "  overmind start -l zephyr-node1,zephyr-node2,wallet-bridge"
echo ""
