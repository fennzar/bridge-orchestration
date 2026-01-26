#!/bin/bash
set -euo pipefail

# Save DEVNET snapshot. Delegates to zephyr's fresh-devnet.
# Usage: ./scripts/save-devnet.sh [name]

source "$(dirname "$0")/lib/devnet.sh"
resolve_fresh_devnet
exec "$FRESH_DEVNET" save "$@"
