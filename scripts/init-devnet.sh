#!/bin/bash
set -euo pipefail

# Initialize DEVNET: build binaries and install bridge-specific dependencies.
# Delegates build to zephyr's fresh-devnet.
#
# Usage:
#   ./scripts/init-devnet.sh              # Build binaries only
#   ./scripts/init-devnet.sh --start      # Build and start DEVNET

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

source "$SCRIPT_DIR/lib/devnet.sh"
resolve_fresh_devnet

# Build DEVNET binaries
"$FRESH_DEVNET" build

# Install fake-orderbook dependencies (bridge-specific)
if [[ -f "$ORCH_DIR/services/fake-orderbook/package.json" ]]; then
    echo "Installing fake-orderbook dependencies..."
    cd "$ORCH_DIR/services/fake-orderbook" && pnpm install --silent 2>/dev/null || true
fi

# Optionally start
if [[ "${1:-}" == "--start" ]]; then
    "$FRESH_DEVNET" start
fi
