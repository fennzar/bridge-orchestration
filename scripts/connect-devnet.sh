#!/bin/bash
set -euo pipefail

# Connect to a fresh-devnet process log. Delegates to zephyr's fresh-devnet.
# Usage: ./scripts/connect-devnet.sh [service]
#
# Services: oracle, node1, node2, gov-wallet, miner-wallet, test-wallet
# No args lists available services.

source "$(dirname "$0")/lib/devnet.sh"
resolve_fresh_devnet
exec "$FRESH_DEVNET" connect "$@"
