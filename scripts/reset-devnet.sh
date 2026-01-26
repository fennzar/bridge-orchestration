#!/bin/bash
set -euo pipefail

# Reset DEVNET to post-init state. Delegates to zephyr's fresh-devnet.
# Usage: ./scripts/reset-devnet.sh [--status|--force|--recover]

source "$(dirname "$0")/lib/devnet.sh"
resolve_fresh_devnet
exec "$FRESH_DEVNET" reset "$@"
