#!/bin/bash
set -euo pipefail

# Save DEVNET checkpoint. Delegates to zephyr's fresh-devnet.
# Usage: ./scripts/checkpoint-devnet.sh [--show]

source "$(dirname "$0")/lib/devnet.sh"
resolve_fresh_devnet
exec "$FRESH_DEVNET" checkpoint "$@"
