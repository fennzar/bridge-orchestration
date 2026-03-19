#!/bin/bash
set -euo pipefail

# ===========================================
# Pre-start Reset Check
# ===========================================
# Checks if a reset is required before starting the dev stack.
# Called from `make dev` after check-repos.sh.
#
# Compares the current bridge-orchestration HEAD against the recorded
# HEAD from the last dev-setup, and checks config/reset-required.json
# to determine if a reset is needed.
#
# Exit codes:
#   0 — OK to continue
#   1 — Reset required, cannot continue

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/repos.sh"

BUILD_STATE="$ORCH_DIR/.state/build.json"
RESET_MARKER="$ORCH_DIR/config/reset-required.json"

# ─── No build state file ───
if [ ! -f "$BUILD_STATE" ]; then
    echo ""
    echo -e "  ${YELLOW}${BOLD}No build state found${NC}"
    echo ""
    echo -e "  This means dev-setup hasn't been run (or was run before"
    echo -e "  the reset-tracking system was added)."
    echo ""
    echo -e "  Recommended: ${BOLD}make dev-reset-hard && make dev-setup && make dev${NC}"
    echo ""

    # Prompt if interactive, otherwise warn and continue
    if [ -t 0 ] && [ -t 1 ]; then
        printf "  Continue anyway? [y/N] "
        read -r ans </dev/tty
        ans="${ans:-n}"
        if [[ ! "$ans" =~ ^[yY]$ ]]; then
            exit 1
        fi
    else
        echo -e "  ${DIM}Non-interactive — continuing with warning.${NC}"
    fi
    echo ""
    exit 0
fi

# ─── Build state exists — compare HEADs ───
RECORDED_HEAD=$(python3 -c "
import json, sys
with open('$BUILD_STATE') as f:
    d = json.load(f)
print(d.get('repos', {}).get('bridge-orchestration', ''))
" 2>/dev/null || echo "")

if [ -z "$RECORDED_HEAD" ]; then
    # Malformed build state — treat as missing
    log_warn "Build state missing bridge-orchestration HEAD — skipping reset check"
    exit 0
fi

CURRENT_HEAD=$(git -C "$ORCH_DIR" rev-parse --short HEAD 2>/dev/null || echo "")

if [ -z "$CURRENT_HEAD" ]; then
    # Not a git repo somehow — skip check
    exit 0
fi

# If HEADs match, no check needed
if [ "$CURRENT_HEAD" = "$RECORDED_HEAD" ]; then
    exit 0
fi

# ─── HEADs differ — check reset marker ───
if [ ! -f "$RESET_MARKER" ]; then
    # No reset marker file — continue silently
    exit 0
fi

RESET_LEVEL=$(python3 -c "
import json, sys
with open('$RESET_MARKER') as f:
    d = json.load(f)
print(d.get('reset', 'none'))
" 2>/dev/null || echo "none")

if [ "$RESET_LEVEL" = "none" ]; then
    exit 0
fi

# Read the full marker details
RESET_SINCE=$(python3 -c "
import json
with open('$RESET_MARKER') as f:
    d = json.load(f)
print(d.get('since', ''))
" 2>/dev/null || echo "")

RESET_REASON=$(python3 -c "
import json
with open('$RESET_MARKER') as f:
    d = json.load(f)
print(d.get('reason', 'Unknown reason'))
" 2>/dev/null || echo "Unknown reason")

# Check if the "since" commit is between the old HEAD and current HEAD
# i.e., the breaking change was introduced after the last setup
if [ -n "$RESET_SINCE" ]; then
    # Check if the since commit is an ancestor of current HEAD (it should be)
    # and is NOT an ancestor of the recorded HEAD (it was introduced after setup)
    since_in_current=$(git -C "$ORCH_DIR" merge-base --is-ancestor "$RESET_SINCE" "$CURRENT_HEAD" 2>/dev/null && echo "yes" || echo "no")
    since_in_recorded=$(git -C "$ORCH_DIR" merge-base --is-ancestor "$RESET_SINCE" "$RECORDED_HEAD" 2>/dev/null && echo "yes" || echo "no")

    if [ "$since_in_current" = "no" ]; then
        # The "since" commit isn't even in our history — skip
        exit 0
    fi

    if [ "$since_in_recorded" = "yes" ]; then
        # The "since" commit was already present at last setup — no action needed
        exit 0
    fi
fi

# ─── Reset is required ───
# Determine the command to run
case "$RESET_LEVEL" in
    soft)
        RESET_CMD="make dev-reset && make dev"
        ;;
    hard)
        RESET_CMD="make dev-reset-hard && make dev-setup && make dev"
        ;;
    delete)
        RESET_CMD="make dev-delete && make dev-init && make dev-setup && make dev"
        ;;
    *)
        RESET_CMD="make dev-reset && make dev"
        ;;
esac

echo ""
echo -e "  ${YELLOW}${BOLD}Reset required${NC}"
echo ""
echo -e "  bridge-orchestration has been updated since your last setup."
echo -e "  Reason: ${RESET_REASON}"
echo ""
echo -e "  Run: ${BOLD}${RESET_CMD}${NC}"
echo ""
echo -e "  ${DIM}(Your current stack state is incompatible with the new code)${NC}"
echo ""

if [ "$RESET_LEVEL" = "soft" ]; then
    # Soft reset — prompt to continue or reset first
    if [ -t 0 ] && [ -t 1 ]; then
        printf "  Continue anyway? [y/N] "
        read -r ans </dev/tty
        ans="${ans:-n}"
        if [[ ! "$ans" =~ ^[yY]$ ]]; then
            exit 1
        fi
        echo ""
        exit 0
    else
        echo -e "  ${DIM}Non-interactive — continuing with warning.${NC}"
        echo ""
        exit 0
    fi
else
    # Hard or delete — do not allow continuing
    exit 1
fi
