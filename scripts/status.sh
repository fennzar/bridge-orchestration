#!/bin/bash

# ===========================================
# Zephyr Bridge Stack - Status
# ===========================================
# Quick status check of all services.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

ok() { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
info() { echo -e "${BLUE}ℹ${NC} $1"; }

echo -e "${BOLD}==========================================${NC}"
echo -e "${BOLD}  Zephyr Bridge Stack - Status${NC}"
echo -e "${BOLD}==========================================${NC}"
echo ""

# ---------------------------------------------
# Docker Services
# ---------------------------------------------
echo -e "${CYAN}━━━ Docker Services ━━━${NC}"

check_docker_service() {
    local name=$1
    local port=$2

    if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^zephyr-${name}$"; then
        fail "$name: not running"
        return 1
    fi

    local status=$(docker inspect --format='{{.State.Health.Status}}' "zephyr-${name}" 2>/dev/null)
    if [ "$status" = "healthy" ]; then
        ok "$name: healthy (port $port)"
    elif [ "$status" = "starting" ]; then
        warn "$name: starting (port $port)"
    else
        warn "$name: running but unhealthy (port $port)"
    fi
}

if ! docker ps &>/dev/null; then
    fail "Docker: cannot connect (permission denied?)"
else
    check_docker_service "redis" 6379
    check_docker_service "postgres" 5432
    check_docker_service "anvil" 8545
fi

echo ""

# ---------------------------------------------
# Overmind Processes
# ---------------------------------------------
echo -e "${CYAN}━━━ Overmind Processes ━━━${NC}"

if [ ! -S "$ORCH_DIR/.overmind-dev.sock" ]; then
    fail "Overmind: not running (no socket)"
    echo "    Start with: make dev-apps"
else
    # Get overmind status
    overmind_output=$(overmind status -s "$ORCH_DIR/.overmind-dev.sock" 2>&1)
    if echo "$overmind_output" | grep -q "connection refused"; then
        fail "Overmind: socket exists but not responding"
        echo "    Try: rm .overmind-dev.sock && make dev-apps"
    else
        while IFS= read -r line; do
            if [[ "$line" =~ ^([a-z0-9_-]+)[[:space:]]+([0-9]+)[[:space:]]+(running|stopped|dead) ]]; then
                name="${BASH_REMATCH[1]}"
                pid="${BASH_REMATCH[2]}"
                status="${BASH_REMATCH[3]}"

                case "$name" in
                    bridge-web) port="7050" ;;
                    bridge-api) port="7051" ;;
                    bridge-watchers) port="-" ;;
                    engine-web) port="7000" ;;
                    engine-watchers) port="-" ;;
                    dashboard) port="7100" ;;
                    *) port="" ;;
                esac

                if [ "$status" = "running" ]; then
                    if [ -n "$port" ]; then
                        ok "$name: running (port $port, pid $pid)"
                    else
                        ok "$name: running (pid $pid)"
                    fi
                else
                    fail "$name: $status"
                fi
            fi
        done <<< "$overmind_output"
    fi
fi

echo ""

# ---------------------------------------------
# Chain Status
# ---------------------------------------------
echo -e "${CYAN}━━━ Chain Status ━━━${NC}"

# Anvil
FOUNDRY_BIN="${HOME}/.foundry/bin"
anvil_block=$("$FOUNDRY_BIN/cast" block-number --rpc-url http://127.0.0.1:8545 2>/dev/null)
if [ -n "$anvil_block" ]; then
    ok "Anvil: block $anvil_block"
else
    fail "Anvil: not responding"
fi

# Detect DEVNET mode: fake oracle on port 5555 means DEVNET
IS_DEVNET=false
if curl -s -m 2 http://127.0.0.1:5555/status >/dev/null 2>&1; then
    IS_DEVNET=true
fi

if [ "$IS_DEVNET" = true ]; then
    info "Mode: DEVNET (fake oracle detected)"

    # Delegate chain/wallet status to fresh-devnet
    source "$SCRIPT_DIR/lib/devnet.sh"
    resolve_fresh_devnet 2>/dev/null && {
        echo ""
        "$FRESH_DEVNET" status
    } || {
        # Fallback: basic DEVNET status
        zephyr_info=$(curl -s -m 3 http://127.0.0.1:47767/json_rpc \
            -d '{"jsonrpc":"2.0","id":"0","method":"get_info"}' \
            -H 'Content-Type: application/json' 2>/dev/null)
        if [ -n "$zephyr_info" ]; then
            height=$(echo "$zephyr_info" | jq -r '.result.height // empty' 2>/dev/null)
            [ -n "$height" ] && ok "Zephyr DEVNET: height $height" || warn "Zephyr DEVNET: responding but no height"
        else
            fail "Zephyr DEVNET: not responding on port 47767"
        fi
    }
else
    # Legacy mainnet-fork mode (deprecated — kept as fallback)
    zephyr_info=$(curl -s -m 3 http://127.0.0.1:48081/json_rpc \
        -d '{"jsonrpc":"2.0","id":"0","method":"get_info"}' \
        -H 'Content-Type: application/json' 2>/dev/null)

    if [ -n "$zephyr_info" ]; then
        height=$(echo "$zephyr_info" | jq -r '.result.height // empty' 2>/dev/null)
        if [ -n "$height" ]; then
            ok "Zephyr: height $height"
        else
            warn "Zephyr: responding but no height"
        fi
    else
        fail "Zephyr: not responding on port 48081"
    fi
fi

echo ""

# ---------------------------------------------
# Wallet RPCs
# ---------------------------------------------
echo -e "${CYAN}━━━ Wallet RPCs ━━━${NC}"

check_wallet_rpc() {
    local name=$1
    local port=$2

    local response=$(curl -s -m 2 http://127.0.0.1:$port/json_rpc \
        -d '{"jsonrpc":"2.0","id":"0","method":"get_address"}' \
        -H 'Content-Type: application/json' 2>/dev/null)

    if [ -n "$response" ] && echo "$response" | jq -e '.result.address' &>/dev/null; then
        local addr=$(echo "$response" | jq -r '.result.address' | head -c 20)
        ok "$name: responding (${addr}...)"
    else
        fail "$name: not responding on port $port"
    fi
}

if [ "$IS_DEVNET" = true ]; then
    check_wallet_rpc "gov-wallet" 48769
    check_wallet_rpc "miner-wallet" 48767
    check_wallet_rpc "test-wallet" 48768
else
    check_wallet_rpc "wallet-bridge" 17777
    check_wallet_rpc "wallet-exchange" 17778
    check_wallet_rpc "wallet-testuser" 17779
fi

echo ""

# ---------------------------------------------
# Status Dashboard
# ---------------------------------------------
echo -e "${CYAN}━━━ Status Dashboard ━━━${NC}"

dash_response=$(curl -s -m 10 http://127.0.0.1:7100/api/status 2>/dev/null)
if [ -n "$dash_response" ] && echo "$dash_response" | jq -e '.timestamp' &>/dev/null; then
    ok "Dashboard: running at http://localhost:7100"
else
    fail "Dashboard: not responding on port 7100"
    echo "    Start with: cd status-dashboard && pnpm dev"
fi

echo ""
echo -e "${BOLD}==========================================${NC}"
