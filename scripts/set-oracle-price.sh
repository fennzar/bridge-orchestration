#!/bin/bash
set -euo pipefail

# Set fake oracle price (DEVNET only). Delegates to zephyr's fresh-devnet.
# Usage: ./scripts/set-oracle-price.sh <usd_price>

source "$(dirname "$0")/lib/devnet.sh"
resolve_fresh_devnet
exec "$FRESH_DEVNET" set-price "$@"
