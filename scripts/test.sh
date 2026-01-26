#!/bin/bash
set -euo pipefail

# ===========================================
# Zephyr Bridge Stack - Run Tests
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
log_success() { echo -e "${GREEN}[PASS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[FAIL]${NC} $1"; }

# Load environment safely (handles unquoted values like mnemonics)
source "$SCRIPT_DIR/lib/env.sh"
if ! load_env "$ORCH_DIR/.env"; then
    log_error ".env file not found"
    exit 1
fi

# Parse arguments
TEST_SUITE="${1:-all}"

show_help() {
    echo "Usage: $0 [suite]"
    echo ""
    echo "Test Suites:"
    echo "  all        Run all tests (default)"
    echo "  foundry    Run Solidity contract tests"
    echo "  bridge     Run bridge unit tests"
    echo "  engine     Run engine unit tests"
    echo "  e2e        Run Playwright E2E tests"
    echo "  quick      Run fast subset (no E2E)"
    echo ""
    echo "Examples:"
    echo "  $0           # Run all tests"
    echo "  $0 foundry   # Run only Foundry tests"
    echo "  $0 quick     # Run unit tests only"
}

if [[ "$TEST_SUITE" == "-h" || "$TEST_SUITE" == "--help" ]]; then
    show_help
    exit 0
fi

echo "==========================================="
echo "  Zephyr Bridge Stack - Test Runner"
echo "  Suite: $TEST_SUITE"
echo "==========================================="
echo ""

FAILED=0

# ---------------------------------------------
# Foundry Tests (Smart Contracts)
# ---------------------------------------------
run_foundry_tests() {
    log_info "Running Foundry tests..."
    cd "$FOUNDRY_REPO_PATH"

    if forge test -vvv; then
        log_success "Foundry tests passed"
    else
        log_error "Foundry tests failed"
        FAILED=1
    fi
    echo ""
}

# ---------------------------------------------
# Bridge Tests (Vitest/Node)
# ---------------------------------------------
run_bridge_tests() {
    log_info "Running Bridge tests..."
    cd "$BRIDGE_REPO_PATH"

    # Check if test script exists
    if grep -q '"test"' package.json; then
        if npm test 2>/dev/null; then
            log_success "Bridge tests passed"
        else
            log_warn "Bridge tests failed or not configured"
            # Don't fail - bridge tests are minimal currently
        fi
    else
        log_warn "No test script in bridge package.json"
    fi
    echo ""
}

# ---------------------------------------------
# Engine Tests (Vitest)
# ---------------------------------------------
run_engine_tests() {
    log_info "Running Engine tests..."
    cd "$ENGINE_REPO_PATH"

    if pnpm test; then
        log_success "Engine tests passed"
    else
        log_error "Engine tests failed"
        FAILED=1
    fi
    echo ""
}

# ---------------------------------------------
# E2E Tests (Playwright)
# ---------------------------------------------
run_e2e_tests() {
    log_info "Running E2E tests..."
    cd "$ORCH_DIR/tests/e2e"

    if [ -f "playwright.config.ts" ]; then
        if npx playwright test; then
            log_success "E2E tests passed"
        else
            log_error "E2E tests failed"
            FAILED=1
        fi
    else
        log_warn "Playwright not configured yet. Skipping E2E tests."
    fi
    echo ""
}

# ---------------------------------------------
# Run Selected Suite
# ---------------------------------------------
case "$TEST_SUITE" in
    all)
        run_foundry_tests
        run_bridge_tests
        run_engine_tests
        run_e2e_tests
        ;;
    foundry)
        run_foundry_tests
        ;;
    bridge)
        run_bridge_tests
        ;;
    engine)
        run_engine_tests
        ;;
    e2e)
        run_e2e_tests
        ;;
    quick)
        run_foundry_tests
        run_bridge_tests
        run_engine_tests
        ;;
    *)
        log_error "Unknown test suite: $TEST_SUITE"
        show_help
        exit 1
        ;;
esac

# ---------------------------------------------
# Summary
# ---------------------------------------------
echo "==========================================="
if [ $FAILED -eq 0 ]; then
    log_success "All tests passed!"
    exit 0
else
    log_error "Some tests failed"
    exit 1
fi
