#!/bin/bash
set -euo pipefail

# ===========================================
# Zephyr Bridge Stack - Stop Everything
# ===========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }

# Load environment safely (handles unquoted values like mnemonics)
source "$SCRIPT_DIR/lib/env.sh"
load_env "$ORCH_DIR/.env" 2>/dev/null || true

echo "==========================================="
echo "  Zephyr Bridge Stack - Stopping"
echo "==========================================="
echo ""

# ---------------------------------------------
# Stop Overmind Processes (bridge-orch)
# ---------------------------------------------
log_info "Stopping Overmind processes..."
cd "$ORCH_DIR"

OVERMIND_SOCK="$ORCH_DIR/.overmind-dev.sock"
if [ -S "$OVERMIND_SOCK" ]; then
    if overmind status -s "$OVERMIND_SOCK" >/dev/null 2>&1; then
        overmind quit -s "$OVERMIND_SOCK" 2>/dev/null || true
        for i in $(seq 1 10); do [ ! -S "$OVERMIND_SOCK" ] && break; sleep 0.5; done
        log_success "Overmind processes stopped"
    else
        log_info "Overmind not running (stale socket)"
    fi
    rm -f "$OVERMIND_SOCK"
else
    log_info "Overmind not running"
fi

# ---------------------------------------------
# Stop DEVNET (fresh-devnet's overmind)
# ---------------------------------------------
# Detect DEVNET mode: if fresh-devnet is running, delegate stop to it
if [ -S "/tmp/zephyr-devnet/overmind.sock" ] || curl -s --max-time 1 http://127.0.0.1:5555/status >/dev/null 2>&1; then
    log_info "DEVNET detected, stopping fresh-devnet..."
    source "$SCRIPT_DIR/lib/devnet.sh" 2>/dev/null || true
    resolve_fresh_devnet 2>/dev/null && {
        "$FRESH_DEVNET" stop 2>/dev/null || true
        log_success "Fresh-devnet stopped"
    } || {
        # Fallback: stop via overmind socket directly
        if [ -S "/tmp/zephyr-devnet/overmind.sock" ]; then
            overmind quit -s /tmp/zephyr-devnet/overmind.sock 2>/dev/null || true
            log_success "DEVNET overmind stopped (fallback)"
        fi
    }
fi

# Kill any lingering Zephyr processes (including detached daemons from previous runs)
log_info "Cleaning up Zephyr processes..."
pkill -f "zephyrd.*--data-dir.*node" 2>/dev/null || true
pkill -f "zephyr-wallet-rpc" 2>/dev/null || true

# Wait for processes to actually die
sleep 1
if pgrep -f "zephyrd.*--data-dir.*node" >/dev/null 2>&1 || pgrep -f "zephyr-wallet-rpc" >/dev/null 2>&1; then
    log_info "Processes still running, sending SIGKILL..."
    pkill -9 -f "zephyrd.*--data-dir.*node" 2>/dev/null || true
    pkill -9 -f "zephyr-wallet-rpc" 2>/dev/null || true
    sleep 1
fi

# Clean up stale overmind sockets and tmux sessions
log_info "Cleaning up stale overmind state..."
rm -rf /tmp/overmind-bridge-orchestration-* 2>/dev/null || true
for sock in /tmp/tmux-*/overmind-bridge-orchestration-*; do
    [ -e "$sock" ] && tmux -L "$(basename "$sock")" kill-server 2>/dev/null || true
done

# ---------------------------------------------
# Stop Docker Services
# ---------------------------------------------
STOP_DOCKER=false

# Check for --keep-infra flag
if [[ "${1:-}" != "--keep-infra" ]]; then
    read -p "Stop Docker services (Redis, Postgres, Anvil)? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        STOP_DOCKER=true
    fi
fi

if [ "$STOP_DOCKER" = true ]; then
    log_info "Stopping Docker services..."
    docker compose -f "$ORCH_DIR/docker-compose.yml" down
    log_success "Docker services stopped"
else
    log_info "Docker services kept running"
fi

echo ""
log_success "Stack stopped"
