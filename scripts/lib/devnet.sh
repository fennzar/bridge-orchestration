#!/bin/bash
# ===========================================
# Shared DEVNET Wrapper Helper
# ===========================================
# Resolves the path to zephyr's fresh-devnet/run.sh and validates it exists.
#
# Usage:
#   source "$(dirname "$0")/lib/devnet.sh"
#   resolve_fresh_devnet
#   exec "$FRESH_DEVNET" <command> "$@"

resolve_fresh_devnet() {
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[1]}")" && pwd)"
    local orch_dir
    orch_dir="$(dirname "$script_dir")"

    # Look locally first (vendored copy)
    if [[ -x "$orch_dir/tools/fresh-devnet/run.sh" ]]; then
        FRESH_DEVNET="$orch_dir/tools/fresh-devnet/run.sh"
        ZEPHYR_CLI="$orch_dir/tools/zephyr-cli/cli"
        return 0
    fi

    # Fall back to Zephyr repo
    source "$script_dir/lib/env.sh"
    load_env "$orch_dir/.env" 2>/dev/null || true
    local zephyr_repo="${ZEPHYR_REPO_PATH:-$(dirname "$orch_dir")/zephyr}"
    FRESH_DEVNET="$zephyr_repo/tools/fresh-devnet/run.sh"
    ZEPHYR_CLI="$zephyr_repo/tools/zephyr-cli/cli"

    if [[ ! -x "$FRESH_DEVNET" ]]; then
        echo "Error: fresh-devnet not found locally or at $FRESH_DEVNET" >&2
        echo "Run: ./scripts/sync-zephyr-artifacts.sh" >&2
        exit 1
    fi
}

require_zephyr_cli() {
    if [[ ! -x "$ZEPHYR_CLI" ]]; then
        echo "Error: zephyr-cli not found at $ZEPHYR_CLI" >&2
        exit 1
    fi
}
