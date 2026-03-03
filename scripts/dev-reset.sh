#!/bin/bash
set -euo pipefail

# ===========================================
# Dev Reset — Coordinated State Reset
# ===========================================
# Resets ALL layers to a clean state, then stops everything.
#
# Default (no flags):
#   Resets to post-setup state. Pops Zephyr to checkpoint,
#   restores Anvil from post-seed snapshot, resets DBs.
#   Ready for: make dev
#
# --hard:
#   Resets to post-init state. Restores LMDB from init snapshots,
#   wipes Anvil completely (no snapshot), resets DBs,
#   removes config/addresses.json.
#   Ready for: make dev-setup
#
# Usage:
#   ./scripts/dev-reset.sh          # Reset to post-setup state
#   ./scripts/dev-reset.sh --hard   # Reset to post-init state

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

# Load shared libraries
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/env.sh"
source "$SCRIPT_DIR/lib/compose.sh"
load_env "$ORCH_DIR/.env" || { echo "Error: .env not found"; exit 1; }

DC_DEV=$(get_dc_dev "$ORCH_DIR")
OVERMIND_SOCK="${OVERMIND_SOCK:-$ORCH_DIR/.overmind-dev.sock}"
ZEPHYR_CLI="${ZEPHYR_REPO_PATH:-$(dirname "$ORCH_DIR")/zephyr}/tools/zephyr-cli/cli"
ZEPHYR_DEVNET_SH="${ZEPHYR_REPO_PATH:-$(dirname "$ORCH_DIR")/zephyr}/tools/devnet.sh"

# Parse flags
HARD_RESET=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --hard)
            HARD_RESET=true; shift ;;
        -h|--help)
            echo "Usage: $0 [--hard]"
            echo ""
            echo "Default:   Reset to post-setup state (restore Anvil snapshot)"
            echo "  --hard   Reset to post-init state (wipe Anvil, remove addresses)"
            exit 0 ;;
        *)
            log_error "Unknown option: $1"; exit 1 ;;
    esac
done

if [ "$HARD_RESET" = true ]; then
    echo "==========================================="
    echo "  Dev Reset (hard — to post-init state)"
    echo "==========================================="
else
    echo "==========================================="
    echo "  Dev Reset (to post-setup state)"
    echo "==========================================="
fi
echo ""

# ===========================================
# Phase 0: Stop apps if running
# ===========================================
if [ -S "$OVERMIND_SOCK" ]; then
    if overmind status -s "$OVERMIND_SOCK" >/dev/null 2>&1; then
        log_info "Stopping Overmind apps..."
        overmind quit -s "$OVERMIND_SOCK" 2>/dev/null || true
        for i in $(seq 1 10); do
            [ ! -S "$OVERMIND_SOCK" ] && break
            sleep 0.5
        done
        log_success "Apps stopped"
    fi
    rm -f "$OVERMIND_SOCK"
fi

# Clean bridge-web cache to prevent ENOENT errors on restart
# Skip when using prod Procfile — the build output is needed
if [[ "${PROCFILE:-}" != *"Procfile.prod"* ]] && [ -n "$BRIDGE_REPO_PATH" ] && [ -d "$BRIDGE_REPO_PATH/apps/web/.next" ]; then
    rm -rf "$BRIDGE_REPO_PATH/apps/web/.next"
    log_info "Cleaned bridge-web .next cache"
fi

# ===========================================
# Phase 1: Start infrastructure temporarily
# ===========================================
INFRA_WAS_RUNNING=false
if $DC_DEV ps --format '{{.Name}}' 2>/dev/null | grep -q zephyr-node1; then
    INFRA_WAS_RUNNING=true
    log_info "Infrastructure already running"
else
    log_info "Starting infrastructure temporarily..."
    $DC_DEV up -d
fi

# Open wallets
log_info "Opening wallets..."
"$SCRIPT_DIR/open-wallets.sh"
echo ""

# ===========================================
# Phase 2: Zephyr chain reset
# ===========================================
log_info "Resetting Zephyr chain..."

if [ "$HARD_RESET" = true ]; then
    # Hard reset: restore LMDB from init snapshots
    SNAPSHOT_DIR="$ORCH_DIR/snapshots/chain"
    if [ ! -f "$SNAPSHOT_DIR/node1-lmdb.tar.gz" ]; then
        log_error "Chain snapshots not found. Run 'make dev-init' first."
        $DC_DEV --profile explorer down --remove-orphans
        exit 1
    fi

    # Close + delete bridge/engine/cex wallets (bridge-orch specific)
    log_info "Closing bridge/engine/cex wallets (will be recreated by dev-setup)..."
    "$ZEPHYR_CLI" wallet close bridge 2>/dev/null || true
    "$ZEPHYR_CLI" wallet close engine 2>/dev/null || true
    "$ZEPHYR_CLI" wallet close cex 2>/dev/null || true
    $DC_DEV exec -T wallet-gov sh -c 'rm -f /wallets/bridge /wallets/bridge.keys /wallets/bridge.address.txt /wallets/engine /wallets/engine.keys /wallets/engine.address.txt /wallets/cex /wallets/cex.keys /wallets/cex.address.txt' 2>/dev/null || true

    # Delegate LMDB restore + base wallet management to devnet.sh
    DC_CMD="$DC_DEV" DEVNET_DOCKER=1 "$ZEPHYR_DEVNET_SH" reset --hard --snapshot-dir "$SNAPSHOT_DIR"

    CHECKPOINT=$("$ZEPHYR_CLI" height)
    log_success "Chain restored to init height $CHECKPOINT"
else
    # Normal reset: pop to setup checkpoint (post-setup state)
    CHECKPOINT=$($DC_DEV exec -T wallet-gov cat /checkpoint/height 2>/dev/null) || true
    if [ -z "$CHECKPOINT" ]; then
        log_error "No checkpoint found. Run 'make dev-init' first."
        $DC_DEV --profile explorer down --remove-orphans
        exit 1
    fi
    CURRENT=$("$ZEPHYR_CLI" height)
    echo "  Current: $CURRENT, Checkpoint: $CHECKPOINT"

    # Close bridge/engine/cex wallets (bridge-orch specific)
    log_info "Closing bridge/engine/cex wallets..."
    for w in bridge engine cex; do
        "$ZEPHYR_CLI" wallet close "$w" 2>/dev/null || true
    done

    # Delegate pop/ringdb/restart/rescan/warmup to devnet.sh
    DC_CMD="$DC_DEV" DEVNET_DOCKER=1 "$ZEPHYR_DEVNET_SH" reset --checkpoint "$CHECKPOINT"

    # Reopen all wallets (including bridge/engine/cex)
    "$SCRIPT_DIR/open-wallets.sh"
fi

log_success "Zephyr chain reset to height $CHECKPOINT"

# ===========================================
# Phase 3: Anvil reset
# ===========================================
log_info "Resetting Anvil..."

if [ "$HARD_RESET" = true ]; then
    # Hard reset: wipe Anvil completely (dev-setup will redeploy)
    # Stop first so the graceful shutdown writes state.json, THEN delete it.
    $DC_DEV stop anvil 2>/dev/null || true
    rm -f "$ORCH_DIR/config/addresses.json"
    rm -f "$ORCH_DIR/deployed-addresses.json"
    rm -f "$ORCH_DIR/snapshots/anvil/post-setup.json"
    rm -f "$ORCH_DIR/snapshots/anvil/state.json"
    log_info "Removed config/addresses.json + Anvil state files"
    $DC_DEV exec -T wallet-gov sh -c 'cp /checkpoint/init-height /checkpoint/height' 2>/dev/null || true
else
    # Normal reset: restore Anvil checkpoint (post-setup state)
    # Stop first so graceful shutdown writes state.json, THEN overwrite it.
    $DC_DEV stop anvil 2>/dev/null || true
    if [ -f "$ORCH_DIR/snapshots/anvil/post-setup.json" ]; then
        /usr/bin/cp "$ORCH_DIR/snapshots/anvil/post-setup.json" "$ORCH_DIR/snapshots/anvil/state.json"
        log_info "Restored Anvil state from checkpoint"
    else
        log_warn "No Anvil snapshot found — EVM state not restored (run dev-setup to create one)"
    fi
fi

# Start Anvil — loads from state.json (checkpoint for normal reset,
# or absent for hard reset = fresh chain).
mkdir -p "$ORCH_DIR/snapshots/anvil" && chmod a+w "$ORCH_DIR/snapshots/anvil"
$DC_DEV start anvil 2>/dev/null || $DC_DEV up -d anvil

log_info "Waiting for Anvil..."
for i in $(seq 1 30); do
    if cast block-number --rpc-url http://127.0.0.1:8545 >/dev/null 2>&1; then
        break
    fi
    sleep 0.5
done

if ! cast block-number --rpc-url http://127.0.0.1:8545 >/dev/null 2>&1; then
    log_error "Anvil did not come up. Check: docker logs orch-anvil"
    $DC_DEV --profile explorer down --remove-orphans
    exit 1
fi

log_success "Anvil reset complete (block $(cast block-number --rpc-url http://127.0.0.1:8545 2>/dev/null || echo '?'))"

# ===========================================
# Phase 4: Database + Redis reset
# ===========================================
log_info "Resetting bridge database..."
cd "$BRIDGE_REPO_PATH/packages/db"
PRISMA_USER_CONSENT_FOR_DANGEROUS_AI_ACTION="yes" DATABASE_URL="$DATABASE_URL_BRIDGE" npx prisma db push --force-reset 2>&1 | tail -1
cd "$ORCH_DIR"

log_info "Resetting engine database..."
cd "$ENGINE_REPO_PATH"
PRISMA_USER_CONSENT_FOR_DANGEROUS_AI_ACTION="yes" DATABASE_URL="$DATABASE_URL_ENGINE" pnpm prisma db push --schema=src/infra/prisma/schema.prisma --force-reset --skip-generate 2>&1 | tail -1
cd "$ORCH_DIR"

log_success "Databases reset"

log_info "Flushing Redis (DB ${REDIS_DB:-6})..."
redis-cli -p "${REDIS_PORT:-6380}" -n "${REDIS_DB:-6}" FLUSHDB >/dev/null 2>&1 || \
    $DC_DEV exec -T redis redis-cli -n "${REDIS_DB:-6}" FLUSHDB >/dev/null 2>&1 || true
log_success "Redis flushed"

# ===========================================
# Phase 5: Stop infrastructure + wipe Blockscout
# ===========================================
log_info "Stopping infrastructure..."
$DC_DEV --profile explorer down --remove-orphans

# Wipe Blockscout DB so it re-indexes cleanly from the restored Anvil state.
# Must happen after `down` since the container holds the volume.
log_info "Resetting blockscout database..."
docker volume rm orch-blockscout-db-data 2>/dev/null || true

echo ""
echo "==========================================="
if [ "$HARD_RESET" = true ]; then
    log_success "Hard reset complete (post-init state)"
    echo "  Next: make dev-setup or make testnet-v2-setup"
else
    log_success "Reset complete (post-setup state)"
    echo "  Next: make dev or make testnet-v2"
fi
echo "==========================================="
