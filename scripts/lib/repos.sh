#!/bin/bash
# ===========================================
# Shared Repository Status & Update Functions
# ===========================================
# Used by setup.sh, status.sh, and pre-start checks.
#
# Requires: lib/logging.sh sourced, PARENT set.

# Pad string to width (used for aligned output)
if ! declare -f pad &>/dev/null; then
    pad() { printf "%-${2:-20}s" "$1"; }
fi

# All repos in the stack
# Format: dir|url|clone_flags|expected_branch
REPOS=(
    "bridge-orchestration|git@github.com:fennzar/bridge-orchestration.git||main"
    "zephyr-eth-foundry|git@github.com:fennzar/zephyr-uniswap-v4-foundry.git|--recursive|main"
    "zephyr-bridge|git@github.com:fennzar/zephyr-bridge.git||master"
    "zephyr-bridge-engine|git@github.com:fennzar/zephyr-bridge-engine.git||master"
    "zephyr|git@github.com:fennzar/zephyr.git|--recursive|fresh-devnet-bootstrap"
)

ZEPHYR_DEVNET_BRANCH="fresh-devnet-bootstrap"

# Show commits between two SHAs with a prefix marker.
# Usage: show_commits <repo_path> <from_sha> <to_sha> <marker> [max]
# marker: "+" for incoming, "*" for unpushed
_show_commits() {
    local repo_path="$1" from="$2" to="$3" marker="$4" max="${5:-5}"
    local count; count=$(git -C "$repo_path" rev-list --count "$from".."$to" 2>/dev/null || echo 0)
    [ "$count" -eq 0 ] && return

    local first=true
    while IFS= read -r line; do
        local sha="${line%% *}"
        local msg="${line#* }"
        if $first; then
            first=false
            # First commit = HEAD of that range
            if [ "$marker" = "+" ]; then
                echo -e "      ${GREEN}${marker}${NC} ${DIM}${line}${NC}  ${DIM}← origin${NC}"
            else
                echo -e "      ${CYAN}${marker}${NC} ${DIM}${line}${NC}  ${DIM}← HEAD${NC}"
            fi
        else
            if [ "$marker" = "+" ]; then
                echo -e "      ${GREEN}${marker}${NC} ${DIM}${line}${NC}"
            else
                echo -e "      ${CYAN}${marker}${NC} ${DIM}${line}${NC}"
            fi
        fi
    done < <(git -C "$repo_path" log --oneline --no-decorate "$from".."$to" 2>/dev/null | head -"$max")

    if [ "$count" -gt "$max" ]; then
        echo -e "      ${DIM}  ... and $((count - max)) more${NC}"
    fi
}

# Print git status for a single repo (read-only, no modifications).
# Two icons per line:
#   [clean/dirty] [sync]  repo  branch sha  (details)
#   clean:  ✓ green    dirty: ✗ yellow
#   sync:   = dim      ahead: ↑ cyan     behind: ↓ yellow    diverged: ↕ red
repo_status() {
    local dir="$1"
    local repo_path="$PARENT/$dir"

    if [ ! -d "$repo_path/.git" ]; then
        if [ -d "$repo_path" ]; then
            echo -e "  ${YELLOW}✗${NC} ${DIM}-${NC} $(pad "$dir" 25)exists but not a git repo"
        else
            echo -e "  ${DIM}-${NC} ${DIM}-${NC} ${DIM}$(pad "$dir" 25)not cloned${NC}"
        fi
        return
    fi

    local branch; branch=$(git -C "$repo_path" branch --show-current 2>/dev/null)
    local short_local; short_local=$(git -C "$repo_path" rev-parse --short HEAD 2>/dev/null)

    if [ -z "$branch" ]; then
        echo -e "  ${DIM}-${NC} ${DIM}-${NC} ${DIM}$(pad "$dir" 25)${short_local} detached HEAD${NC}"
        return
    fi

    # ── Dirty check ──
    local dirty_icon="${GREEN}✓${NC}"
    local dirty_desc=""
    if ! git -C "$repo_path" diff --quiet 2>/dev/null || \
       ! git -C "$repo_path" diff --cached --quiet 2>/dev/null || \
       [ -n "$(git -C "$repo_path" ls-files --others --exclude-standard 2>/dev/null | head -1)" ]; then
        local changes; changes=$(git -C "$repo_path" status --short 2>/dev/null | wc -l)
        dirty_icon="${YELLOW}✗${NC}"
        dirty_desc="${changes} changed"
    fi

    # ── Sync check ──
    local sync_icon="${DIM}=${NC}"
    local sync_desc=""
    local upstream; upstream=$(git -C "$repo_path" rev-parse --abbrev-ref "@{upstream}" 2>/dev/null || echo "")
    local local_sha="" remote_sha="" merge_base=""
    local ahead=0 behind=0

    if [ -z "$upstream" ]; then
        sync_icon="${DIM}-${NC}"
        sync_desc="no upstream"
    else
        local_sha=$(git -C "$repo_path" rev-parse HEAD 2>/dev/null)
        remote_sha=$(git -C "$repo_path" rev-parse "$upstream" 2>/dev/null)

        if [ "$local_sha" = "$remote_sha" ]; then
            sync_icon="${DIM}=${NC}"
        else
            merge_base=$(git -C "$repo_path" merge-base "$local_sha" "$remote_sha" 2>/dev/null)

            if [ "$merge_base" = "$local_sha" ]; then
                behind=$(git -C "$repo_path" rev-list --count "$local_sha".."$remote_sha" 2>/dev/null || echo "?")
                sync_icon="${YELLOW}↓${NC}"
                sync_desc="${behind} behind"
            elif [ "$merge_base" = "$remote_sha" ]; then
                ahead=$(git -C "$repo_path" rev-list --count "$remote_sha".."$local_sha" 2>/dev/null || echo "?")
                sync_icon="${CYAN}↑${NC}"
                sync_desc="${ahead} ahead"
            else
                ahead=$(git -C "$repo_path" rev-list --count "$merge_base".."$local_sha" 2>/dev/null || echo "?")
                behind=$(git -C "$repo_path" rev-list --count "$merge_base".."$remote_sha" 2>/dev/null || echo "?")
                sync_icon="${RED}↕${NC}"
                sync_desc="${ahead} ahead, ${behind} behind"
            fi
        fi
    fi

    # ── Build description ──
    local parts=()
    [ -n "$dirty_desc" ] && parts+=("$dirty_desc")
    [ -n "$sync_desc" ] && parts+=("$sync_desc")
    local desc=""
    if [ ${#parts[@]} -gt 0 ]; then
        desc="  ($(IFS=', '; echo "${parts[*]}"))"
    fi

    echo -e "  ${dirty_icon} ${sync_icon} $(pad "$dir" 25)${branch} ${DIM}${short_local}${NC}${desc}"

    # ── Show commits when ahead/behind ──
    if [ "$ahead" -gt 0 ] && [ -n "$remote_sha" ]; then
        _show_commits "$repo_path" "$remote_sha" "$local_sha" "*"
    fi
    if [ "$behind" -gt 0 ] && [ -n "$local_sha" ]; then
        _show_commits "$repo_path" "$local_sha" "$remote_sha" "+"
    fi
}

# Print tracking context for current branch.
# Shows: expected branch warning, upstream remote sync.
# Usage: repo_tracking_info <dir> [expected_branch]
repo_tracking_info() {
    local dir="$1"
    local expected_branch="${2:-}"
    local repo_path="$PARENT/$dir"

    [ -d "$repo_path/.git" ] || return

    local branch; branch=$(git -C "$repo_path" branch --show-current 2>/dev/null)
    [ -z "$branch" ] && return

    # ── Expected branch warning ──
    if [ -n "$expected_branch" ] && [ "$branch" != "$expected_branch" ]; then
        echo -e "      ${YELLOW}⚠${NC} expected branch: ${BOLD}${expected_branch}${NC}"
    fi

    # ── Upstream remote sync (fork tracking) ──
    if git -C "$repo_path" remote 2>/dev/null | grep -q '^upstream$'; then
        local upstream_ref=""
        for candidate in upstream/master upstream/main; do
            if git -C "$repo_path" rev-parse --verify "$candidate" &>/dev/null; then
                upstream_ref="$candidate"
                break
            fi
        done

        if [ -n "$upstream_ref" ]; then
            local local_sha; local_sha=$(git -C "$repo_path" rev-parse HEAD 2>/dev/null)
            local upstream_sha; upstream_sha=$(git -C "$repo_path" rev-parse "$upstream_ref" 2>/dev/null)

            if [ "$local_sha" = "$upstream_sha" ]; then
                echo -e "      ${DIM}⇡ ${upstream_ref}: in sync${NC}"
            else
                local merge_base; merge_base=$(git -C "$repo_path" merge-base "$local_sha" "$upstream_sha" 2>/dev/null || echo "")
                if [ -z "$merge_base" ]; then
                    echo -e "      ${DIM}⇡ ${upstream_ref}: no common ancestor${NC}"
                elif [ "$merge_base" = "$local_sha" ]; then
                    local u_behind; u_behind=$(git -C "$repo_path" rev-list --count "$local_sha".."$upstream_sha" 2>/dev/null)
                    echo -e "      ${YELLOW}⇣${NC} ${upstream_ref}: ${YELLOW}${u_behind} behind${NC}"
                elif [ "$merge_base" = "$upstream_sha" ]; then
                    local u_ahead; u_ahead=$(git -C "$repo_path" rev-list --count "$upstream_sha".."$local_sha" 2>/dev/null)
                    echo -e "      ${CYAN}⇡${NC} ${upstream_ref}: ${u_ahead} ahead"
                else
                    local u_ahead; u_ahead=$(git -C "$repo_path" rev-list --count "$merge_base".."$local_sha" 2>/dev/null)
                    local u_behind; u_behind=$(git -C "$repo_path" rev-list --count "$merge_base".."$upstream_sha" 2>/dev/null)
                    echo -e "      ${RED}⇡⇣${NC} ${upstream_ref}: ${u_ahead} ahead, ${YELLOW}${u_behind} behind${NC}"
                fi
            fi
        fi
    fi
}

# Print detailed info for all branches except current.
# Usage: repo_other_branches <dir> [expected_branch]
repo_other_branches() {
    local dir="$1"
    local expected_branch="${2:-}"
    local repo_path="$PARENT/$dir"

    [ -d "$repo_path/.git" ] || return

    local branch; branch=$(git -C "$repo_path" branch --show-current 2>/dev/null)
    [ -z "$branch" ] && return

    local all_branches; all_branches=$(git -C "$repo_path" branch --format='%(refname:short)' 2>/dev/null)
    local branch_count; branch_count=$(echo "$all_branches" | wc -l)
    local other_count=$((branch_count - 1))

    [ "$other_count" -eq 0 ] && return

    # Default branch for comparisons
    local default_ref="${expected_branch:-$branch}"
    local default_sha; default_sha=$(git -C "$repo_path" rev-parse "$default_ref" 2>/dev/null || true)

    local TCOL=16  # tracking column visible width

    echo ""
    echo -e "      ${DIM}─ other branches ────────────────────── vs ${default_ref} ──${NC}"

    while IFS= read -r b; do
        [ "$b" = "$branch" ] && continue

        local b_sha; b_sha=$(git -C "$repo_path" rev-parse "$b" 2>/dev/null || true)
        [ -z "$b_sha" ] && continue

        # ── Tracking status (build colored + plain for padding) ──
        local track_color="" track_plain=""
        local up; up=$(git -C "$repo_path" rev-parse --abbrev-ref "${b}@{upstream}" 2>/dev/null || true)
        if [ -n "$up" ] && [ "$up" != "${b}@{upstream}" ]; then
            local remote_name="${up%%/*}"
            local remote_sha; remote_sha=$(git -C "$repo_path" rev-parse "$up" 2>/dev/null || true)
            if [ -z "$remote_sha" ] || [ "$b_sha" = "$remote_sha" ]; then
                track_plain="● ${remote_name} ="
                track_color="${GREEN}●${NC} ${DIM}${remote_name} =${NC}"
            else
                local t_ahead=0 t_behind=0
                t_ahead=$(git -C "$repo_path" rev-list --count "${remote_sha}..${b_sha}" 2>/dev/null || echo 0)
                t_behind=$(git -C "$repo_path" rev-list --count "${b_sha}..${remote_sha}" 2>/dev/null || echo 0)
                local tp="" tc=""
                if [ "$t_ahead" -gt 0 ]; then
                    tp="↑${t_ahead}"
                    tc="${CYAN}↑${t_ahead}${NC}"
                fi
                if [ "$t_behind" -gt 0 ]; then
                    [ -n "$tp" ] && tp="${tp} " && tc="${tc} "
                    tp="${tp}↓${t_behind}"
                    tc="${tc}${YELLOW}↓${t_behind}${NC}"
                fi
                track_plain="● ${remote_name} ${tp}"
                track_color="${GREEN}●${NC} ${remote_name} ${tc}"
            fi
        else
            track_plain="○ local"
            track_color="${DIM}○ local${NC}"
        fi

        # Pad tracking column to fixed visible width
        local tpad=$((TCOL - ${#track_plain}))
        [ "$tpad" -lt 1 ] && tpad=1
        local tspace; tspace=$(printf "%${tpad}s" "")

        # ── vs default branch ──
        local vs_str=""
        if [ "$b" = "$default_ref" ]; then
            vs_str="◆ ${BOLD}default${NC}"
        elif [ -n "$default_sha" ]; then
            local d_ahead=0 d_behind=0
            d_ahead=$(git -C "$repo_path" rev-list --count "${default_sha}..${b_sha}" 2>/dev/null || echo 0)
            d_behind=$(git -C "$repo_path" rev-list --count "${b_sha}..${default_sha}" 2>/dev/null || echo 0)

            if [ "$d_ahead" -eq 0 ]; then
                vs_str="${GREEN}✓ merged${NC}"
            elif [ "$d_behind" -eq 0 ]; then
                vs_str="${CYAN}+${d_ahead}${NC}"
            else
                vs_str="${CYAN}+${d_ahead}${NC} ${YELLOW}−${d_behind}${NC}"
            fi
        fi

        # ── Last commit age ──
        local age; age=$(git -C "$repo_path" log -1 --format='%cr' "$b" 2>/dev/null || true)
        age=$(echo "$age" | sed \
            -e 's/ seconds\? ago/s/' \
            -e 's/ minutes\? ago/m/' \
            -e 's/ hours\? ago/h/' \
            -e 's/ days\? ago/d/' \
            -e 's/ weeks\? ago/w/' \
            -e 's/ months\? ago/mo/' \
            -e 's/ years\? ago/y/')

        # ── Print line ──
        local padded; padded=$(printf "%-35s" "$b")
        echo -e "        ${padded} ${track_color}${tspace}${vs_str}  ${DIM}◷ ${age}${NC}"
    done <<< "$all_branches"
}

# Legacy wrapper — calls both parts. Used by callers that don't need the split.
repo_branch_info() {
    repo_tracking_info "$@"
    repo_other_branches "$@"
}

# Fetch all repos, print status, return count of repos that are behind.
# Usage: repos_fetch_status
repos_fetch_status() {
    local behind_count=0

    for entry in "${REPOS[@]}"; do
        IFS='|' read -r dir _ _ <<< "$entry"
        local repo_path="$PARENT/$dir"
        [ -d "$repo_path/.git" ] || continue
        git -C "$repo_path" fetch --quiet 2>/dev/null || true
    done

    for entry in "${REPOS[@]}"; do
        IFS='|' read -r dir _ _ <<< "$entry"
        repo_status "$dir"

        # Track if any repo is behind
        local repo_path="$PARENT/$dir"
        [ -d "$repo_path/.git" ] || continue
        local upstream; upstream=$(git -C "$repo_path" rev-parse --abbrev-ref "@{upstream}" 2>/dev/null || echo "")
        [ -z "$upstream" ] && continue
        local local_sha; local_sha=$(git -C "$repo_path" rev-parse HEAD 2>/dev/null)
        local remote_sha; remote_sha=$(git -C "$repo_path" rev-parse "$upstream" 2>/dev/null)
        if [ "$local_sha" != "$remote_sha" ]; then
            local merge_base; merge_base=$(git -C "$repo_path" merge-base "$local_sha" "$remote_sha" 2>/dev/null)
            [ "$merge_base" = "$local_sha" ] && ((behind_count++)) || true
        fi
    done

    return "$behind_count"
}
