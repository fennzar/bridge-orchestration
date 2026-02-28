#!/bin/bash

# ===========================================
# Zephyr Bridge Stack - Status
# ===========================================
# Comprehensive status display that works in any state:
# stopped, partially running, or fully running.
#
# Combines live service checks with persisted state inspection.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

# ── Shared logging + env ──────────────────────

source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/env.sh"
load_env "$ORCH_DIR/.env" 2>/dev/null || true

ZEPHYR_CLI="${ZEPHYR_REPO_PATH:-$(dirname "$ORCH_DIR")/zephyr}/tools/zephyr-cli/cli"

# ── Docker Compose command ──────────────────

COMPOSE_BASE="$ORCH_DIR/docker/compose.base.yml"
COMPOSE_DEV="$ORCH_DIR/docker/compose.dev.yml"
DC_DEV="docker compose -p bridge --env-file $ORCH_DIR/.env -f $COMPOSE_BASE -f $COMPOSE_DEV -f $ORCH_DIR/docker/compose.blockscout.yml"

# ── Docker service definitions ──────────────
# Format: container_name:display_name:port

DOCKER_SERVICES=(
    "zephyr-redis:redis:6380"
    "zephyr-postgres:postgres:5432"
    "zephyr-anvil:anvil:8545"
    "zephyr-node1:zephyr-node1:47767"
    "zephyr-node2:zephyr-node2:47867"
    "zephyr-wallet-gov:wallet-gov:48769"
    "zephyr-wallet-miner:wallet-miner:48767"
    "zephyr-wallet-test:wallet-test:48768"
    "zephyr-wallet-bridge:wallet-bridge:48770"
    "zephyr-wallet-engine:wallet-engine:48771"
    "zephyr-wallet-cex:wallet-cex:48772"
    "zephyr-fake-oracle:fake-oracle:5555"
    "zephyr-fake-orderbook:fake-orderbook:5556"
    "zephyr-blockscout-proxy:blockscout:4000:optional"
)

# ── Overmind process definitions ────────────
# Format: name:port (- means no port)

OVERMIND_PROCESSES=(
    "bridge-web:7050"
    "bridge-api:7051"
    "bridge-watchers:-"
    "engine-web:7000"
    "engine-watchers:-"
    "dashboard:7100"
)

# Auto-detect which overmind socket is active (dev or prod)
# Prefer an active socket over the Makefile default.
if [ -S "$ORCH_DIR/.overmind-prod.sock" ] && overmind status -s "$ORCH_DIR/.overmind-prod.sock" &>/dev/null; then
    OVERMIND_SOCK="$ORCH_DIR/.overmind-prod.sock"
elif [ -S "$ORCH_DIR/.overmind-dev.sock" ] && overmind status -s "$ORCH_DIR/.overmind-dev.sock" &>/dev/null; then
    OVERMIND_SOCK="$ORCH_DIR/.overmind-dev.sock"
else
    OVERMIND_SOCK="${OVERMIND_SOCK:-$ORCH_DIR/.overmind-dev.sock}"
fi

# ===========================================
# Helper: check if Docker is available
# ===========================================

docker_available() {
    docker ps &>/dev/null 2>&1
}

# ===========================================
# Helper: count running Docker containers
# ===========================================

count_running_containers() {
    if ! docker_available; then
        echo 0
        return
    fi
    local count=0
    for svc in "${DOCKER_SERVICES[@]}"; do
        IFS=: read -r container _ _ flags <<< "$svc"
        # Skip optional services (e.g. Blockscout) for stage detection
        [ "${flags:-}" = "optional" ] && continue
        if docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${container}$"; then
            ((count++))
        fi
    done
    echo "$count"
}

# ===========================================
# Helper: check if Overmind is running
# ===========================================

overmind_running() {
    [ -S "$OVERMIND_SOCK" ] && overmind status -s "$OVERMIND_SOCK" &>/dev/null
}

# ===========================================
# Helper: read from Docker volume (works when stopped)
# ===========================================

read_volume_file() {
    local volume="$1"
    local filepath="$2"
    docker run --rm -v "${volume}:/mnt" alpine cat "/mnt/${filepath}" 2>/dev/null
}

# ===========================================
# Helper: human-readable file size
# ===========================================

human_size() {
    local file="$1"
    if [ -f "$file" ]; then
        local bytes
        bytes=$(stat -c%s "$file" 2>/dev/null || stat -f%z "$file" 2>/dev/null || echo 0)
        if [ "$bytes" -ge 1048576 ]; then
            echo "$(( bytes / 1048576 ))M"
        elif [ "$bytes" -ge 1024 ]; then
            echo "$(( bytes / 1024 ))K"
        else
            echo "${bytes}B"
        fi
    else
        echo "?"
    fi
}

# ===========================================
# Section 1: Pipeline Stage Detection
# ===========================================

detect_stage() {
    local has_snapshots=false
    local has_addresses=false
    local has_docker=false
    local has_overmind=false

    # Check chain snapshots
    if ls "$ORCH_DIR"/snapshots/chain/*.tar.gz &>/dev/null; then
        has_snapshots=true
    fi

    # Check addresses.json (contracts deployed)
    if [ -f "$ORCH_DIR/config/addresses.json" ]; then
        has_addresses=true
    fi

    # Check Docker containers
    if docker_available; then
        local running
        running=$(count_running_containers)
        if [ "$running" -gt 0 ]; then
            has_docker=true
        fi
    fi

    # Check Overmind
    if overmind_running; then
        has_overmind=true
    fi

    # Determine stage
    if [ "$has_overmind" = true ]; then
        STAGE="RUNNING"
        STAGE_DESC="all services active"
        STAGE_COLOR="$GREEN"
        STAGE_NEXT=""
    elif [ "$has_docker" = true ]; then
        STAGE="INFRA-ONLY"
        STAGE_DESC="Docker running, apps stopped"
        STAGE_COLOR="$YELLOW"
        STAGE_NEXT="make dev-apps"
    elif [ "$has_addresses" = true ]; then
        STAGE="READY"
        STAGE_DESC="post-setup, stopped"
        STAGE_COLOR="$BLUE"
        STAGE_NEXT="make dev"
    elif [ "$has_snapshots" = true ]; then
        STAGE="INITIALIZED"
        STAGE_DESC="post-init, stopped"
        STAGE_COLOR="$YELLOW"
        STAGE_NEXT="make dev-setup"
    else
        STAGE="NOTHING"
        STAGE_DESC="no data"
        STAGE_COLOR="$RED"
        STAGE_NEXT="make dev-init"
    fi
}

print_stage() {
    echo -e "${BOLD}==========================================${NC}"
    echo -e "${BOLD}  Zephyr Bridge Stack — Status${NC}"
    echo -e "${BOLD}==========================================${NC}"
    echo ""
    echo -e "  Stage: ${STAGE_COLOR}${BOLD}${STAGE}${NC} ${DIM}(${STAGE_DESC})${NC}"
    if [ -n "$STAGE_NEXT" ]; then
        echo -e "  Next:  ${CYAN}${STAGE_NEXT}${NC}"
    fi
    echo ""
}

# ===========================================
# Section 2: Persisted State
# ===========================================

print_persisted_state() {
    echo -e "${CYAN}━━━ Persisted State ━━━${NC}"

    # Checkpoint height
    local checkpoint_height
    if docker_available; then
        checkpoint_height=$(read_volume_file "zephyr-checkpoint" "height" 2>/dev/null)
    fi
    if [ -n "${checkpoint_height:-}" ]; then
        echo -e "  Checkpoint:      height ${BOLD}${checkpoint_height}${NC}"
    else
        echo -e "  Checkpoint:      ${DIM}none${NC}"
    fi

    # Chain snapshots
    local snap_dir="$ORCH_DIR/snapshots/chain"
    if ls "$snap_dir"/*.tar.gz &>/dev/null 2>&1; then
        local snap_list=""
        for f in "$snap_dir"/*.tar.gz; do
            local name
            name=$(basename "$f" .tar.gz)
            local size
            size=$(human_size "$f")
            if [ -n "$snap_list" ]; then
                snap_list="$snap_list, $name ($size)"
            else
                snap_list="$name ($size)"
            fi
        done
        echo -e "  Chain snapshots: ${snap_list}"
    else
        echo -e "  Chain snapshots: ${DIM}none${NC}"
    fi

    # Anvil snapshots
    local anvil_dir="$ORCH_DIR/snapshots/anvil"
    if ls "$anvil_dir"/*.json "$anvil_dir"/*.hex &>/dev/null 2>&1; then
        local anvil_list=""
        for f in "$anvil_dir"/*.json "$anvil_dir"/*.hex; do
            [ -f "$f" ] || continue
            local name
            name=$(basename "$f")
            local size
            size=$(human_size "$f")
            if [ -n "$anvil_list" ]; then
                anvil_list="$anvil_list, $name ($size)"
            else
                anvil_list="$name ($size)"
            fi
        done
        echo -e "  Anvil snapshots: ${anvil_list}"
    else
        echo -e "  Anvil snapshots: ${DIM}none${NC}"
    fi

    # Contracts from addresses.json
    local addr_file="$ORCH_DIR/config/addresses.json"
    if [ -f "$addr_file" ]; then
        local token_count pool_count token_names pool_names
        token_count=$(jq '.tokens | length' "$addr_file" 2>/dev/null || echo 0)
        pool_count=$(jq '.pools | length' "$addr_file" 2>/dev/null || echo 0)
        token_names=$(jq -r '.tokens | keys | join(", ")' "$addr_file" 2>/dev/null || echo "?")
        pool_names=$(jq -r '.pools | keys | join(", ")' "$addr_file" 2>/dev/null || echo "?")
        echo -e "  Contracts:       ${BOLD}${token_count}${NC} tokens (${token_names}), ${BOLD}${pool_count}${NC} pools"
        echo -e "                   ${DIM}${pool_names}${NC}"
    else
        echo -e "  Contracts:       ${DIM}none (no addresses.json)${NC}"
    fi

    # Wallets from Docker volume
    if docker_available; then
        local wallet_files
        wallet_files=$(docker run --rm -v "zephyr-wallets:/w" alpine ls /w/ 2>/dev/null | grep '\.keys$' | sed 's/\.keys$//' | tr '\n' ',' | sed 's/,$//' | sed 's/,/, /g')
        if [ -n "${wallet_files:-}" ]; then
            echo -e "  Wallets:         ${wallet_files}"
        else
            echo -e "  Wallets:         ${DIM}none${NC}"
        fi
    else
        echo -e "  Wallets:         ${DIM}(Docker unavailable)${NC}"
    fi

    echo ""
}

# ===========================================
# Section 3: Docker Services
# ===========================================

print_docker_services() {
    echo -e "${CYAN}━━━ Docker Services ━━━${NC}"

    if ! docker_available; then
        fail "Docker: cannot connect"
        for svc in "${DOCKER_SERVICES[@]}"; do
            IFS=: read -r _ display port _ <<< "$svc"
            dim "$(printf '%-18s' "$display") unavailable"
        done
        echo ""
        return
    fi

    for svc in "${DOCKER_SERVICES[@]}"; do
        IFS=: read -r container display port flags <<< "$svc"

        if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${container}$"; then
            if [ "${flags:-}" = "optional" ]; then
                dim "$(printf '%-18s' "$display") not running"
            else
                fail "$(printf '%-18s' "$display") stopped"
            fi
            continue
        fi

        # Check health status
        local health
        health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container" 2>/dev/null || echo "unknown")

        case "$health" in
            healthy)
                ok "$(printf '%-18s' "$display") healthy (port $port)"
                ;;
            starting)
                warn "$(printf '%-18s' "$display") starting (port $port)"
                ;;
            none)
                ok "$(printf '%-18s' "$display") running (port $port)"
                ;;
            *)
                warn "$(printf '%-18s' "$display") unhealthy (port $port)"
                ;;
        esac
    done

    echo ""
}

# ===========================================
# Section 3b: Docker Log Warnings
# ===========================================

print_docker_warnings() {
    if ! docker_available; then
        return
    fi

    local found_issues=false
    local warnings=""

    for svc in "${DOCKER_SERVICES[@]}"; do
        IFS=: read -r container display port flags <<< "$svc"

        # Skip containers that aren't running
        if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${container}$"; then
            continue
        fi

        # Sample last 50 lines and count error patterns
        local log_sample
        log_sample=$(docker logs --tail 50 "$container" 2>&1) || continue

        local error_count=0
        local sample_line=""
        while IFS= read -r line; do
            if echo "$line" | grep -qiE '(error|fatal|panic|ENOSPC|BlockOutOfRange|TransportError|no space left|OOM)'; then
                error_count=$((error_count + 1))
                if [ -z "$sample_line" ]; then
                    sample_line="${line:0:100}"
                fi
            fi
        done <<< "$log_sample"

        if [ "$error_count" -gt 10 ]; then
            if [ "$found_issues" = false ]; then
                found_issues=true
                warnings+="$(echo -e "${CYAN}━━━ Docker Log Warnings ━━━${NC}")\n"
            fi
            warnings+="$(warn "$(printf '%-18s' "$display") $error_count errors in last 50 lines")\n"
            warnings+="$(dim "  ${sample_line}")\n"
        fi
    done

    if [ "$found_issues" = true ]; then
        echo -e "$warnings"
    fi
}

# ===========================================
# Section 4: Overmind Processes
# ===========================================

print_overmind_processes() {
    echo -e "${CYAN}━━━ App Processes (Overmind) ━━━${NC}"

    if ! overmind_running; then
        for proc in "${OVERMIND_PROCESSES[@]}"; do
            IFS=: read -r name port <<< "$proc"
            if [ "$port" = "-" ]; then
                dim "$(printf '%-18s' "$name") not running"
            else
                dim "$(printf '%-18s' "$name") not running (port $port)"
            fi
        done
        echo ""
        return
    fi

    # Parse overmind status output
    local overmind_output
    overmind_output=$(overmind status -s "$OVERMIND_SOCK" 2>&1)

    for proc in "${OVERMIND_PROCESSES[@]}"; do
        IFS=: read -r name port <<< "$proc"

        # Match the process line from overmind status
        local proc_line
        proc_line=$(echo "$overmind_output" | grep "^${name}" || true)

        if [ -z "$proc_line" ]; then
            if [ "$port" = "-" ]; then
                dim "$(printf '%-18s' "$name") not running"
            else
                dim "$(printf '%-18s' "$name") not running (port $port)"
            fi
            continue
        fi

        local pid status
        pid=$(echo "$proc_line" | awk '{print $2}')
        status=$(echo "$proc_line" | awk '{print $3}')

        if [ "$status" = "running" ]; then
            if [ "$port" = "-" ]; then
                ok "$(printf '%-18s' "$name") running (pid $pid)"
            else
                ok "$(printf '%-18s' "$name") running (port $port, pid $pid)"
            fi
        else
            fail "$(printf '%-18s' "$name") $status"
        fi
    done

    echo ""
}

# ===========================================
# Section 5: Chain Vitals (only when running)
# ===========================================

print_chain_vitals() {
    # Only show if Docker infra is running
    if [ "$STAGE" != "RUNNING" ] && [ "$STAGE" != "INFRA-ONLY" ]; then
        return
    fi

    echo -e "${CYAN}━━━ Chain Vitals ━━━${NC}"

    # Zephyr node heights (via CLI)
    local node1_height node2_height cli_output
    cli_output=$("$ZEPHYR_CLI" height --all 2>/dev/null) || true
    node1_height=$(echo "$cli_output" | grep '^node1:' | awk '{print $2}') || true
    node2_height=$(echo "$cli_output" | grep '^node2:' | awk '{print $2}') || true

    if [ -n "${node1_height:-}" ] || [ -n "${node2_height:-}" ]; then
        local zephyr_str="  Zephyr:  "
        if [ -n "${node1_height:-}" ]; then
            zephyr_str+="height ${BOLD}${node1_height}${NC} (node1)"
        else
            zephyr_str+="${DIM}node1 not responding${NC}"
        fi
        if [ -n "${node2_height:-}" ]; then
            zephyr_str+=", height ${BOLD}${node2_height}${NC} (node2)"
        else
            zephyr_str+=", ${DIM}node2 not responding${NC}"
        fi
        echo -e "$zephyr_str"
    else
        echo -e "  Zephyr:  ${DIM}not responding${NC}"
    fi

    # Mining status
    local mining_response
    mining_response=$(curl -sf -m 2 http://127.0.0.1:47767/mining_status 2>/dev/null) || true
    if [ -n "${mining_response:-}" ]; then
        local mining_active mining_threads
        mining_active=$(echo "$mining_response" | jq -r '.active // false' 2>/dev/null)
        mining_threads=$(echo "$mining_response" | jq -r '.threads_count // 0' 2>/dev/null)
        if [ "$mining_active" = "true" ]; then
            echo -e "  Mining:  ${YELLOW}${BOLD}active${NC} (${mining_threads} threads)"
        else
            echo -e "  Mining:  ${DIM}stopped${NC}"
        fi
    fi

    # Anvil block number
    local anvil_block
    anvil_block=$(curl -sf -m 2 http://127.0.0.1:8545 -X POST \
        -H 'Content-Type: application/json' \
        -d '{"jsonrpc":"2.0","method":"eth_blockNumber","id":1}' 2>/dev/null | jq -r '.result // empty' 2>/dev/null) || true
    if [ -n "${anvil_block:-}" ]; then
        # Convert hex to decimal
        local anvil_dec
        anvil_dec=$(printf '%d' "$anvil_block" 2>/dev/null || echo "$anvil_block")
        echo -e "  Anvil:   block ${BOLD}${anvil_dec}${NC}"
    else
        echo -e "  Anvil:   ${DIM}not responding${NC}"
    fi

    # Oracle price
    local oracle_response
    oracle_response=$(curl -sf -m 2 http://127.0.0.1:5555/status 2>/dev/null) || true
    if [ -n "${oracle_response:-}" ]; then
        local spot
        spot=$(echo "$oracle_response" | jq -r '.spot // empty' 2>/dev/null)
        if [ -n "${spot:-}" ]; then
            # spot is in piconero (1e12), convert to dollars
            local price
            price=$(echo "scale=2; $spot / 1000000000000" | bc 2>/dev/null || echo "?")
            echo -e "  Oracle:  \$${BOLD}${price}${NC} (spot)"
        else
            echo -e "  Oracle:  ${DIM}responding but no price${NC}"
        fi
    else
        echo -e "  Oracle:  ${DIM}not responding${NC}"
    fi

    echo ""
}

# ===========================================
# Main
# ===========================================

detect_stage
print_stage
print_persisted_state
print_docker_services
print_docker_warnings
print_overmind_processes
print_chain_vitals

echo -e "${BOLD}==========================================${NC}"
