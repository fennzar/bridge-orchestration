#!/bin/bash
set -euo pipefail

# ===========================================
# Zephyr Bridge Stack - Prerequisite Verification
# ===========================================
# Validates the development environment before running other scripts.
# Checks: software, paths, repos, and logs their status.
#
# Usage:
#   ./scripts/verify.sh           # Full verification
#   ./scripts/verify.sh --quiet   # Only show errors/warnings
#   ./scripts/verify.sh --json    # Output as JSON (for CI)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Counters
ERRORS=0
WARNINGS=0

# Options
QUIET=false
JSON_OUTPUT=false

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -q|--quiet)
            QUIET=true
            shift
            ;;
        --json)
            JSON_OUTPUT=true
            QUIET=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  -q, --quiet   Only show errors and warnings"
            echo "  --json        Output results as JSON"
            echo "  -h, --help    Show this help"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Logging functions
log_header() {
    if [ "$QUIET" = false ]; then
        echo ""
        echo -e "${BOLD}${CYAN}━━━ $1 ━━━${NC}"
    fi
}

log_info() {
    if [ "$QUIET" = false ]; then
        echo -e "${BLUE}[INFO]${NC} $1"
    fi
}

log_ok() {
    if [ "$QUIET" = false ]; then
        echo -e "${GREEN}  ✓${NC} $1"
    fi
}

log_warn() {
    echo -e "${YELLOW}  ⚠${NC} $1"
    WARNINGS=$((WARNINGS + 1))
}

log_error() {
    echo -e "${RED}  ✗${NC} $1"
    ERRORS=$((ERRORS + 1))
}

log_detail() {
    if [ "$QUIET" = false ]; then
        echo -e "    ${1}"
    fi
}

# JSON output accumulator
JSON_RESULTS=()
json_add() {
    local category=$1
    local item=$2
    local status=$3
    local details=${4:-""}
    JSON_RESULTS+=("{\"category\":\"$category\",\"item\":\"$item\",\"status\":\"$status\",\"details\":\"$details\"}")
}

# ===========================================
# Check: .env file exists and is loaded
# ===========================================
check_env_file() {
    log_header "Environment Configuration"

    if [ ! -f "$ORCH_DIR/.env" ]; then
        log_error ".env file not found"
        log_detail "Run: cp .env.example .env"
        json_add "config" ".env" "error" "File not found"
        return 1
    fi

    log_ok ".env file exists"
    json_add "config" ".env" "ok" ""

    # Load environment using shared loader
    source "$SCRIPT_DIR/lib/env.sh"
    load_env "$ORCH_DIR/.env"

    # Validate required variables
    local required_vars=(
        "ROOT"
        "BRIDGE_ENV"
        "BRIDGE_REPO_PATH"
        "ENGINE_REPO_PATH"
        "FOUNDRY_REPO_PATH"
    )

    for var in "${required_vars[@]}"; do
        if [ -z "${!var:-}" ]; then
            log_error "$var is not set in .env"
            json_add "config" "$var" "error" "Not set"
        else
            log_ok "$var = ${!var}"
            json_add "config" "$var" "ok" "${!var}"
        fi
    done
}

# ===========================================
# Check: Required software
# ===========================================
check_software() {
    log_header "Required Software"

    # Node.js
    if command -v node &> /dev/null; then
        local node_version=$(node -v)
        local node_major=$(echo "$node_version" | sed 's/v\([0-9]*\).*/\1/')
        if [ "$node_major" -ge 22 ]; then
            log_ok "Node.js $node_version"
            json_add "software" "node" "ok" "$node_version"
        else
            log_warn "Node.js $node_version (22+ recommended)"
            json_add "software" "node" "warning" "$node_version"
        fi
    else
        log_error "Node.js not found"
        log_detail "Install: nvm install 22"
        json_add "software" "node" "error" "Not found"
    fi

    # pnpm
    if command -v pnpm &> /dev/null; then
        local pnpm_version=$(pnpm -v)
        log_ok "pnpm $pnpm_version"
        json_add "software" "pnpm" "ok" "$pnpm_version"
    else
        log_error "pnpm not found"
        log_detail "Install: npm install -g pnpm"
        json_add "software" "pnpm" "error" "Not found"
    fi

    # Docker
    if command -v docker &> /dev/null; then
        local docker_version=$(docker --version | awk '{print $3}' | tr -d ',')
        log_ok "Docker $docker_version"
        json_add "software" "docker" "ok" "$docker_version"

        # Check docker daemon
        if docker ps &>/dev/null; then
            log_ok "Docker daemon accessible"
            json_add "software" "docker-daemon" "ok" ""
        else
            log_error "Cannot connect to Docker daemon"
            log_detail "Run: sudo usermod -aG docker \$USER && newgrp docker"
            json_add "software" "docker-daemon" "error" "Not accessible"
        fi
    else
        log_error "Docker not found"
        log_detail "Install: sudo apt install docker.io"
        json_add "software" "docker" "error" "Not found"
    fi

    # Docker Compose
    local compose_check=$(docker compose version 2>&1) || true
    if [[ "$compose_check" == *"Docker Compose"* ]]; then
        local compose_version=$(echo "$compose_check" | grep -oP 'v[\d.]+' | head -1 || echo "unknown")
        log_ok "Docker Compose $compose_version"
        json_add "software" "docker-compose" "ok" "$compose_version"
    elif [[ "$compose_check" == *"permission denied"* ]]; then
        log_warn "Docker Compose (requires docker access)"
        json_add "software" "docker-compose" "warning" "Requires docker access"
    else
        log_error "Docker Compose not found"
        json_add "software" "docker-compose" "error" "Not found"
    fi

    # Foundry tools
    local foundry_bin="${HOME}/.foundry/bin"
    for tool in forge anvil cast; do
        if command -v "$tool" &> /dev/null; then
            local version=$($tool --version 2>/dev/null | head -1 || echo "installed")
            log_ok "$tool: $version"
            json_add "software" "$tool" "ok" "$version"
        elif [ -x "$foundry_bin/$tool" ]; then
            local version=$("$foundry_bin/$tool" --version 2>/dev/null | head -1 || echo "installed")
            log_ok "$tool: $version (at $foundry_bin)"
            json_add "software" "$tool" "ok" "$version"
        else
            log_error "$tool not found"
            log_detail "Install: curl -L https://foundry.paradigm.xyz | bash && foundryup"
            json_add "software" "$tool" "error" "Not found"
        fi
    done

    # Overmind
    if command -v overmind &> /dev/null; then
        local overmind_version=$(overmind -v 2>/dev/null || echo "installed")
        log_ok "Overmind: $overmind_version"
        json_add "software" "overmind" "ok" "$overmind_version"
    else
        log_warn "Overmind not found (needed for process management)"
        log_detail "Install: https://github.com/DarthSim/overmind#installation"
        json_add "software" "overmind" "warning" "Not found"
    fi

    # tmux (required by overmind)
    if command -v tmux &> /dev/null; then
        local tmux_version=$(tmux -V 2>/dev/null || echo "installed")
        log_ok "tmux: $tmux_version"
        json_add "software" "tmux" "ok" "$tmux_version"
    else
        log_warn "tmux not found (required by Overmind)"
        log_detail "Install: sudo apt install tmux"
        json_add "software" "tmux" "warning" "Not found"
    fi

    # psql (optional)
    if command -v psql &> /dev/null; then
        local psql_version=$(psql --version | awk '{print $3}')
        log_ok "psql: $psql_version"
        json_add "software" "psql" "ok" "$psql_version"
    else
        log_info "psql not found (optional, for direct DB access)"
        json_add "software" "psql" "info" "Not found"
    fi

    # redis-cli (optional)
    if command -v redis-cli &> /dev/null; then
        local redis_version=$(redis-cli --version | awk '{print $2}')
        log_ok "redis-cli: $redis_version"
        json_add "software" "redis-cli" "ok" "$redis_version"
    else
        log_info "redis-cli not found (optional, Redis runs in Docker)"
        json_add "software" "redis-cli" "info" "Not found"
    fi
}

# ===========================================
# Check: Zephyr vendored artifacts
# ===========================================
check_zephyr() {
    log_header "Zephyr Artifacts"

    # Check if any artifacts are missing — if so, verify the Zephyr repo is available
    local has_missing=false
    if [ ! -f "$ORCH_DIR/docker/zephyr/bin/zephyrd" ] || \
       [ ! -f "$ORCH_DIR/docker/fake-oracle/server.js" ] || \
       [ ! -x "$ORCH_DIR/tools/fresh-devnet/run.sh" ] || \
       [ ! -x "$ORCH_DIR/tools/zephyr-cli/cli" ]; then
        has_missing=true
    fi

    # Zephyr repo availability (needed by sync-zephyr-artifacts.sh)
    local zephyr_repo="${ZEPHYR_REPO_PATH:-$(dirname "$ORCH_DIR")/zephyr}"
    if [ "$has_missing" = true ]; then
        if [ ! -d "$zephyr_repo/.git" ]; then
            log_error "Zephyr repo not found at $zephyr_repo"
            log_detail "Clone it or set ZEPHYR_REPO_PATH in .env"
            log_detail "sync-zephyr-artifacts.sh will not work without it"
            json_add "zephyr" "repo" "error" "Not found at $zephyr_repo"
        else
            local branch
            branch=$(git -C "$zephyr_repo" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
            if [ "$branch" = "fresh-devnet-bootstrap" ]; then
                log_ok "Zephyr repo: $zephyr_repo (branch: $branch)"
                json_add "zephyr" "repo" "ok" "$branch"
            else
                log_warn "Zephyr repo on branch '$branch' (expected: fresh-devnet-bootstrap)"
                log_detail "Run: cd $zephyr_repo && git checkout fresh-devnet-bootstrap"
                json_add "zephyr" "repo" "warning" "branch: $branch"
            fi
        fi
    fi

    # Vendored binaries (placed by sync-zephyr-artifacts.sh)
    local bin_dir="$ORCH_DIR/docker/zephyr/bin"
    for bin in zephyrd zephyr-wallet-rpc; do
        if [ -f "$bin_dir/$bin" ]; then
            local size=$(du -sh "$bin_dir/$bin" 2>/dev/null | awk '{print $1}')
            log_ok "$bin ($size)"
            json_add "zephyr" "$bin" "ok" "$size"
        else
            log_error "$bin not found at $bin_dir/"
            log_detail "Run: ./scripts/sync-zephyr-artifacts.sh"
            json_add "zephyr" "$bin" "error" "Not found"
        fi
    done

    # Vendored oracle files
    local oracle_dir="$ORCH_DIR/docker/fake-oracle"
    for f in server.js oracle_private.pem oracle_public.pem; do
        if [ -f "$oracle_dir/$f" ]; then
            log_ok "oracle: $f"
            json_add "zephyr" "oracle_$f" "ok" ""
        else
            log_error "oracle: $f not found"
            log_detail "Run: ./scripts/sync-zephyr-artifacts.sh"
            json_add "zephyr" "oracle_$f" "error" "Not found"
        fi
    done

    # Vendored tooling
    if [ -x "$ORCH_DIR/tools/fresh-devnet/run.sh" ]; then
        log_ok "tools/fresh-devnet/"
        json_add "zephyr" "fresh-devnet" "ok" ""
    else
        log_error "tools/fresh-devnet/ not found"
        log_detail "Run: ./scripts/sync-zephyr-artifacts.sh"
        json_add "zephyr" "fresh-devnet" "error" "Not found"
    fi

    if [ -x "$ORCH_DIR/tools/zephyr-cli/cli" ]; then
        log_ok "tools/zephyr-cli/"
        json_add "zephyr" "zephyr-cli" "ok" ""
    else
        log_error "tools/zephyr-cli/ not found"
        log_detail "Run: ./scripts/sync-zephyr-artifacts.sh"
        json_add "zephyr" "zephyr-cli" "error" "Not found"
    fi
}

# ===========================================
# Check: Repository status
# ===========================================
check_repos() {
    log_header "Repository Status"

    local repos=(
        "BRIDGE_REPO_PATH:zephyr-bridge"
        "ENGINE_REPO_PATH:zephyr-bridge-engine"
        "FOUNDRY_REPO_PATH:zephyr-eth-foundry"
    )

    for repo_info in "${repos[@]}"; do
        local var_name="${repo_info%%:*}"
        local repo_name="${repo_info##*:}"
        local repo_path="${!var_name:-}"

        if [ -z "$repo_path" ]; then
            log_error "$repo_name: $var_name not set"
            json_add "repos" "$repo_name" "error" "Path not set"
            continue
        fi

        if [ ! -d "$repo_path" ]; then
            log_error "$repo_name: directory not found at $repo_path"
            json_add "repos" "$repo_name" "error" "Not found"
            continue
        fi

        if [ ! -d "$repo_path/.git" ]; then
            log_warn "$repo_name: not a git repository"
            json_add "repos" "$repo_name" "warning" "Not a git repo"
            continue
        fi

        # Get git info
        cd "$repo_path"

        local branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
        local commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
        local commit_date=$(git log -1 --format="%cr" 2>/dev/null || echo "unknown")
        local remote=$(git remote get-url origin 2>/dev/null || echo "no remote")
        local status_summary=""

        # Check for uncommitted changes
        local changes=$(git status --porcelain 2>/dev/null | wc -l)
        if [ "$changes" -gt 0 ]; then
            status_summary=" [${changes} uncommitted changes]"
        fi

        # Check if behind remote
        git fetch --quiet 2>/dev/null || true
        local behind=$(git rev-list HEAD..@{upstream} --count 2>/dev/null || echo "0")
        local ahead=$(git rev-list @{upstream}..HEAD --count 2>/dev/null || echo "0")

        if [ "$behind" -gt 0 ] || [ "$ahead" -gt 0 ]; then
            status_summary="$status_summary [↓${behind} ↑${ahead}]"
        fi

        log_ok "$repo_name"
        log_detail "Branch: $branch @ $commit ($commit_date)$status_summary"
        log_detail "Remote: $remote"

        json_add "repos" "$repo_name" "ok" "branch:$branch,commit:$commit,changes:$changes"

        cd "$ORCH_DIR"
    done
}

# ===========================================
# Check: Docker services status
# ===========================================
check_docker_services() {
    log_header "Docker Services"

    if ! docker ps &>/dev/null; then
        log_error "Cannot connect to Docker daemon"
        log_detail "Docker services cannot be checked"
        return 0
    fi

    cd "$ORCH_DIR"

    # Check if compose files exist
    if [ ! -f "$ORCH_DIR/docker/compose.base.yml" ]; then
        log_error "docker/compose.base.yml not found"
        json_add "docker" "compose-file" "error" "Not found"
        return 1
    fi

    local services=("redis" "postgres" "anvil" "zephyr-node1" "zephyr-node2" "wallet-gov" "wallet-miner" "wallet-test" "fake-oracle")

    for service in "${services[@]}"; do
        local status=$(docker compose --env-file "$ORCH_DIR/.env" -f "$ORCH_DIR/docker/compose.base.yml" -f "$ORCH_DIR/docker/compose.dev.yml" ps --format json "$service" 2>/dev/null | jq -r '.State' 2>/dev/null || echo "not found")

        if [ "$status" = "running" ]; then
            log_ok "$service: running"
            json_add "docker" "$service" "ok" "running"
        elif [ "$status" = "not found" ] || [ -z "$status" ]; then
            log_info "$service: not started"
            log_detail "Run: docker compose up -d"
            json_add "docker" "$service" "info" "Not started"
        else
            log_warn "$service: $status"
            json_add "docker" "$service" "warning" "$status"
        fi
    done
}

# ===========================================
# Check: Contract addresses
# ===========================================
check_contracts() {
    log_header "Contract Configuration"

    local addresses_file="$ORCH_DIR/config/addresses.local.json"

    if [ -f "$addresses_file" ]; then
        local contract_count=$(jq 'keys | length' "$addresses_file" 2>/dev/null || echo "0")
        log_ok "Contract addresses file exists ($contract_count contracts)"
        json_add "contracts" "addresses_file" "ok" "$contract_count contracts"

        # List key contracts
        if [ "$QUIET" = false ]; then
            for key in wZEPH wZSD PoolManager UniversalRouter; do
                local addr=$(jq -r ".$key // empty" "$addresses_file" 2>/dev/null)
                if [ -n "$addr" ]; then
                    log_detail "$key: $addr"
                fi
            done
        fi
    else
        log_warn "Contract addresses not found at $addresses_file"
        log_detail "Run: ./scripts/deploy-contracts.sh"
        json_add "contracts" "addresses_file" "warning" "Not found"
    fi
}

# ===========================================
# Main
# ===========================================
main() {
    if [ "$JSON_OUTPUT" = false ]; then
        echo ""
        echo -e "${BOLD}==========================================${NC}"
        echo -e "${BOLD}  Zephyr Bridge Stack - Verification${NC}"
        echo -e "${BOLD}==========================================${NC}"
    fi

    check_env_file
    check_software
    check_zephyr
    check_repos
    check_docker_services
    check_contracts

    # Summary
    if [ "$JSON_OUTPUT" = true ]; then
        echo "{"
        echo "  \"errors\": $ERRORS,"
        echo "  \"warnings\": $WARNINGS,"
        echo "  \"results\": ["
        local first=true
        for result in "${JSON_RESULTS[@]}"; do
            if [ "$first" = true ]; then
                first=false
            else
                echo ","
            fi
            echo -n "    $result"
        done
        echo ""
        echo "  ]"
        echo "}"
    else
        echo ""
        echo -e "${BOLD}━━━ Summary ━━━${NC}"

        if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
            echo -e "${GREEN}✓ All checks passed${NC}"
        else
            if [ $ERRORS -gt 0 ]; then
                echo -e "${RED}✗ $ERRORS error(s)${NC}"
            fi
            if [ $WARNINGS -gt 0 ]; then
                echo -e "${YELLOW}⚠ $WARNINGS warning(s)${NC}"
            fi
        fi

        # Hint: check if vendored artifacts are missing
        if [ ! -f "$ORCH_DIR/docker/zephyr/bin/zephyrd" ] || \
           [ ! -f "$ORCH_DIR/docker/fake-oracle/server.js" ] || \
           [ ! -x "$ORCH_DIR/tools/fresh-devnet/run.sh" ] || \
           [ ! -x "$ORCH_DIR/tools/zephyr-cli/cli" ]; then
            echo ""
            echo -e "${BOLD}Hint:${NC} Some Zephyr artifacts are missing. Run:"
            echo -e "  ${CYAN}./scripts/sync-zephyr-artifacts.sh${NC}"
            echo "This copies binaries, oracle files, and CLI tools from the Zephyr repo."
        fi
        echo ""
    fi

    # Exit code
    if [ $ERRORS -gt 0 ]; then
        exit 1
    fi
    exit 0
}

main
