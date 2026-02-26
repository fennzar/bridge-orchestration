#!/bin/bash
# ===========================================
# Open Zephyr Wallets
# ===========================================
# Wallet RPCs don't auto-load wallet files after container restart.
# This script opens all wallets that exist on the shared volume.
#
# Usage: ./scripts/open-wallets.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

source "$SCRIPT_DIR/lib/env.sh"
load_env "$ORCH_DIR/.env" 2>/dev/null || true

ZEPHYR_CLI="${ZEPHYR_REPO_PATH:-$(dirname "$ORCH_DIR")/zephyr}/tools/zephyr-cli/cli"

"$ZEPHYR_CLI" wallet open all
