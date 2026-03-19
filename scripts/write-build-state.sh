#!/bin/bash
set -euo pipefail

# ===========================================
# Write Build State
# ===========================================
# Records the current commit HEADs of all repos and EVM chain ID
# into .state/build.json after a successful dev-setup.
#
# Usage:
#   ./scripts/write-build-state.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"
PARENT="$(cd "$ORCH_DIR/.." && pwd)"

source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/env.sh"
source "$SCRIPT_DIR/lib/repos.sh"

load_env "$ORCH_DIR/.env" || { log_error ".env not found"; exit 1; }

# Create .state directory
mkdir -p "$ORCH_DIR/.state"

# Collect repo HEADs
REPO_JSON="{"
first=true
for entry in "${REPOS[@]}"; do
    IFS='|' read -r dir _ _ <<< "$entry"
    repo_path="$PARENT/$dir"
    if [ -d "$repo_path/.git" ]; then
        sha=$(git -C "$repo_path" rev-parse --short HEAD 2>/dev/null || echo "unknown")
        if $first; then
            first=false
        else
            REPO_JSON="$REPO_JSON,"
        fi
        REPO_JSON="$REPO_JSON"$'\n'"    \"$dir\": \"$sha\""
    fi
done
REPO_JSON="$REPO_JSON"$'\n'"  }"

# Read chain ID from env
CHAIN_ID="${EVM_CHAIN_ID:-31337}"

# Write build state
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "$ORCH_DIR/.state/build.json" <<EOF
{
  "timestamp": "$TIMESTAMP",
  "repos": $REPO_JSON,
  "chainId": $CHAIN_ID,
  "resetLevel": "setup"
}
EOF

log_success "Build state written to .state/build.json"
