#!/bin/bash
set -euo pipefail

# ===========================================
# DEPRECATED - Mainnet-Fork Only
# ===========================================
# This script contains mainnet-fork LMDB reset logic.
# Use DEVNET mode instead: make dev-reset
# ===========================================

# ===========================================
# Zephyr Bridge Stack - Full Reset
# ===========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Load environment safely (handles unquoted values like mnemonics)
source "$SCRIPT_DIR/lib/env.sh"
if ! load_env "$ORCH_DIR/.env"; then
    log_error ".env file not found"
    exit 1
fi

# Parse arguments
SKIP_ZEPHYR=false
SKIP_EVM=false
SKIP_WALLETS=false
FORCE=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-zephyr)
            SKIP_ZEPHYR=true
            shift
            ;;
        --skip-evm)
            SKIP_EVM=true
            shift
            ;;
        --skip-wallets)
            SKIP_WALLETS=true
            shift
            ;;
        -f|--force)
            FORCE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --skip-zephyr   Don't reset Zephyr LMDB"
            echo "  --skip-evm      Don't reset Anvil state"
            echo "  --skip-wallets  Don't recreate Zephyr wallets"
            echo "  -f, --force     Skip confirmation prompts"
            echo "  -h, --help      Show this help"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "==========================================="
echo "  Zephyr Bridge Stack - Full Reset"
echo "==========================================="
echo ""
echo "This will reset:"
if [ "$SKIP_ZEPHYR" = false ]; then
    echo "  - Zephyr LMDB (restore from snapshot)"
fi
if [ "$SKIP_WALLETS" = false ]; then
    echo "  - Zephyr wallets (recreate fresh)"
fi
if [ "$SKIP_EVM" = false ]; then
    echo "  - Anvil state (redeploy contracts)"
fi
echo "  - Redis data"
echo "  - PostgreSQL databases"
echo ""

if [ "$FORCE" = false ]; then
    read -p "Continue? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Cancelled"
        exit 0
    fi
fi

# ---------------------------------------------
# Stop Everything
# ---------------------------------------------
log_info "Stopping all services..."
"$SCRIPT_DIR/stop.sh" --keep-infra 2>/dev/null || true

# ---------------------------------------------
# Reset Zephyr LMDB
# ---------------------------------------------
if [ "$SKIP_ZEPHYR" = false ]; then
    log_info "Resetting Zephyr LMDB..."

    if [ -d "$ZEPHYR_SNAPSHOT_DIR/node1-lmdb-split" ] && [ -d "$ZEPHYR_SNAPSHOT_DIR/node2-lmdb-split" ]; then
        rm -rf "$ZEPHYR_DATA_DIR/node1/lmdb"
        rm -rf "$ZEPHYR_DATA_DIR/node2/lmdb"
        cp -r "$ZEPHYR_SNAPSHOT_DIR/node1-lmdb-split" "$ZEPHYR_DATA_DIR/node1/lmdb"
        cp -r "$ZEPHYR_SNAPSHOT_DIR/node2-lmdb-split" "$ZEPHYR_DATA_DIR/node2/lmdb"
        log_success "Zephyr LMDB restored from snapshot"
    else
        log_warn "Zephyr LMDB snapshots not found at $ZEPHYR_SNAPSHOT_DIR"
        log_warn "Skipping LMDB reset. Create snapshots first with ./scripts/snapshot-zephyr.sh"
    fi
fi

# ---------------------------------------------
# Reset Zephyr Wallets
# ---------------------------------------------
if [ "$SKIP_WALLETS" = false ]; then
    log_info "Recreating Zephyr wallets..."
    cd "$ZEPHYR_BIN_PATH"

    rm -f "$ZEPHYR_WALLET_DIR/localbridge"* 2>/dev/null || true
    rm -f "$ZEPHYR_WALLET_DIR/localexchange"* 2>/dev/null || true
    rm -f "$ZEPHYR_WALLET_DIR/localtestuser"* 2>/dev/null || true
    rm -f "$ZEPHYR_WALLET_DIR/localmining"* 2>/dev/null || true

    ./zephyr-wallet-cli --generate-new-wallet "$ZEPHYR_WALLET_DIR/localbridge" --password "" --command "exit"
    ./zephyr-wallet-cli --generate-new-wallet "$ZEPHYR_WALLET_DIR/localexchange" --password "" --command "exit"
    ./zephyr-wallet-cli --generate-new-wallet "$ZEPHYR_WALLET_DIR/localtestuser" --password "" --command "exit"
    ./zephyr-wallet-cli --generate-new-wallet "$ZEPHYR_WALLET_DIR/localmining" --password "" --command "exit"

    log_success "Zephyr wallets recreated"
fi

# ---------------------------------------------
# Reset Redis
# ---------------------------------------------
log_info "Resetting Redis..."
cd "$ORCH_DIR"
docker compose exec -T redis redis-cli FLUSHDB
log_success "Redis flushed"

# ---------------------------------------------
# Reset PostgreSQL
# ---------------------------------------------
log_info "Resetting PostgreSQL databases..."
docker compose exec -T postgres psql -U zephyr -c "DROP DATABASE IF EXISTS zephyrbridge_dev;"
docker compose exec -T postgres psql -U zephyr -c "DROP DATABASE IF EXISTS zephyr_bridge_arb;"
docker compose exec -T postgres psql -U zephyr -c "CREATE DATABASE zephyrbridge_dev;"
docker compose exec -T postgres psql -U zephyr -c "CREATE DATABASE zephyr_bridge_arb;"
docker compose exec -T postgres psql -U zephyr -c "GRANT ALL PRIVILEGES ON DATABASE zephyrbridge_dev TO zephyr;"
docker compose exec -T postgres psql -U zephyr -c "GRANT ALL PRIVILEGES ON DATABASE zephyr_bridge_arb TO zephyr;"

# Run migrations
log_info "Running database migrations..."
cd "$BRIDGE_REPO_PATH"
DATABASE_URL="$DATABASE_URL_BRIDGE" npx prisma migrate dev --skip-generate 2>/dev/null || true
DATABASE_URL="$DATABASE_URL_BRIDGE" npx prisma generate

cd "$ENGINE_REPO_PATH"
DATABASE_URL="$DATABASE_URL_ENGINE" pnpm db:generate
DATABASE_URL="$DATABASE_URL_ENGINE" pnpm db:migrate 2>/dev/null || true

log_success "Databases reset and migrated"

# ---------------------------------------------
# Reset Anvil / Redeploy Contracts
# ---------------------------------------------
if [ "$SKIP_EVM" = false ]; then
    log_info "Resetting Anvil..."

    # Reset Anvil to blank state
    cast rpc anvil_reset --rpc-url http://127.0.0.1:8545 || true

    # Redeploy contracts
    log_info "Deploying contracts..."
    cd "$FOUNDRY_REPO_PATH"
    if [ -f "./scripts/deploy_all_test_env1.sh" ]; then
        ./scripts/deploy_all_test_env1.sh
        log_success "Contracts deployed"
    else
        log_warn "Deployment script not found. Deploy contracts manually."
    fi

    # Save new snapshot
    cast rpc anvil_dumpState --rpc-url http://127.0.0.1:8545 > "$ANVIL_SNAPSHOT_DIR/post-deploy.hex"
    log_success "Anvil snapshot updated"
fi

# ---------------------------------------------
# Summary
# ---------------------------------------------
echo ""
echo "==========================================="
echo "  Reset Complete!"
echo "==========================================="
echo ""
echo "Next steps:"
echo "  1. Start the stack: ./scripts/dev.sh"
echo "  2. Mine blocks and fund wallets"
echo "  3. Set up bridge account mappings"
echo ""
