#!/bin/bash
set -euo pipefail

# ===========================================
# Dev Setup — Bridge Infrastructure
# ===========================================
# Creates bridge/engine/cex wallets, deploys EVM contracts, seeds liquidity
# through the full bridge wrap flow. Requires dev-init to have been run.
#
# Usage:
#   ./scripts/dev-setup.sh
#
# Stops everything when done (volumes persist).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

# Load shared libraries
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/env.sh"
source "$SCRIPT_DIR/lib/compose.sh"
source "$SCRIPT_DIR/lib/disk.sh"
source "$SCRIPT_DIR/lib/prereqs.sh"
load_env "$ORCH_DIR/.env" || { echo "Error: .env not found"; exit 1; }

require_tool docker
require_tool overmind
require_tool python3
require_tool cast

# Cleanup disk if low before heavy operations
maybe_cleanup_disk

DC_DEV=$(get_dc_dev "$ORCH_DIR")
OVERMIND_SOCK="${OVERMIND_SOCK:-$ORCH_DIR/.overmind-dev.sock}"
PROCFILE="${PROCFILE:-$ORCH_DIR/Procfile.dev}"
ZEPHYR_CLI="${ZEPHYR_REPO_PATH:-$(dirname "$ORCH_DIR")/zephyr}/tools/zephyr-cli/cli"

# Target oracle price for this setup run (USD)
SETUP_PRICE="${SETUP_PRICE:-2.00}"

source "$SCRIPT_DIR/lib/cleanup.sh"

# Cleanup handler: stop apps + infra on exit (success or failure)
cleanup() {
    local exit_code=$?
    echo ""
    log_info "Stopping apps + infrastructure..."
    shutdown_overmind "$OVERMIND_SOCK"
    $DC_DEV down --remove-orphans 2>/dev/null || true
    if [ $exit_code -eq 0 ]; then
        log_success "Setup complete — everything stopped"
    else
        log_error "Setup failed — everything stopped"
    fi
    exit $exit_code
}
trap cleanup EXIT

echo "==========================================="
echo "  Dev Setup — Bridge Infrastructure"
echo "==========================================="
echo ""

# ===========================================
# Step 1: Prerequisites
# ===========================================
log_info "Checking prerequisites..."

if ! docker volume ls -q --filter name=zephyr-checkpoint | grep -q .; then
    log_error "Checkpoint volume not found. Run 'make dev-init' first."
    exit 1
fi

if [[ ! -x "$ZEPHYR_CLI" ]]; then
    log_error "zephyr-cli not found at $ZEPHYR_CLI"
    exit 1
fi

log_success "Prerequisites OK"
echo ""

# ===========================================
# Step 2: Start infrastructure
# ===========================================
log_info "Starting Docker infrastructure..."
# Ensure Anvil state dir is writable by foundry user (uid 1000) in container
mkdir -p "$ORCH_DIR/snapshots/anvil" && chmod a+w "$ORCH_DIR/snapshots/anvil"
$DC_DEV up -d
echo ""

# ===========================================
# Step 3: Verify checkpoint exists in volume
# ===========================================
log_info "Verifying chain checkpoint..."
CHECKPOINT=$($DC_DEV exec -T wallet-gov cat /checkpoint/height 2>/dev/null) || true
if [ -z "$CHECKPOINT" ]; then
    log_error "No checkpoint found in volume. Run 'make dev-init' first."
    exit 1
fi
log_success "Chain checkpoint at height $CHECKPOINT"
echo ""

# ===========================================
# Step 4: Wait for Postgres + push DB schemas
# ===========================================
log_info "Waiting for Postgres..."
for i in $(seq 1 30); do
    $DC_DEV exec -T postgres pg_isready -U postgres >/dev/null 2>&1 && break
    sleep 0.5
done

log_info "Pushing database schemas (force-reset for clean state)..."
cd "$BRIDGE_REPO_PATH/packages/db" && PRISMA_USER_CONSENT_FOR_DANGEROUS_AI_ACTION="yes" DATABASE_URL="$DATABASE_URL_BRIDGE" npx prisma db push --force-reset 2>&1 | tail -1
cd "$ENGINE_REPO_PATH" && PRISMA_USER_CONSENT_FOR_DANGEROUS_AI_ACTION="yes" DATABASE_URL="$DATABASE_URL_ENGINE" pnpm prisma db push --schema=src/infra/prisma/schema.prisma --force-reset 2>&1 | tail -1
cd "$ORCH_DIR"
# Flush Redis for clean state
redis-cli -p "${REDIS_PORT:-6380}" -n "${REDIS_DB:-6}" FLUSHDB >/dev/null 2>&1 || \
    $DC_DEV exec -T redis redis-cli -n "${REDIS_DB:-6}" FLUSHDB >/dev/null 2>&1 || true
log_success "Database schemas pushed + Redis flushed"
echo ""

# ===========================================
# Step 5: Open base wallets + create bridge/engine/cex wallets
# ===========================================
log_info "Opening base wallets..."
"$SCRIPT_DIR/open-wallets.sh"

log_info "Creating bridge, engine, and cex wallets..."
"$ZEPHYR_CLI" wallet create bridge
"$ZEPHYR_CLI" wallet create engine
"$ZEPHYR_CLI" wallet create cex

BRIDGE_ADDR=$("$ZEPHYR_CLI" address bridge | awk '{print $NF}')
ENGINE_ZEPH_ADDR=$("$ZEPHYR_CLI" address engine | awk '{print $NF}')
CEX_ZEPH_ADDR=$("$ZEPHYR_CLI" address cex | awk '{print $NF}')
log_success "Bridge wallet: ${BRIDGE_ADDR:0:20}..."
log_success "Engine wallet: ${ENGINE_ZEPH_ADDR:0:20}..."
log_success "CEX wallet:    ${CEX_ZEPH_ADDR:0:20}..."
echo ""

# ===========================================
# Step 6: Set oracle price + mine warmup blocks
# ===========================================
log_info "Stopping mining + flushing txpool..."
"$ZEPHYR_CLI" mine stop 2>/dev/null || true
"$ZEPHYR_CLI" flush-txpool 2>/dev/null || true

log_info "Rescanning wallets (sync with current chain)..."
"$ZEPHYR_CLI" rescan all

log_info "Setting oracle price to \$${SETUP_PRICE}..."
"$ZEPHYR_CLI" price "$SETUP_PRICE"

# Mine warm-up blocks for output unlock + oracle price absorption
log_info "Mining warm-up blocks..."
BEFORE_HEIGHT=$("$ZEPHYR_CLI" height)
"$ZEPHYR_CLI" mine start --threads 2
TARGET_HEIGHT=$((BEFORE_HEIGHT + 65))
"$ZEPHYR_CLI" wait "$TARGET_HEIGHT"
"$ZEPHYR_CLI" mine stop
sleep 2

# Refresh all wallets
for w in gov miner test bridge engine cex; do
    "$ZEPHYR_CLI" refresh "$w" 2>/dev/null || true
done
sleep 2
CUR=$("$ZEPHYR_CLI" height)
log_success "Mined to height $CUR (was $BEFORE_HEIGHT)"
echo ""

# ===========================================
# Step 7: Patch pool prices (oracle is now at $SETUP_PRICE)
# ===========================================
log_info "Patching pool prices to match devnet oracle..."
python3 "$SCRIPT_DIR/patch-pool-prices.py"
echo ""

# ===========================================
# Step 8: Reset Anvil + deploy contracts
# ===========================================
log_info "Resetting Anvil for fresh deploy..."
$DC_DEV stop anvil
rm -f "$ORCH_DIR/snapshots/anvil/state.json"
$DC_DEV start anvil
log_info "Waiting for Anvil..."
for i in $(seq 1 30); do
    cast block-number --rpc-url http://127.0.0.1:8545 >/dev/null 2>&1 && break
    sleep 1
done

log_info "Deploying EVM contracts..."
"$SCRIPT_DIR/deploy-contracts.sh"

# Keep addresses files in sync
cp "$ORCH_DIR/config/addresses.json" "$ORCH_DIR/config/addresses.local.json"
echo ""

# ===========================================
# Step 9: Sync env + start Overmind apps
# ===========================================
log_info "Starting apps (bridge + engine)..."
# Clean stale overmind socket and zombie processes from previous runs
shutdown_overmind "$OVERMIND_SOCK"
"$SCRIPT_DIR/sync-env.sh"
# Always use dev Procfile for setup — prod builds don't exist yet
SETUP_PROCFILE="$ORCH_DIR/Procfile.dev"
FORM="bridge-web=1,bridge-api=1,bridge-watchers=1,engine-web=1,engine-watchers=1,dashboard=0"
cd "$ORCH_DIR" && env -u TMUX -u TMUX_PANE -u TERM_PROGRAM OVERMIND_FORMATION="$FORM" overmind start -D -f "$SETUP_PROCFILE" -s "$OVERMIND_SOCK"

log_success "Apps started"

log_info "Waiting for bridge-api health (using 127.0.0.1:7051/health)..."
for i in $(seq 1 60); do
    if curl -sf http://127.0.0.1:7051/health >/dev/null 2>&1; then
        log_success "Bridge API healthy"
        break
    fi
    [ "$i" -eq 1 ] && log_info "   (Still waiting... if this persists, try: overmind connect bridge-api)"
    [ "$i" -eq 60 ] && {
        log_error "Bridge API not healthy after 60s"
        echo "DEBUG: overmind full status:"
        overmind status -s "$OVERMIND_SOCK" || true
        echo "DEBUG: curl test output:"
        curl -v http://127.0.0.1:7051/health 2>&1 | tail -n 20
        exit 1
    }
    sleep 2
done
echo ""

# ===========================================
# Step 10: Seed liquidity
# ===========================================
log_info "Seeding liquidity (engine native seeder)..."
"$SCRIPT_DIR/seed-via-engine.sh"
echo ""

# Mine blocks for change output maturity
log_info "Mining blocks for change output maturity..."
BEFORE=$("$ZEPHYR_CLI" height)
"$ZEPHYR_CLI" mine start --threads 2
TARGET=$((BEFORE + 15))
"$ZEPHYR_CLI" wait "$TARGET"
"$ZEPHYR_CLI" mine stop
sleep 2
for w in gov miner test bridge engine cex; do
    "$ZEPHYR_CLI" refresh "$w" 2>/dev/null || true
done
sleep 2
CUR=$("$ZEPHYR_CLI" height)
log_success "Mined to height $CUR, wallets refreshed"
echo ""

# ===========================================
# Step 11: Update Zephyr checkpoint
# ===========================================
log_info "Updating Zephyr checkpoint..."
NEW_HEIGHT=$("$ZEPHYR_CLI" height)
$DC_DEV exec -T wallet-gov sh -c "echo $NEW_HEIGHT > /checkpoint/height"
log_success "Checkpoint updated: $CHECKPOINT -> $NEW_HEIGHT"
echo ""

# ===========================================
# Step 12: Sanity check (while services are still running)
# ===========================================
log_info "Running post-setup sanity check..."
python3 "$SCRIPT_DIR/sanity-check-post-setup-state.py" --price "$SETUP_PRICE"
echo ""

# ===========================================
# Step 13: Save Anvil snapshot
# ===========================================
log_info "Saving Anvil EVM snapshot..."
# Anvil uses --state (bidirectional) + --preserve-historical-states, so a graceful
# stop writes the full state (including per-block history) to state.json.
# We copy that as the checkpoint for dev-reset.
mkdir -p "$ORCH_DIR/snapshots/anvil" && chmod a+w "$ORCH_DIR/snapshots/anvil"
$DC_DEV stop anvil
sleep 2
if [ -s "$ORCH_DIR/snapshots/anvil/state.json" ]; then
    cp "$ORCH_DIR/snapshots/anvil/state.json" "$ORCH_DIR/snapshots/anvil/post-setup.json"
    log_success "Anvil snapshot saved ($(du -h "$ORCH_DIR/snapshots/anvil/post-setup.json" | cut -f1))"
else
    log_warn "Anvil state.json not found after stop — dev-reset will start Anvil fresh"
fi
# Clean up legacy snapshots
rm -f "$ORCH_DIR/snapshots/anvil/post-setup.hex"
rm -f "$ORCH_DIR/snapshots/anvil/post-deploy.hex"
rm -f "$ORCH_DIR/snapshots/anvil/post-seed.hex"

# Write build state now — setup is complete regardless of final stop outcome
log_info "Recording build state..."
"$SCRIPT_DIR/write-build-state.sh"
echo '{"reset": "none"}' > "$ORCH_DIR/config/reset-required.json"
log_success "Reset marker cleared"
echo ""

# ===========================================
# Step 14: Stop (handled by cleanup trap)
# ===========================================
echo ""
echo "==========================================="
log_success "Dev setup complete"
echo "  Contracts: config/addresses.json"
echo "  Checkpoint: height $NEW_HEIGHT"
echo "==========================================="
