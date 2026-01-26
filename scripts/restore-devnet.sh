#!/bin/bash
set -euo pipefail

# Restore DEVNET snapshot. Delegates to zephyr's fresh-devnet.
# Usage: ./scripts/restore-devnet.sh [name]

source "$(dirname "$0")/lib/devnet.sh"
resolve_fresh_devnet
exec "$FRESH_DEVNET" restore "$@"
