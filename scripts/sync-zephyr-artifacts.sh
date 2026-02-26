#!/bin/bash
set -euo pipefail

# ===========================================
# Sync Zephyr Artifacts into Bridge-Orchestration
# ===========================================
# Copies binaries, oracle files, and zephyr-cli
# from the Zephyr repo so this repo can function independently.
#
# Usage:
#   ./scripts/sync-zephyr-artifacts.sh            # Copy missing artifacts
#   ./scripts/sync-zephyr-artifacts.sh --force     # Overwrite all
#   ./scripts/sync-zephyr-artifacts.sh --no-build  # Skip binary build

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

# Load shared logging
source "$SCRIPT_DIR/lib/logging.sh"

# Override log_skip with script-specific version
log_skip() { echo -e "${YELLOW}[SKIP]${NC} $1 (already exists, use --force to overwrite)"; }

# ===========================================
# Parse flags
# ===========================================
FORCE=false
NO_BUILD=false

for arg in "$@"; do
    case "$arg" in
        --force)   FORCE=true ;;
        --no-build) NO_BUILD=true ;;
        -h|--help)
            echo "Usage: $0 [--force] [--no-build]"
            echo ""
            echo "Copies Zephyr artifacts into this repo:"
            echo "  - Devnet binaries (zephyrd, zephyr-wallet-rpc) → docker/zephyr/bin/"
            echo "  - Fake oracle files → docker/fake-oracle/"
            echo "  - Zephyr CLI → tools/zephyr-cli/"
            echo "  - Python RPC framework → utils/python-rpc/"
            echo ""
            echo "Options:"
            echo "  --force     Overwrite existing files"
            echo "  --no-build  Skip building binaries if not found"
            echo "  -h, --help  Show this help"
            exit 0
            ;;
        *)
            log_error "Unknown flag: $arg"
            echo "Run $0 --help for usage"
            exit 1
            ;;
    esac
done

# ===========================================
# Locate Zephyr repo
# ===========================================
source "$SCRIPT_DIR/lib/env.sh"
load_env "$ORCH_DIR/.env" 2>/dev/null || true

ZEPHYR_REPO="${ZEPHYR_REPO_PATH:-$(dirname "$ORCH_DIR")/zephyr}"

if [[ ! -d "$ZEPHYR_REPO/.git" ]]; then
    log_error "Zephyr repo not found at: $ZEPHYR_REPO"
    echo "  Set ZEPHYR_REPO_PATH in .env or clone zephyr as a sibling directory."
    exit 1
fi

echo "==========================================="
echo "  Sync Zephyr Artifacts"
echo "==========================================="
echo ""
echo "Source: $ZEPHYR_REPO"
echo "Dest:   $ORCH_DIR"
echo ""

COPIED=0
SKIPPED=0

# Helper: copy a single file
copy_file() {
    local src="$1" dest="$2" label="$3"
    if [[ ! -f "$src" ]]; then
        log_warn "$label: source not found at $src"
        return 1
    fi
    if [[ -f "$dest" ]] && [[ "$FORCE" != "true" ]]; then
        log_skip "$label"
        ((SKIPPED++)) || true
        return 0
    fi
    mkdir -p "$(dirname "$dest")"
    cp "$src" "$dest"
    log_success "$label"
    ((COPIED++)) || true
}

# Helper: copy a directory (rsync-like)
copy_dir() {
    local src="$1" dest="$2" label="$3"
    if [[ ! -d "$src" ]]; then
        log_warn "$label: source directory not found at $src"
        return 1
    fi
    if [[ -d "$dest" ]] && [[ "$FORCE" != "true" ]]; then
        log_skip "$label"
        ((SKIPPED++)) || true
        return 0
    fi
    mkdir -p "$dest"
    rsync -a --exclude='__pycache__' "$src/" "$dest/"
    log_success "$label"
    ((COPIED++)) || true
}

# ===========================================
# 1. Devnet binaries
# ===========================================
log_info "Binaries..."

BIN_SRC="$ZEPHYR_REPO/build/devnet/bin"

if [[ ! -f "$BIN_SRC/zephyrd" ]] && [[ "$NO_BUILD" != "true" ]]; then
    log_info "Binaries not built yet, building (this may take a while)..."
    if [[ -x "$ZEPHYR_REPO/tools/fresh-devnet/run.sh" ]]; then
        (cd "$ZEPHYR_REPO" && tools/fresh-devnet/run.sh build)
    else
        log_error "Cannot build: tools/fresh-devnet/run.sh not found in Zephyr repo"
        exit 1
    fi
fi

copy_file "$BIN_SRC/zephyrd" "$ORCH_DIR/docker/zephyr/bin/zephyrd" "zephyrd"
copy_file "$BIN_SRC/zephyr-wallet-rpc" "$ORCH_DIR/docker/zephyr/bin/zephyr-wallet-rpc" "zephyr-wallet-rpc"

# Mirror mode binaries (optional — only if built with DEVNET_MIRROR_SUPPLY)
MIRROR_BIN_SRC="$ZEPHYR_REPO/build/devnet-mirror/bin"
if [[ -f "$MIRROR_BIN_SRC/zephyrd" ]] && [[ -f "$MIRROR_BIN_SRC/zephyr-wallet-rpc" ]]; then
    log_info "Mirror binaries..."
    copy_file "$MIRROR_BIN_SRC/zephyrd" "$ORCH_DIR/docker/zephyr/bin-mirror/zephyrd" "zephyrd (mirror)"
    copy_file "$MIRROR_BIN_SRC/zephyr-wallet-rpc" "$ORCH_DIR/docker/zephyr/bin-mirror/zephyr-wallet-rpc" "zephyr-wallet-rpc (mirror)"
fi

# ===========================================
# 2. Fake oracle files
# ===========================================
log_info "Fake oracle..."

ORACLE_SRC="$ZEPHYR_REPO/tools/fake-oracle"
copy_file "$ORACLE_SRC/server.js" "$ORCH_DIR/docker/fake-oracle/server.js" "server.js"
copy_file "$ORACLE_SRC/oracle_private.pem" "$ORCH_DIR/docker/fake-oracle/oracle_private.pem" "oracle_private.pem"
copy_file "$ORACLE_SRC/oracle_public.pem" "$ORCH_DIR/docker/fake-oracle/oracle_public.pem" "oracle_public.pem"

# ===========================================
# 3. Docker infrastructure (Dockerfiles, entrypoints, compose)
# ===========================================
log_info "Docker infrastructure..."

copy_dir "$ZEPHYR_REPO/docker/zephyr" "$ORCH_DIR/docker/zephyr" "docker/zephyr/"
copy_dir "$ZEPHYR_REPO/docker/devnet-init" "$ORCH_DIR/docker/devnet-init" "docker/devnet-init/"

# ===========================================
# 4. Zephyr CLI + python-rpc dependency
# ===========================================
log_info "Zephyr CLI..."

copy_dir "$ZEPHYR_REPO/tools/zephyr-cli" "$ORCH_DIR/tools/zephyr-cli" "tools/zephyr-cli/"
copy_dir "$ZEPHYR_REPO/utils/python-rpc" "$ORCH_DIR/utils/python-rpc" "utils/python-rpc/"

# ===========================================
# Summary
# ===========================================
echo ""
echo "==========================================="
echo -e "${GREEN}Sync complete${NC}: $COPIED copied, $SKIPPED skipped"
echo "==========================================="
echo ""
if [[ $SKIPPED -gt 0 ]]; then
    echo "Use --force to overwrite existing files."
    echo ""
fi
