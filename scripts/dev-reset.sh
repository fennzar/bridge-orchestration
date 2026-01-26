#!/bin/bash
set -euo pipefail

# ===========================================
# Coordinated Dev Reset
# ===========================================
# Resets ALL layers to a clean post-init state:
#   1. Zephyr chain pop (to checkpoint)
#   2. Anvil wipe + contract redeploy
#   3. Database reset (Postgres)
#   4. Redis flush
#
# Usage:
#   ./scripts/dev-reset.sh              # Full coordinated reset (~30s)
#   ./scripts/dev-reset.sh --zephyr-only  # Zephyr chain only
#   ./scripts/dev-reset.sh --evm-only     # Anvil + contracts only
#   ./scripts/dev-reset.sh --db-only      # Postgres + Redis only

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

# Load environment
source "$SCRIPT_DIR/lib/env.sh"
load_env "$ORCH_DIR/.env" || { echo "Error: .env not found"; exit 1; }

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

DC_DEV="docker compose --env-file $ORCH_DIR/.env -f $ORCH_DIR/docker/compose.base.yml -f $ORCH_DIR/docker/compose.dev.yml"
OVERMIND_SOCK="$ORCH_DIR/.overmind-dev.sock"

# Parse flags
RESET_ZEPHYR=true
RESET_EVM=true
RESET_DB=true

while [[ $# -gt 0 ]]; do
    case $1 in
        --zephyr-only)
            RESET_EVM=false; RESET_DB=false; shift ;;
        --evm-only)
            RESET_ZEPHYR=false; RESET_DB=false; shift ;;
        --db-only)
            RESET_ZEPHYR=false; RESET_EVM=false; shift ;;
        -h|--help)
            echo "Usage: $0 [--zephyr-only|--evm-only|--db-only]"
            echo ""
            echo "Full reset (default): Zephyr pop + Anvil wipe + DB reset + Redis flush"
            echo ""
            echo "Options:"
            echo "  --zephyr-only  Pop Zephyr blocks to checkpoint only"
            echo "  --evm-only     Wipe Anvil state + redeploy contracts only"
            echo "  --db-only      Reset Postgres + flush Redis only"
            exit 0 ;;
        *)
            log_error "Unknown option: $1"; exit 1 ;;
    esac
done

echo "==========================================="
echo "  Dev Reset"
echo "==========================================="
SCOPE=""
if [ "$RESET_ZEPHYR" = true ]; then SCOPE="$SCOPE Zephyr"; fi
if [ "$RESET_EVM" = true ]; then SCOPE="$SCOPE EVM"; fi
if [ "$RESET_DB" = true ]; then SCOPE="$SCOPE DB+Redis"; fi
echo "  Scope:${SCOPE}"
echo ""

# ===========================================
# Phase 0: Stop apps if running
# ===========================================
APPS_WERE_RUNNING=false
if [ -S "$OVERMIND_SOCK" ]; then
    if overmind status -s "$OVERMIND_SOCK" >/dev/null 2>&1; then
        log_info "Stopping Overmind apps..."
        APPS_WERE_RUNNING=true
        overmind quit -s "$OVERMIND_SOCK" 2>/dev/null || true
        # Wait for socket to disappear
        for i in $(seq 1 10); do
            [ ! -S "$OVERMIND_SOCK" ] && break
            sleep 0.5
        done
        log_success "Apps stopped"
    fi
    rm -f "$OVERMIND_SOCK"
fi

# ===========================================
# Phase 1: Zephyr chain pop
# ===========================================
if [ "$RESET_ZEPHYR" = true ]; then
    log_info "Resetting Zephyr chain..."

    CHECKPOINT=$($DC_DEV exec -T wallet-gov cat /checkpoint/height 2>/dev/null) || true
    if [ -z "$CHECKPOINT" ]; then
        log_error "No checkpoint found. Run 'make dev-init' first."
        exit 1
    fi

    CURRENT=$(curl -sf http://localhost:47767/json_rpc \
        -d '{"jsonrpc":"2.0","id":"0","method":"get_info"}' | jq -r '.result.height')
    BLOCKS_TO_POP=$((CURRENT - CHECKPOINT))

    echo "  Current: $CURRENT, Checkpoint: $CHECKPOINT, Popping: $BLOCKS_TO_POP blocks"

    # Stop mining
    log_info "Stopping mining..."
    curl -sf http://localhost:47767/stop_mining -d '{}' >/dev/null 2>&1 || true
    sleep 1

    # Pop blocks on both nodes
    log_info "Popping blocks on node1..."
    curl -sf http://localhost:47767/json_rpc \
        -d "{\"jsonrpc\":\"2.0\",\"id\":\"0\",\"method\":\"pop_blocks\",\"params\":{\"nblocks\":$BLOCKS_TO_POP}}" >/dev/null
    log_info "Popping blocks on node2..."
    curl -sf http://localhost:47867/json_rpc \
        -d "{\"jsonrpc\":\"2.0\",\"id\":\"0\",\"method\":\"pop_blocks\",\"params\":{\"nblocks\":$BLOCKS_TO_POP}}" >/dev/null
    sleep 3

    # Rescan wallets
    log_info "Rescanning wallets..."
    curl -sf http://localhost:48769/json_rpc \
        -d '{"jsonrpc":"2.0","id":"0","method":"rescan_blockchain","params":{"hard":false}}' >/dev/null 2>&1 || true
    curl -sf http://localhost:48767/json_rpc \
        -d '{"jsonrpc":"2.0","id":"0","method":"rescan_blockchain","params":{"hard":false}}' >/dev/null 2>&1 || true
    curl -sf http://localhost:48768/json_rpc \
        -d '{"jsonrpc":"2.0","id":"0","method":"rescan_blockchain","params":{"hard":false}}' >/dev/null 2>&1 || true
    sleep 2

    # Restart mining
    log_info "Restarting mining..."
    MINER_ADDR=$(curl -sf http://localhost:48767/json_rpc \
        -d '{"jsonrpc":"2.0","id":"0","method":"get_address","params":{"account_index":0}}' | jq -r '.result.address')
    curl -sf http://localhost:47767/start_mining \
        -d "{\"do_background_mining\":false,\"ignore_battery\":true,\"miner_address\":\"$MINER_ADDR\",\"threads_count\":2}" >/dev/null

    log_success "Zephyr chain reset to height $CHECKPOINT"
fi

# ===========================================
# Phase 2: Anvil wipe + contract redeploy
# ===========================================
if [ "$RESET_EVM" = true ]; then
    log_info "Resetting Anvil..."

    # Wipe state file inside container and restart
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

    log_success "Anvil reset + contracts deployed"
fi

# ===========================================
# Phase 3: Database + Redis reset
# ===========================================
if [ "$RESET_DB" = true ]; then
    # Postgres: force-reset via Prisma
    log_info "Resetting bridge database..."
    cd "$BRIDGE_REPO_PATH/packages/db"
    DATABASE_URL="$DATABASE_URL_BRIDGE" npx prisma db push --force-reset 2>&1 | tail -1
    cd "$ORCH_DIR"

    log_info "Resetting engine database..."
    cd "$ENGINE_REPO_PATH"
    DATABASE_URL="$DATABASE_URL_ENGINE" pnpm prisma db push --schema=src/infra/prisma/schema.prisma --force-reset --skip-generate 2>&1 | tail -1
    cd "$ORCH_DIR"

    log_success "Databases reset"

    # Redis flush
    log_info "Flushing Redis (DB ${REDIS_DB:-6})..."
    redis-cli -p "${REDIS_PORT:-6380}" -n "${REDIS_DB:-6}" FLUSHDB >/dev/null 2>&1 || \
        $DC_DEV exec -T redis redis-cli -n "${REDIS_DB:-6}" FLUSHDB >/dev/null 2>&1 || true

    log_success "Redis flushed"
fi

# ===========================================
# Phase 4: Restart apps if they were running
# ===========================================
if [ "$APPS_WERE_RUNNING" = true ]; then
    log_info "Restarting Overmind apps..."
    cd "$ORCH_DIR" && overmind start -D -f "$ORCH_DIR/Procfile.dev" -s "$OVERMIND_SOCK"
    log_success "Apps restarted"
fi

echo ""
echo "==========================================="
log_success "Reset complete"
echo "==========================================="
