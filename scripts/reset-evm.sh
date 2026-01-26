#!/bin/bash
set -euo pipefail

# ===========================================
# Reset EVM Only (preserve Zephyr state)
# ===========================================
# Wipes Anvil state file, restarts container, redeploys contracts.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

# Load environment safely (handles unquoted values like mnemonics)
source "$SCRIPT_DIR/lib/env.sh"
load_env "$ORCH_DIR/.env" || { echo "Error: .env not found"; exit 1; }

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

DC_DEV="docker compose --env-file $ORCH_DIR/.env -f $ORCH_DIR/docker/compose.base.yml -f $ORCH_DIR/docker/compose.dev.yml"

echo "==========================================="
echo "  Reset EVM (Zephyr state preserved)"
echo "==========================================="
echo ""

# Wipe Anvil state file and restart container
log_info "Wiping Anvil state and restarting..."
$DC_DEV exec -T anvil rm -f /data/anvil-state.json 2>/dev/null || true
$DC_DEV restart anvil

# Wait for Anvil to be healthy
log_info "Waiting for Anvil..."
for i in $(seq 1 30); do
    if cast block-number --rpc-url http://127.0.0.1:8545 >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

if ! cast block-number --rpc-url http://127.0.0.1:8545 >/dev/null 2>&1; then
    log_error "Anvil did not come up. Check: docker logs zephyr-anvil"
    exit 1
fi

# Redeploy contracts
log_info "Deploying contracts..."
"$SCRIPT_DIR/deploy-contracts.sh"

# Reset engine database (EVM-related tables)
log_info "Resetting engine database..."
cd "$ENGINE_REPO_PATH"
DATABASE_URL="$DATABASE_URL_ENGINE" pnpm db:reset 2>/dev/null || true

echo ""
log_success "EVM reset complete. Zephyr state preserved."
