#!/bin/bash
set -euo pipefail
# ===========================================
# Pre-start repo check: fetch and prompt if behind
# ===========================================
# Called before `make dev` and `make testnet-v2`.
# Fetches all repos, shows status, and if any are behind
# offers to pull before continuing.
#
# If bridge-orchestration itself is updated, exits with code 2
# to signal the caller to re-run (scripts may have changed).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"
PARENT="$(cd "$ORCH_DIR/.." && pwd)"

source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/repos.sh"

pad() { printf "%-${2:-20}s" "$1"; }

echo ""
echo "Checking repositories..."
echo ""

repos_fetch_status
behind=$?

if [ "$behind" -gt 0 ]; then
    echo ""
    echo -e "  ${YELLOW}${behind} repo(s) behind remote.${NC}"
    echo ""
    if [ -t 0 ] && [ -t 1 ]; then
        printf "  Pull latest changes? [Y/n] "
        read -r ans </dev/tty
        ans="${ans:-y}"
        if [[ "$ans" =~ ^[yY]$ ]]; then
            echo ""
            self_updated=false
            for entry in "${REPOS[@]}"; do
                IFS='|' read -r dir _ _ <<< "$entry"
                local_path="$PARENT/$dir"
                [ -d "$local_path/.git" ] || continue

                upstream=$(git -C "$local_path" rev-parse --abbrev-ref "@{upstream}" 2>/dev/null || echo "")
                [ -z "$upstream" ] && continue

                local_sha=$(git -C "$local_path" rev-parse HEAD 2>/dev/null)
                remote_sha=$(git -C "$local_path" rev-parse "$upstream" 2>/dev/null)
                [ "$local_sha" = "$remote_sha" ] && continue

                merge_base=$(git -C "$local_path" merge-base "$local_sha" "$remote_sha" 2>/dev/null)
                [ "$merge_base" != "$local_sha" ] && continue

                # Behind — attempt pull
                short_remote=$(git -C "$local_path" rev-parse --short "$upstream" 2>/dev/null)

                # Check for dirty worktree
                if ! git -C "$local_path" diff --quiet 2>/dev/null || \
                   ! git -C "$local_path" diff --cached --quiet 2>/dev/null; then
                    echo -e "  ${YELLOW}!${NC} $(pad "$dir" 25)skipped (uncommitted changes)"
                    continue
                fi

                if git -C "$local_path" pull --ff-only --quiet 2>/dev/null; then
                    echo -e "  ${GREEN}✓${NC} $(pad "$dir" 25)pulled → ${short_remote}"
                    [ "$dir" = "bridge-orchestration" ] && self_updated=true
                else
                    echo -e "  ${RED}✗${NC} $(pad "$dir" 25)pull failed"
                fi
            done

            if $self_updated; then
                echo ""
                echo -e "  ${YELLOW}${BOLD}bridge-orchestration was updated — re-run your command.${NC}"
                echo ""
                exit 2
            fi
            echo ""
        fi
    else
        echo -e "  ${DIM}Non-interactive — skipping pull.${NC}"
    fi
else
    echo ""
fi
