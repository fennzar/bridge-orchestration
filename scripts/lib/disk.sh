#!/bin/bash
# Disk cleanup helpers — prune caches when disk space is low.
# Source: scripts/lib/logging.sh (for log_info, log_success)

maybe_cleanup_disk() {
    local free_gb
    free_gb=$(df -BG --output=avail . | tail -1 | tr -d ' G')
    if [ "$free_gb" -ge 10 ]; then return 0; fi

    log_info "Low disk space (${free_gb}GB free). Cleaning caches..."
    local before=$free_gb

    # 1. pnpm store prune (~2-3GB)
    if command -v pnpm &>/dev/null; then pnpm store prune 2>/dev/null; fi

    # 2. .next/cache (webpack cache, not needed for serving)
    find "${BRIDGE_REPO_PATH:-/dev/null}" "${ENGINE_REPO_PATH:-/dev/null}" \
        -path '*/.next/cache' -type d -exec rm -rf {} + 2>/dev/null || true

    # 3. Docker: dangling images + build cache
    docker image prune -f 2>/dev/null || true
    docker builder prune -f 2>/dev/null || true

    # 4. apt cache
    sudo apt-get clean 2>/dev/null || true

    local after
    after=$(df -BG --output=avail . | tail -1 | tr -d ' G')
    log_success "Freed $((after - before))GB (now ${after}GB free)"
}
