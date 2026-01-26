#!/bin/bash
set -euo pipefail

# ===========================================
# Setup Applications (Bridge, Engine)
# ===========================================
# Installs dependencies and runs migrations for app repos.
# Run setup-infra.sh first.

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

# Foundry tools path
FOUNDRY_BIN="${HOME}/.foundry/bin"

echo "==========================================="
echo "  Application Setup"
echo "==========================================="
echo ""

# Load environment
source "$SCRIPT_DIR/lib/env.sh"
if ! load_env "$ORCH_DIR/.env"; then
    log_error ".env not found"
    exit 1
fi

# Sync env files to repos
log_info "Syncing environment files..."
"$SCRIPT_DIR/sync-env.sh"

# ---------------------------------------------
# Bridge Dependencies
# ---------------------------------------------
if [ -d "$BRIDGE_REPO_PATH" ]; then
    log_info "Installing bridge dependencies..."
    cd "$BRIDGE_REPO_PATH"
    pnpm install

    log_info "Running bridge database migrations..."
    DATABASE_URL="$DATABASE_URL_BRIDGE" pnpm exec prisma migrate dev --skip-generate 2>/dev/null || \
        log_warn "Bridge migrations may need attention"
    DATABASE_URL="$DATABASE_URL_BRIDGE" pnpm exec prisma generate

    log_success "Bridge setup complete"
else
    log_warn "Bridge repo not found at $BRIDGE_REPO_PATH"
fi

# ---------------------------------------------
# Engine Dependencies
# ---------------------------------------------
if [ -d "$ENGINE_REPO_PATH" ]; then
    log_info "Installing engine dependencies..."
    cd "$ENGINE_REPO_PATH"
    pnpm install

    log_info "Running engine database migrations..."
    pnpm db:generate
    pnpm db:migrate 2>/dev/null || log_warn "Engine migrations may need attention"

    log_success "Engine setup complete"
else
    log_warn "Engine repo not found at $ENGINE_REPO_PATH"
fi

# ---------------------------------------------
# Foundry Dependencies
# ---------------------------------------------
if [ -d "$FOUNDRY_REPO_PATH" ]; then
    log_info "Installing Foundry dependencies..."
    cd "$FOUNDRY_REPO_PATH"

    if command -v forge &>/dev/null; then
        forge install --no-git 2>/dev/null || forge install
    elif [ -x "$FOUNDRY_BIN/forge" ]; then
        "$FOUNDRY_BIN/forge" install --no-git 2>/dev/null || "$FOUNDRY_BIN/forge" install
    fi

    log_success "Foundry setup complete"
else
    log_warn "Foundry repo not found at $FOUNDRY_REPO_PATH"
fi

echo ""
log_success "Application setup complete!"
echo ""
