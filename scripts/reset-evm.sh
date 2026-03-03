#!/bin/bash
set -euo pipefail

# ===========================================
# Reset EVM Only (preserve Zephyr state)
# ===========================================
# Wipes Anvil state file, restarts container, redeploys contracts.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

# Load shared libraries
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/env.sh"
source "$SCRIPT_DIR/lib/compose.sh"
load_env "$ORCH_DIR/.env" || { echo "Error: .env not found"; exit 1; }

DC_DEV=$(get_dc_dev "$ORCH_DIR")

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
    log_error "Anvil did not come up. Check: docker logs orch-anvil"
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
