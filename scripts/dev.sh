#!/bin/bash
set -euo pipefail

# ===========================================
# DEPRECATED - Mainnet-Fork / Legacy Dev Script
# ===========================================
# This script is from the pre-Docker-Compose era when Zephyr nodes
# and wallets ran natively via Overmind. Use `make dev` instead.
#
# For DEVNET (recommended): make dev-init / make dev / make dev-reset
# ===========================================

echo ""
echo "=============================================="
echo "  WARNING: scripts/dev.sh is DEPRECATED"
echo "  Use 'make dev' (or 'make dev-init' for first run) instead."
echo "=============================================="
echo ""

# ===========================================
# Zephyr Bridge Stack - Start Development (DEPRECATED)
# ===========================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"
FOUNDRY_BIN="${HOME}/.foundry/bin"

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

# ---------------------------------------------
# Run prerequisite verification
# ---------------------------------------------
if [ "${SKIP_VERIFY:-}" != "1" ]; then
    log_info "Running prerequisite verification..."
    if ! "$SCRIPT_DIR/verify.sh" --quiet; then
        log_error "Prerequisite check failed. Run './scripts/verify.sh' for details."
        exit 1
    fi
    log_success "Prerequisites verified"
fi

# Load environment safely (handles unquoted values like mnemonics)
source "$SCRIPT_DIR/lib/env.sh"
if ! load_env "$ORCH_DIR/.env"; then
    log_error ".env file not found. Run ./scripts/setup.sh first."
    exit 1
fi

# Parse arguments
DETACHED=false
ENV_OVERRIDE=""
USE_DEVNET=false
DEVNET_RESET=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -d|--detached)
            DETACHED=true
            shift
            ;;
        --devnet)
            USE_DEVNET=true
            export ZEPHYR_CHAIN_MODE=devnet
            export FAKE_ORDERBOOK_ENABLED=true
            shift
            ;;
        --devnet-reset|--reset)
            USE_DEVNET=true
            DEVNET_RESET=true
            export ZEPHYR_CHAIN_MODE=devnet
            export FAKE_ORDERBOOK_ENABLED=true
            shift
            ;;
        --env)
            ENV_OVERRIDE="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  -d, --detached    Run in background"
            echo "  --devnet          DEVNET mode: fresh chain, controllable oracle"
            echo "  --devnet-reset    Reset DEVNET to checkpoint (recommended between tests)"
            echo "  --env <env>       Override BRIDGE_ENV (local, sepolia)"
            echo "  -h, --help        Show this help"
            echo ""
            echo "DEVNET Modes (recommended for testing):"
            echo "  --devnet          Full init (~5-6 min first time, creates checkpoint)"
            echo "  --devnet-reset    Light reset (~30 sec) - USE THIS BETWEEN TESTS"
            echo ""
            echo "Typical workflow:"
            echo "  ./scripts/dev.sh --devnet        # First time"
            echo "  ./scripts/dev.sh --devnet-reset  # Between tests (fast reset)"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Apply environment override
if [ -n "$ENV_OVERRIDE" ]; then
    export BRIDGE_ENV="$ENV_OVERRIDE"
    export NEXT_PUBLIC_BRIDGE_ENV="$ENV_OVERRIDE"
    log_info "Environment override: $ENV_OVERRIDE"
fi

# Determine chain mode
CHAIN_MODE="${ZEPHYR_CHAIN_MODE:-mainnet-fork}"
if [ "$USE_DEVNET" = true ]; then
    CHAIN_MODE="devnet"
fi

echo "==========================================="
echo "  Zephyr Bridge Stack - Starting"
echo "  Environment: $BRIDGE_ENV"
echo "  Chain Mode:  $CHAIN_MODE"
echo "==========================================="
echo ""

# ---------------------------------------------
# Kill stale Zephyr processes from previous runs
# (Skip in DEVNET mode - fresh-devnet manages its own processes)
# ---------------------------------------------
if [ "$USE_DEVNET" = false ]; then
    if pgrep -f "zephyrd.*--data-dir.*node" >/dev/null 2>&1 || pgrep -f "zephyr-wallet-rpc" >/dev/null 2>&1; then
        log_warn "Found stale Zephyr processes from a previous run, killing..."
        pkill -f "zephyrd.*--data-dir.*node" 2>/dev/null || true
        pkill -f "zephyr-wallet-rpc" 2>/dev/null || true
        sleep 1
        # Force kill if still alive
        pkill -9 -f "zephyrd.*--data-dir.*node" 2>/dev/null || true
        pkill -9 -f "zephyr-wallet-rpc" 2>/dev/null || true
        log_success "Stale processes cleaned up"
    fi
fi

# Clean up stale overmind state
rm -rf /tmp/overmind-bridge-orchestration-* 2>/dev/null || true

# ---------------------------------------------
# Start Docker Services
# ---------------------------------------------
log_info "Starting Docker services..."
cd "$ORCH_DIR"
# Start services individually — if Redis port is taken by a system instance,
# Postgres and Anvil should still start fine.
docker compose up -d postgres anvil 2>/dev/null || true
docker compose up -d redis 2>/dev/null || true

# Wait for services
sleep 3

# Verify Docker services — Redis can be either Docker or system instance
if redis-cli ping 2>/dev/null | grep -q "PONG"; then
    log_success "Redis ready"
elif docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q "PONG"; then
    log_success "Redis ready (Docker)"
else
    log_error "Redis not responding (neither system nor Docker)"
    exit 1
fi

if ! docker compose exec -T postgres pg_isready -U zephyr 2>/dev/null | grep -q "accepting"; then
    log_error "PostgreSQL not responding"
    exit 1
fi
log_success "PostgreSQL ready"

BLOCK_NUM=$("$FOUNDRY_BIN/cast" block-number --rpc-url http://127.0.0.1:8545 2>/dev/null || echo "")
if [ -z "$BLOCK_NUM" ]; then
    log_error "Anvil not responding"
    exit 1
fi
log_success "Anvil ready (block $BLOCK_NUM)"

# ---------------------------------------------
# Check Zephyr LMDB (mainnet-fork) or DEVNET
# ---------------------------------------------
if [ "$CHAIN_MODE" = "devnet" ]; then
    # Resolve fresh-devnet path
    source "$SCRIPT_DIR/lib/devnet.sh"
    resolve_fresh_devnet

    # Check if fresh-devnet is already running
    DEVNET_RUNNING=false
    if curl -s http://127.0.0.1:5555/status >/dev/null 2>&1; then
        DEVNET_RUNNING=true
        log_success "DEVNET already running (fake oracle responding)"
    fi

    # Handle reset mode
    if [ "$DEVNET_RESET" = true ]; then
        if [ "$DEVNET_RUNNING" = false ]; then
            log_error "DEVNET not running. Use --devnet for full init first."
            exit 1
        fi
        log_info "Resetting DEVNET to post-init state..."
        "$FRESH_DEVNET" reset
        log_success "DEVNET reset complete"
    elif [ "$DEVNET_RUNNING" = false ]; then
        log_info "Starting DEVNET (fake oracle, nodes, wallets)..."
        log_info "This takes ~5-6 minutes for initial state setup."
        log_info "You can monitor progress in a separate terminal:"
        log_info "  tail -f /tmp/zephyr-devnet/logs/*.log"
        echo ""

        "$FRESH_DEVNET" start new

        log_success "DEVNET started"

        # Save checkpoint for future resets
        log_info "Saving checkpoint for future resets..."
        "$FRESH_DEVNET" checkpoint
    fi
else
    # Mainnet fork mode - check LMDB
    if [ ! -d "$ZEPHYR_DATA_DIR/node1/lmdb" ] || [ ! -d "$ZEPHYR_DATA_DIR/node2/lmdb" ]; then
        log_warn "Zephyr LMDB not found."
        log_warn "Run ./scripts/init-zephyr-lmdb.sh to initialize from mainnet."
        echo ""
        read -p "Continue anyway (Zephyr processes will fail)? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
fi

# ---------------------------------------------
# Check Zephyr Wallets (mainnet-fork only)
# ---------------------------------------------
if [ "$CHAIN_MODE" != "devnet" ]; then
    if [ ! -f "$ZEPHYR_WALLET_DIR/localbridge" ]; then
        log_warn "Zephyr wallets not found. Run ./scripts/setup.sh to create them."
    fi
fi

# ---------------------------------------------
# Start Overmind
# ---------------------------------------------
log_info "Starting processes with Overmind..."
cd "$ORCH_DIR"

# Export paths for Procfile
export ZEPHYR_BIN_PATH
export ZEPHYR_DATA_DIR
export ZEPHYR_WALLET_DIR
export BRIDGE_REPO_PATH
export ENGINE_REPO_PATH
export ZEPHYR_REPO_PATH
export ORCHESTRATION_PATH

# Select Procfile based on chain mode
if [ "$CHAIN_MODE" = "devnet" ]; then
    PROCFILE="Procfile.devnet"
    # Export DEVNET-specific paths
    export ZEPHYR_DEVNET_BUILD_DIR="${ZEPHYR_DEVNET_BUILD_DIR:-$ZEPHYR_REPO_PATH/build/Linux/devnet/release}"
    export DEVNET_ORACLE_PORT="${DEVNET_ORACLE_PORT:-5555}"
    export FAKE_ORDERBOOK_PORT="${FAKE_ORDERBOOK_PORT:-5556}"
    export FAKE_ORDERBOOK_SPREAD_BPS="${FAKE_ORDERBOOK_SPREAD_BPS:-50}"
    export FAKE_ORDERBOOK_DEPTH_LEVELS="${FAKE_ORDERBOOK_DEPTH_LEVELS:-20}"
    log_info "Using DEVNET mode with Procfile.devnet"
else
    PROCFILE="Procfile"
    log_info "Using mainnet-fork mode with Procfile"
fi

if [ "$DETACHED" = true ]; then
    log_info "Starting in detached mode..."
    overmind start -D -f "$PROCFILE"
    log_success "Stack started in background"
    echo ""
    echo "Commands:"
    echo "  overmind status         # Check process status"
    echo "  overmind connect <proc> # Attach to process (Ctrl-B D to detach)"
    echo "  overmind restart <proc> # Restart process"
    echo "  ./scripts/stop.sh       # Stop everything"
    if [ "$CHAIN_MODE" = "devnet" ]; then
        echo ""
        echo "DEVNET Commands:"
        echo "  ./scripts/set-oracle-price.sh <usd>  # Change oracle price"
        echo "  ./scripts/set-scenario.sh <preset>   # Quick presets: normal, defensive, crisis"
    fi
else
    log_info "Starting in foreground (Ctrl+C to stop)..."
    echo ""
    echo "Process names (for overmind connect):"
    if [ "$CHAIN_MODE" = "devnet" ]; then
        echo "  Orderbook: fake-orderbook"
        echo "  Bridge:    bridge-web, bridge-api, bridge-watchers"
        echo "  Engine:    engine-web, engine-watchers"
        echo ""
        echo "DEVNET (managed by fresh-devnet, use run.sh status):"
        echo "  Oracle:  http://127.0.0.1:5555/status"
        echo "  Node1:   http://127.0.0.1:47767/json_rpc"
        echo "  Wallets: gov=48769, miner=48767, test=48768"
    else
        echo "  Zephyr:  zephyr-node1, zephyr-node2"
        echo "  Wallets: wallet-mining, wallet-bridge, wallet-exchange, wallet-testuser"
        echo "  Bridge:  bridge-web, bridge-api, bridge-watchers"
        echo "  Engine:  engine-web, engine-watchers"
    fi
    echo ""
    overmind start -f "$PROCFILE"
fi
