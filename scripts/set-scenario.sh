#!/bin/bash
set -euo pipefail

# Set scenario preset (DEVNET only).
# Delegates price setting to zephyr's fresh-devnet, then sets bridge-specific
# fake orderbook spread.
#
# Usage: ./scripts/set-scenario.sh <preset>

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

source "$SCRIPT_DIR/lib/devnet.sh"
resolve_fresh_devnet

# Load env for orderbook port
source "$SCRIPT_DIR/lib/env.sh"
load_env "$ORCH_DIR/.env" 2>/dev/null || true

# Delegate price setting to zephyr
"$FRESH_DEVNET" scenario "$@"

# Bridge-specific: also set fake orderbook spread
SCENARIO="${1:-}"
ORDERBOOK_PORT="${FAKE_ORDERBOOK_PORT:-5556}"

# Map scenario to spread (bps)
case "$SCENARIO" in
    normal|recovery)   SPREAD=50 ;;
    high-spread)       SPREAD=200 ;;
    defensive)         SPREAD=100 ;;
    crisis)            SPREAD=300 ;;
    high-rr|depeg)     SPREAD=50 ;;
    volatility)        SPREAD=150 ;;
    *) exit 0 ;;  # help flag or fresh-devnet handled the error, skip orderbook
esac

curl -sf -X POST "http://127.0.0.1:$ORDERBOOK_PORT/set-spread" \
    -H "Content-Type: application/json" \
    -d "{\"spreadBps\": $SPREAD}" >/dev/null 2>&1 && \
    echo "  Orderbook spread: ${SPREAD} bps" || true
