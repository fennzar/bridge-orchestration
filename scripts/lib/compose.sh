#!/bin/bash
# ===========================================
# Centralized Docker Compose Command Builder
# ===========================================
# Single source of truth for the compose chain.
# All scripts source this instead of defining DC_DEV independently.
#
# Usage:
#   source "$SCRIPT_DIR/lib/compose.sh"
#   DC_DEV=$(get_dc_dev "$ORCH_DIR")

get_dc_dev() {
    local orch_dir="$1"
    local zephyr_base="${ZEPHYR_REPO_PATH:-$(dirname "$orch_dir")/zephyr}/docker/compose.yml"

    if [ ! -f "$zephyr_base" ]; then
        echo "Error: Zephyr compose.yml not found at $zephyr_base" >&2
        echo "Check ZEPHYR_REPO_PATH in .env" >&2
        return 1
    fi

    echo "docker compose -p bridge-orch --env-file $orch_dir/.env" \
        "-f $zephyr_base" \
        "-f $orch_dir/docker/compose.bridge.yml" \
        "-f $orch_dir/docker/compose.engine.yml" \
        "-f $orch_dir/docker/compose.dev.yml" \
        "-f $orch_dir/docker/compose.blockscout.yml"
}
