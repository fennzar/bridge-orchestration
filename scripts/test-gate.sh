#!/bin/bash
set -euo pipefail

# ===========================================
# Test Gate — Per-Tier State Management
# ===========================================
# Each test tier is self-contained. This gate handles:
#   - precheck:  No state management — just check files/binaries
#   - infra/ops: Reset to post-init + start infra (no apps)
#   - bridge/engine/e2e: Ensure post-setup + full stack running
#
# Usage:
#   ./scripts/test-gate.sh precheck
#   ./scripts/test-gate.sh infra
#   ./scripts/test-gate.sh ops
#   ./scripts/test-gate.sh bridge
#   ./scripts/test-gate.sh engine
#   ./scripts/test-gate.sh e2e
#
# Environment variables:
#   CI=1  — Auto-accept all prompts (no hang in CI)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

TIER="${1:?Usage: test-gate.sh <tier>}"

# Helper: is this an interactive terminal (not CI)?
is_interactive() {
    [ -t 0 ] && [ "${CI:-}" != "1" ]
}

# ===========================================
# T1: precheck — no state management
# ===========================================
if [ "$TIER" = "precheck" ]; then
    # Precheck is pure file/binary checks. Load .env if it exists
    # (some checks need ZEPHYR_REPO_PATH etc.) but don't require it.
    if [ -f "$ORCH_DIR/.env" ]; then
        source "$SCRIPT_DIR/lib/env.sh"
        load_env "$ORCH_DIR/.env" 2>/dev/null || true
    fi
    echo "[test-gate] precheck: no state management needed"
    exit 0
fi

# ===========================================
# All other tiers: load shared libraries
# ===========================================
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/env.sh"
source "$SCRIPT_DIR/lib/compose.sh"

# Universal checks for tiers that need infrastructure
if [ ! -f "$ORCH_DIR/.env" ]; then
    log_error ".env not found. Run: make setup"
    exit 1
fi

load_env "$ORCH_DIR/.env" || { log_error "Failed to load .env"; exit 1; }

if grep -q '<KEYGEN:' "$ORCH_DIR/.env" 2>/dev/null; then
    log_error ".env contains unresolved <KEYGEN:> placeholders. Run: make keygen"
    exit 1
fi

if [ -z "${ZEPHYR_REPO_PATH:-}" ] || [ ! -d "$ZEPHYR_REPO_PATH" ]; then
    log_error "ZEPHYR_REPO_PATH not set or directory does not exist: ${ZEPHYR_REPO_PATH:-<unset>}"
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    log_error "Docker is not running"
    exit 1
fi

if [ ! -f "$ORCH_DIR/snapshots/chain/node1-lmdb.tar.gz" ]; then
    log_error "dev-init has not been run. Run: make dev-init"
    exit 1
fi

DC_DEV=$(get_dc_dev "$ORCH_DIR")
OVERMIND_SOCK="${OVERMIND_SOCK:-$ORCH_DIR/.overmind-dev.sock}"

log_success "Base prerequisites OK"

# ===========================================
# Tier-specific gate logic
# ===========================================

case "$TIER" in
    infra|ops)
        # Pre-setup tiers: need clean post-init state + infra running (no apps)
        echo ""
        log_info "Resetting to post-init state (dev-reset-hard)..."
        "$SCRIPT_DIR/dev-reset.sh" --hard
        log_success "Reset complete"
        echo ""

        log_info "Starting infrastructure..."
        $DC_DEV up -d
        "$SCRIPT_DIR/open-wallets.sh"

        log_success "Infrastructure ready (tier=$TIER)"
        ;;

    bridge|engine|e2e)
        # Post-setup tiers: need clean post-setup state + full stack running
        echo ""

        if [ ! -f "$ORCH_DIR/config/addresses.json" ]; then
            # No setup done yet — do full setup from scratch
            log_warn "config/addresses.json not found — full setup required"
            echo ""

            DO_SETUP=1
            if is_interactive; then
                printf "  Run dev-reset-hard + dev-test-setup now? [Y/n] "
                read -r ans
                case "$ans" in [nN]) log_error "Cannot run tests without setup. Run: make dev-test-setup"; exit 1 ;; esac
            fi

            if [ "$DO_SETUP" = "1" ]; then
                log_info "Resetting to post-init state..."
                "$SCRIPT_DIR/dev-reset.sh" --hard
                log_info "Running test setup (this deploys contracts + seeds)..."
                "$SCRIPT_DIR/dev-test-setup.sh"
                log_success "Test setup complete — stack running"
            fi
        else
            # Setup exists — reset to post-setup checkpoint
            log_info "Resetting to post-setup state (dev-reset)..."
            "$SCRIPT_DIR/dev-reset.sh"
            log_success "Reset complete"
            echo ""

            # Ensure stack is running
            STACK_RUNNING=true

            # Check overmind
            if [ -S "$OVERMIND_SOCK" ] && overmind status -s "$OVERMIND_SOCK" >/dev/null 2>&1; then
                : # running
            else
                STACK_RUNNING=false
            fi

            # Check infra (Anvil as proxy)
            if ! curl -sf http://127.0.0.1:8545 -X POST \
                -d '{"jsonrpc":"2.0","method":"eth_blockNumber","id":1}' \
                -H 'Content-Type: application/json' >/dev/null 2>&1; then
                STACK_RUNNING=false
            fi

            if [ "$STACK_RUNNING" = "false" ]; then
                log_info "Stack not running — starting via make dev..."
                make -C "$ORCH_DIR" dev
            fi
        fi

        log_success "Test gate ready (tier=$TIER)"
        ;;

    *)
        log_error "Unknown tier: $TIER"
        echo "  Valid tiers: precheck, infra, ops, bridge, engine, e2e"
        exit 1
        ;;
esac
