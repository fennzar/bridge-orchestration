#!/bin/bash
set -euo pipefail

# ===========================================
# Setup Infrastructure (Docker, Anvil, Contracts)
# ===========================================
# Starts Docker services and deploys EVM contracts.
# Does NOT touch Zephyr or application repos.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Foundry tools path
FOUNDRY_BIN="${HOME}/.foundry/bin"

echo "==========================================="
echo "  Infrastructure Setup"
echo "==========================================="
echo ""

# Load environment
source "$SCRIPT_DIR/lib/env.sh"
if ! load_env "$ORCH_DIR/.env"; then
    log_error ".env not found. Run: cp .env.example .env"
    exit 1
fi

# ---------------------------------------------
# Create Directories
# ---------------------------------------------
log_info "Creating directories..."

mkdir -p "$ZEPHYR_DATA_DIR/node1"
mkdir -p "$ZEPHYR_DATA_DIR/node2"
mkdir -p "$ZEPHYR_WALLET_DIR"
mkdir -p "${ZEPHYR_SNAPSHOT_DIR:-$ORCH_DIR/snapshots/zephyr}"
mkdir -p "${ANVIL_SNAPSHOT_DIR:-$ORCH_DIR/snapshots/anvil}"
mkdir -p "$ORCH_DIR/logs"
mkdir -p "$ORCH_DIR/config"

log_success "Directories created"

# ---------------------------------------------
# Start Docker Services
# ---------------------------------------------
log_info "Starting Docker services..."

cd "$ORCH_DIR"
docker compose up -d

log_info "Waiting for services to be ready..."
sleep 3

# Check Redis
if docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
    log_success "Redis is ready"
else
    log_error "Redis failed to start"
    docker compose logs redis
    exit 1
fi

# Check Postgres
if docker compose exec -T postgres pg_isready -U zephyr 2>/dev/null | grep -q "accepting"; then
    log_success "PostgreSQL is ready"
else
    log_error "PostgreSQL failed to start"
    docker compose logs postgres
    exit 1
fi

# Check Anvil
if cast block-number --rpc-url http://127.0.0.1:8545 &>/dev/null || \
   "$FOUNDRY_BIN/cast" block-number --rpc-url http://127.0.0.1:8545 &>/dev/null; then
    log_success "Anvil is ready"
else
    log_error "Anvil failed to start"
    docker compose logs anvil
    exit 1
fi

# ---------------------------------------------
# Deploy Contracts
# ---------------------------------------------
log_info "Deploying contracts to Anvil..."
"$SCRIPT_DIR/deploy-contracts.sh"

echo ""
log_success "Infrastructure setup complete!"
echo ""
echo "Services running:"
echo "  - Redis:      localhost:6379"
echo "  - PostgreSQL: localhost:5432"
echo "  - Anvil:      localhost:8545"
echo ""
