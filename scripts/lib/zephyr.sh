#!/bin/bash
# ===========================================
# Zephyr CLI path resolution
# ===========================================
# Single source of truth for the zephyr-cli path. All scripts that shell out
# to the Zephyr wallet/daemon CLI should use these helpers instead of
# inlining `${ZEPHYR_REPO_PATH:-$(dirname "$ORCH_DIR")/zephyr}/tools/...`.
#
# Requires: ORCH_DIR set by caller.
#
# Usage:
#   source "$SCRIPT_DIR/lib/zephyr.sh"
#   ZEPHYR_CLI=$(get_zephyr_cli "$ORCH_DIR")
#   ZEPHYR_DEVNET_SH=$(get_zephyr_devnet_sh "$ORCH_DIR")

# Resolve the Zephyr repo path (env var or sibling fallback).
_get_zephyr_repo() {
    local orch_dir="$1"
    echo "${ZEPHYR_REPO_PATH:-$(dirname "$orch_dir")/zephyr}"
}

# Path to the high-level Python CLI (wallet ops, mine, send, etc.)
get_zephyr_cli() {
    local orch_dir="$1"
    echo "$(_get_zephyr_repo "$orch_dir")/tools/zephyr-cli/cli"
}

# Path to the devnet.sh helper script (reset, snapshot, etc.)
get_zephyr_devnet_sh() {
    local orch_dir="$1"
    echo "$(_get_zephyr_repo "$orch_dir")/tools/devnet.sh"
}
