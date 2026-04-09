#!/bin/bash
set -euo pipefail
# ===========================================
# Cross-repo git status / diff
# ===========================================
# Usage:
#   make status-git          Fetch + file-level changes across all repos
#   make status-git-diff     Fetch + full unified diff across all repos

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"
PARENT="$(cd "$ORCH_DIR/.." && pwd)"

source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/repos.sh"

SHOW_DIFF=false
for arg in "$@"; do
    case "$arg" in
        --diff) SHOW_DIFF=true ;;
    esac
done

# ── Parallel fetch ────────────────────────
declare -A fetch_pids
fetch_count=0
for entry in "${REPOS[@]}"; do
    IFS='|' read -r dir _ _ _ <<< "$entry"
    local_path="$PARENT/$dir"
    [ -d "$local_path/.git" ] || continue
    git -C "$local_path" fetch --quiet 2>/dev/null &
    fetch_pids["$dir"]=$!
    fetch_count=$((fetch_count + 1))
done

# ── Diff mode ──────────────────────────────

if $SHOW_DIFF; then
    # Wait for all fetches before showing diffs
    wait 2>/dev/null || true

    any_diff=false
    for entry in "${REPOS[@]}"; do
        IFS='|' read -r dir _ _ _ <<< "$entry"
        local_path="$PARENT/$dir"
        [ -d "$local_path/.git" ] || continue

        diff_output=$(git -C "$local_path" diff --color 2>/dev/null) || true
        staged_output=$(git -C "$local_path" diff --cached --color 2>/dev/null) || true

        if [ -n "$diff_output" ] || [ -n "$staged_output" ]; then
            any_diff=true
            echo ""
            echo -e "${BOLD}━━━ ${dir} ━━━${NC}"
            [ -n "$staged_output" ] && echo "$staged_output"
            [ -n "$diff_output" ] && echo "$diff_output"
        fi
    done

    if ! $any_diff; then
        echo ""
        echo -e "  ${DIM}No diffs across any repo.${NC}"
    fi
    echo ""
    exit 0
fi

# ── Status mode ────────────────────────────

echo ""
echo -e "${BOLD}==========================================${NC}"
echo -e "${BOLD}  Cross-Repo Git Status${NC}"
echo -e "${BOLD}==========================================${NC}"

any_changes=false

for entry in "${REPOS[@]}"; do
    IFS='|' read -r dir _ _ expected_branch <<< "$entry"
    local_path="$PARENT/$dir"

    # Wait for this repo's fetch (others continue in parallel)
    if [ -n "${fetch_pids[$dir]:-}" ]; then
        wait "${fetch_pids[$dir]}" 2>/dev/null || true
    fi

    if [ ! -d "$local_path/.git" ]; then
        echo ""
        repo_status "$dir"
        continue
    fi

    # Gather file changes
    staged=$(git -C "$local_path" diff --cached --name-status 2>/dev/null) || true
    unstaged=$(git -C "$local_path" diff --name-status 2>/dev/null) || true
    untracked=$(git -C "$local_path" ls-files --others --exclude-standard 2>/dev/null) || true

    staged_count=0; [ -n "$staged" ] && staged_count=$(echo "$staged" | wc -l)
    unstaged_count=0; [ -n "$unstaged" ] && unstaged_count=$(echo "$unstaged" | wc -l)
    untracked_count=0; [ -n "$untracked" ] && untracked_count=$(echo "$untracked" | wc -l)
    file_changes=$((staged_count + unstaged_count + untracked_count))

    # ── Section 1: Current branch ─────────
    echo ""
    repo_status "$dir"
    repo_tracking_info "$dir" "$expected_branch"

    [ "$file_changes" -gt 0 ] && any_changes=true

    # File changes (part of current branch context)
    if [ -n "$staged" ]; then
        while IFS=$'\t' read -r status file; do
            case "$status" in
                A*) echo -e "    ${GREEN}+${NC} ${file}  ${DIM}(staged, new)${NC}" ;;
                M*) echo -e "    ${GREEN}~${NC} ${file}  ${DIM}(staged)${NC}" ;;
                D*) echo -e "    ${RED}-${NC} ${file}  ${DIM}(staged, deleted)${NC}" ;;
                R*) echo -e "    ${CYAN}→${NC} ${file}  ${DIM}(staged, renamed)${NC}" ;;
                *)  echo -e "    ${GREEN}~${NC} ${file}  ${DIM}(staged)${NC}" ;;
            esac
        done <<< "$staged"
    fi

    if [ -n "$unstaged" ]; then
        while IFS=$'\t' read -r status file; do
            case "$status" in
                M*) echo -e "    ${YELLOW}~${NC} ${file}" ;;
                D*) echo -e "    ${RED}-${NC} ${file}  ${DIM}(deleted)${NC}" ;;
                *)  echo -e "    ${YELLOW}~${NC} ${file}" ;;
            esac
        done <<< "$unstaged"
    fi

    if [ -n "$untracked" ]; then
        while IFS= read -r file; do
            echo -e "    ${DIM}?${NC} ${DIM}${file}${NC}"
        done <<< "$untracked"
    fi

    # ── Section 2: Other branches ─────────
    repo_other_branches "$dir" "$expected_branch"
done

echo ""
echo -e "${BOLD}==========================================${NC}"
if $any_changes; then
    echo -e "  ${DIM}make status-git-diff   show full diff${NC}"
fi
