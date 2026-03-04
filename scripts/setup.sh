#!/usr/bin/env bash
set -euo pipefail

# ===========================================
# Bridge Orchestration — Interactive Setup
# ===========================================
# Checks prerequisites, offers auto-install, clones repos,
# installs dependencies, and prints next steps.
#
# Idempotent — safe to run repeatedly.
# Use --yes to auto-accept all prompts (CI/non-interactive).

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PARENT="$(cd "$ROOT/.." && pwd)"

source "$SCRIPT_DIR/lib/logging.sh"

# ── Auto-accept mode ────────────────────────────
AUTO_YES=false
for arg in "$@"; do
    case "$arg" in
        --yes|-y) AUTO_YES=true ;;
    esac
done

# ── Config ────────────────────────────────────

NODE_MIN=22
NVM_VERSION="0.40.1"
OVERMIND_VERSION="2.5.1"

# name|git_url|clone_flags
REPOS=(
    "zephyr-eth-foundry|git@github.com:fennzar/zephyr-uniswap-v4-foundry.git|--recursive"
    "zephyr-bridge|git@github.com:fennzar/zephyr-bridge.git|"
    "zephyr-bridge-engine|git@github.com:fennzar/zephyr-bridge-engine.git|"
    "zephyr|git@github.com:fennzar/zephyr.git|--recursive"
)

# ── OS Detection ──────────────────────────────

OS_ID="unknown"
OS_PRETTY="unknown"
IS_DEBIAN=false

detect_os() {
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS_ID="${ID:-unknown}"
        OS_PRETTY="${PRETTY_NAME:-$OS_ID}"
    elif [[ "$OSTYPE" == darwin* ]]; then
        OS_ID="macos"
        OS_PRETTY="macOS $(sw_vers -productVersion 2>/dev/null || echo '')"
    fi
    case "$OS_ID" in
        ubuntu|debian|pop|linuxmint|elementary) IS_DEBIAN=true ;;
    esac
}

# ── Utilities ─────────────────────────────────

# Compare semver: version_ge "22.11.0" "22" → true
version_ge() {
    local have="$1" need="$2"
    local have_major="${have%%.*}"
    local need_major="${need%%.*}"
    [ "$have_major" -ge "$need_major" ] 2>/dev/null
}

# Prompt y/N, returns 0 on yes
ask_yn() {
    local prompt="$1"
    if $AUTO_YES; then
        printf "\n  %s [y/N] y (auto)\n" "$prompt"
        return 0
    fi
    printf "\n  %s [y/N] " "$prompt"
    read -r ans </dev/tty
    [[ "$ans" =~ ^[yY]$ ]]
}

# Print a section divider
section() {
    echo ""
    echo -e "  ${DIM}── $1 ──${NC}"
    echo ""
}

# Right-pad a string to width
pad() {
    printf "%-${2:-20}s" "$1"
}

# Spinner characters (ASCII — works everywhere)
SPIN='|/-\'

# Run a command in the background with a spinner on the current line.
# Usage: spin_while "label" command [args...]
# Prints: | label   →   ✓ label   or   ✗ label
spin_while() {
    local label="$1"; shift
    local logfile; logfile=$(mktemp)

    "$@" >"$logfile" 2>&1 &
    local pid=$!
    local i=0

    while kill -0 "$pid" 2>/dev/null; do
        local s="${SPIN:$((i % ${#SPIN})):1}"
        printf "\r  ${YELLOW}%s${NC} %s" "$s" "$label"
        ((i++)) || true
        sleep 0.1
    done

    local rc=0
    wait "$pid" || rc=$?

    if [ "$rc" -eq 0 ]; then
        printf "\r  ${GREEN}✓${NC} %-60s\n" "$label"
    else
        printf "\r  ${RED}✗${NC} %-60s\n" "$label"
        cat "$logfile" | tail -5 | sed 's/^/      /'
    fi

    rm -f "$logfile"
    return "$rc"
}

# Run multiple tasks in parallel with docker-compose-style spinners.
# Populate TASK_NAMES, TASK_CMDS (bash -c strings), TASK_STATES before calling.
# TASK_STATES: "pending" = will run, "skip" = already done (shown dimmed)
# After return: TASK_RESULTS array has exit codes ("skip", "0", or non-zero)
declare -a TASK_NAMES=() TASK_CMDS=() TASK_STATES=() TASK_RESULTS=()

run_parallel_tasks() {
    local -a pids=() logs=()
    local tmpdir; tmpdir=$(mktemp -d)
    local num_lines=${#TASK_NAMES[@]}

    TASK_RESULTS=()

    # Print initial lines and start background jobs
    for i in "${!TASK_NAMES[@]}"; do
        if [ "${TASK_STATES[$i]}" = "skip" ]; then
            echo -e "  ${DIM}-${NC} ${DIM}$(pad "${TASK_NAMES[$i]}" 35)already installed${NC}"
            pids+=("")
            logs+=("")
            TASK_RESULTS+=("skip")
        else
            echo -e "  ${YELLOW}|${NC} $(pad "${TASK_NAMES[$i]}" 35)installing..."
            local logfile="$tmpdir/$i.log"
            bash -c "${TASK_CMDS[$i]}" >"$logfile" 2>&1 &
            pids+=($!)
            logs+=("$logfile")
            TASK_RESULTS+=("")
        fi
    done

    # Count pending tasks
    local total=0
    for i in "${!pids[@]}"; do [ -n "${pids[$i]}" ] && ((total++)) || true; done

    if [ "$total" -eq 0 ]; then
        rm -rf "$tmpdir"
        return 0
    fi

    # Animate until all done
    local done_count=0 spin_idx=0 failed=0
    while [ "$done_count" -lt "$total" ]; do
        ((spin_idx++)) || true
        local spin="${SPIN:$((spin_idx % ${#SPIN})):1}"

        # Check for completions
        for i in "${!pids[@]}"; do
            [ -z "${pids[$i]}" ] && continue
            [ -n "${TASK_RESULTS[$i]}" ] && continue
            if ! kill -0 "${pids[$i]}" 2>/dev/null; then
                local rc=0
                wait "${pids[$i]}" || rc=$?
                TASK_RESULTS[$i]="$rc"
                ((done_count++)) || true
                [ "$rc" -ne 0 ] && ((failed++)) || true
            fi
        done

        # Redraw all lines
        printf "\033[%dA" "$num_lines"
        for i in "${!TASK_NAMES[@]}"; do
            if [ "${TASK_STATES[$i]}" = "skip" ]; then
                printf "\r  ${DIM}-${NC} ${DIM}%-35s already installed${NC}%-10s\n" "${TASK_NAMES[$i]}" ""
            elif [ -n "${TASK_RESULTS[$i]}" ]; then
                if [ "${TASK_RESULTS[$i]}" -eq 0 ]; then
                    printf "\r  ${GREEN}✓${NC} %-35s done%-20s\n" "${TASK_NAMES[$i]}" ""
                else
                    printf "\r  ${RED}✗${NC} %-35s failed%-18s\n" "${TASK_NAMES[$i]}" ""
                fi
            else
                printf "\r  ${YELLOW}%s${NC} %-35s installing...%-11s\n" "$spin" "${TASK_NAMES[$i]}" ""
            fi
        done

        [ "$done_count" -lt "$total" ] && sleep 0.1
    done

    # Show error details
    if [ "$failed" -gt 0 ]; then
        echo ""
        for i in "${!TASK_NAMES[@]}"; do
            if [ -n "${TASK_RESULTS[$i]}" ] && [ "${TASK_RESULTS[$i]}" != "skip" ] && [ "${TASK_RESULTS[$i]}" -ne 0 ]; then
                echo -e "  ${RED}${TASK_NAMES[$i]}:${NC}"
                cat "${logs[$i]}" 2>/dev/null | tail -5 | sed 's/^/    /'
            fi
        done
    fi

    rm -rf "$tmpdir"
    return "$failed"
}

# ── Prereq Check Functions ────────────────────
# Each sets: _name, _version, _status (ok|missing|outdated), _note

declare -a PREREQ_NAMES=()
declare -a PREREQ_VERSIONS=()
declare -a PREREQ_STATUSES=()
declare -a PREREQ_NOTES=()

add_result() {
    PREREQ_NAMES+=("$1")
    PREREQ_VERSIONS+=("$2")
    PREREQ_STATUSES+=("$3")
    PREREQ_NOTES+=("${4:-}")
}

check_git() {
    if command -v git &>/dev/null; then
        local ver; ver=$(git --version 2>/dev/null | sed 's/git version //')
        add_result "git" "$ver" "ok"
    else
        add_result "git" "not found" "missing"
    fi
}

check_python3() {
    if command -v python3 &>/dev/null; then
        local ver; ver=$(python3 --version 2>/dev/null | sed 's/Python //')
        add_result "python3" "$ver" "ok"
    else
        add_result "python3" "not found" "missing"
    fi
}

check_node() {
    local ver="" source_note=""

    # Check nvm first
    if [ -s "${NVM_DIR:-$HOME/.nvm}/nvm.sh" ]; then
        # Source nvm to make it available
        export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
        # shellcheck disable=SC1091
        . "$NVM_DIR/nvm.sh" 2>/dev/null || true
    fi

    if command -v node &>/dev/null; then
        ver=$(node --version 2>/dev/null | sed 's/^v//')
        if [ -n "${NVM_DIR:-}" ] && command -v nvm &>/dev/null; then
            source_note="via nvm"
        fi
        if version_ge "$ver" "$NODE_MIN"; then
            local display="$ver"
            [ -n "$source_note" ] && display="$ver ($source_note)"
            add_result "node" "$display" "ok"
        else
            add_result "node" "$ver" "outdated" "need ${NODE_MIN}+"
        fi
    else
        add_result "node" "not found" "missing"
    fi
}

check_pnpm() {
    if command -v pnpm &>/dev/null; then
        local ver; ver=$(pnpm --version 2>/dev/null)
        add_result "pnpm" "$ver" "ok"
    else
        # Check if node is missing too
        if ! command -v node &>/dev/null; then
            add_result "pnpm" "not found" "missing" "needs node"
        else
            add_result "pnpm" "not found" "missing"
        fi
    fi
}

check_docker() {
    if command -v docker &>/dev/null; then
        local ver; ver=$(docker --version 2>/dev/null | sed 's/Docker version \([^,]*\).*/\1/')
        add_result "docker" "$ver" "ok"
    else
        add_result "docker" "not found" "missing"
    fi
}

check_docker_compose() {
    if command -v docker &>/dev/null && docker compose version &>/dev/null 2>&1; then
        local ver; ver=$(docker compose version --short 2>/dev/null)
        add_result "docker compose" "$ver" "ok"
    elif ! command -v docker &>/dev/null; then
        add_result "docker compose" "not found" "missing" "needs docker"
    else
        add_result "docker compose" "not found" "missing"
    fi
}

check_forge() {
    if command -v forge &>/dev/null; then
        local ver; ver=$(forge --version 2>/dev/null | head -1 | grep -oP '\d+\.\d+\.\d+' || echo "?")
        add_result "forge" "$ver" "ok"
    else
        add_result "forge" "not found" "missing"
    fi
}

check_overmind() {
    if command -v overmind &>/dev/null; then
        local ver; ver=$(overmind --version 2>/dev/null | head -1 | grep -oP '\d+\.\d+\.\d+' || echo "?")
        add_result "overmind" "$ver" "ok"
    else
        add_result "overmind" "not found" "missing"
    fi
}

check_tmux() {
    if command -v tmux &>/dev/null; then
        local ver; ver=$(tmux -V 2>/dev/null | sed 's/tmux //')
        add_result "tmux" "$ver" "ok"
    else
        add_result "tmux" "not found" "missing"
    fi
}

check_jq() {
    if command -v jq &>/dev/null; then
        local ver; ver=$(jq --version 2>/dev/null | sed 's/jq-//')
        add_result "jq" "$ver" "ok"
    else
        add_result "jq" "not found" "missing"
    fi
}

check_bc() {
    if command -v bc &>/dev/null; then
        local ver; ver=$(bc --version 2>/dev/null | head -1 | sed 's/.*bc //' | sed 's/ .*//')
        add_result "bc" "$ver" "ok"
    else
        add_result "bc" "not found" "missing"
    fi
}

check_curl() {
    if command -v curl &>/dev/null; then
        local ver; ver=$(curl --version 2>/dev/null | head -1 | sed 's/curl //' | sed 's/ .*//')
        add_result "curl" "$ver" "ok"
    else
        add_result "curl" "not found" "missing"
    fi
}


# ── Install Functions ─────────────────────────

install_apt_batch() {
    local -a pkgs=("$@")
    local pkg_list="${pkgs[*]}"

    section "Missing apt packages: $pkg_list"
    echo -e "    sudo apt install -y $pkg_list"

    if ! $IS_DEBIAN; then
        echo ""
        echo -e "  ${DIM}Not a Debian/Ubuntu system — install manually and re-run.${NC}"
        return 1
    fi

    if ask_yn "Install now? (or N to install manually and re-run)"; then
        echo ""
        # Install one at a time with spinner per package (apt locks prevent parallel)
        local all_ok=true
        for pkg in "${pkgs[@]}"; do
            spin_while "$pkg" sudo apt install -y "$pkg" || all_ok=false
        done
        echo ""
        if $all_ok; then
            log_success "All apt packages installed"
            return 0
        else
            log_error "Some packages failed to install"
            return 1
        fi
    else
        echo ""
        echo "  Run the command above, then: make setup"
        return 1
    fi
}

install_node() {
    section "Missing: node"
    echo "  Node.js ${NODE_MIN}+ is required. nvm (Node Version Manager) is recommended."
    echo ""
    echo "  Install command:"
    echo -e "    ${CYAN}curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v${NVM_VERSION}/install.sh | bash${NC}"
    echo -e "    ${CYAN}source ~/.bashrc${NC}"
    echo -e "    ${CYAN}nvm install ${NODE_MIN}${NC}"
    echo ""
    echo -e "  ${DIM}Docs: https://github.com/nvm-sh/nvm${NC}"

    if ask_yn "Install now? (or N to install manually and re-run)"; then
        echo ""
        # Install nvm
        spin_while "nvm ${NVM_VERSION}" bash -c "curl -o- 'https://raw.githubusercontent.com/nvm-sh/nvm/v${NVM_VERSION}/install.sh' 2>/dev/null | bash" || true
        export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
        # shellcheck disable=SC1091
        . "$NVM_DIR/nvm.sh" 2>/dev/null || true
        # Install node via nvm
        if command -v nvm &>/dev/null; then
            spin_while "node ${NODE_MIN}" nvm install "$NODE_MIN" || true
        fi
        local ver; ver=$(node --version 2>/dev/null | sed 's/^v//')
        if [ -n "$ver" ]; then
            echo ""
            log_success "node $ver installed via nvm"
            echo ""
            echo "  Run 'make setup' to continue."
            exit 0
        fi
        echo ""
        log_error "nvm/node install failed"
        echo ""
        echo "  Run 'make setup' to retry."
        exit 1
    else
        echo ""
        echo "  Run the commands above, then: make setup"
        exit 1
    fi
}

install_pnpm() {
    section "Missing: pnpm"
    echo "  pnpm is required for JS/TS dependency management."
    echo ""
    echo "  Install command:"
    echo -e "    ${CYAN}npm install -g pnpm${NC}"
    echo ""
    echo -e "  ${DIM}Docs: https://pnpm.io/installation${NC}"

    if ask_yn "Install now? (or N to install manually and re-run)"; then
        echo ""
        if spin_while "pnpm" npm install -g pnpm && command -v pnpm &>/dev/null; then
            local ver; ver=$(pnpm --version 2>/dev/null)
            echo ""
            log_success "pnpm $ver installed"
            echo ""
            echo "  Run 'make setup' to continue."
            exit 0
        else
            echo ""
            log_error "pnpm install failed"
            echo ""
            echo "  Run 'make setup' to retry."
            exit 1
        fi
    else
        echo ""
        echo "  Run the command above, then: make setup"
        exit 1
    fi
}

install_docker() {
    section "Missing: docker"
    echo "  Docker CE + Compose plugin is required."
    echo ""
    echo "  Install commands:"
    echo -e "    ${CYAN}curl -fsSL https://get.docker.com | sh${NC}"
    echo -e "    ${CYAN}sudo usermod -aG docker \$USER${NC}"
    echo ""
    echo -e "  ${DIM}Docs: https://docs.docker.com/engine/install/${NC}"

    if ask_yn "Install now? (or N to install manually and re-run)"; then
        echo ""
        if spin_while "Docker CE + Compose (this may take a minute)" bash -c "curl -fsSL https://get.docker.com | sh" && command -v docker &>/dev/null; then
            local ver; ver=$(docker --version 2>/dev/null | sed 's/Docker version \([^,]*\).*/\1/')
            echo ""
            log_success "Docker $ver installed"
            # Add current user to docker group
            if ! groups | grep -q docker; then
                sudo usermod -aG docker "$USER" 2>/dev/null || true
                echo ""
                echo -e "  ${YELLOW}NOTE:${NC} Added $USER to docker group."
                echo "  You may need to log out and back in (or run 'newgrp docker')"
                echo "  for group changes to take effect."
            fi
        else
            echo ""
            log_error "Docker install failed"
        fi
        echo ""
        echo "  Run 'make setup' to continue."
        exit 0
    else
        echo ""
        echo "  Run the commands above, then: make setup"
        exit 1
    fi
}

install_docker_compose() {
    section "Missing: docker compose"
    echo "  The Docker Compose plugin is required (docker already installed)."
    echo ""
    echo "  Install command:"
    echo -e "    ${CYAN}sudo apt install -y docker-compose-plugin${NC}"
    echo ""
    echo -e "  ${DIM}Docs: https://docs.docker.com/compose/install/${NC}"

    if $IS_DEBIAN; then
        if ask_yn "Install now? (or N to install manually and re-run)"; then
            echo ""
            if spin_while "docker-compose-plugin" sudo apt install -y docker-compose-plugin; then
                local ver; ver=$(docker compose version --short 2>/dev/null)
                echo ""
                log_success "docker compose $ver installed"
            else
                echo ""
                log_error "Install failed"
            fi
            echo ""
            echo "  Run 'make setup' to continue."
            exit 0
        fi
    fi
    echo ""
    echo "  Run the command above, then: make setup"
    exit 1
}

install_forge() {
    section "Missing: forge"
    echo "  Foundry (forge) is required for Solidity contract compilation."
    echo ""
    echo "  Install command:"
    echo -e "    ${CYAN}curl -L https://foundry.paradigm.xyz | bash${NC}"
    echo -e "    ${CYAN}source ~/.bashrc${NC}"
    echo -e "    ${CYAN}foundryup${NC}"
    echo ""
    echo -e "  ${DIM}Docs: https://book.getfoundry.sh${NC}"

    if ask_yn "Install now? (or N to install manually and re-run)"; then
        echo ""
        spin_while "foundryup" bash -c "curl -L https://foundry.paradigm.xyz 2>/dev/null | bash" || true
        export PATH="$HOME/.foundry/bin:$PATH"
        spin_while "foundryup (downloading toolchain)" foundryup || true
        if command -v forge &>/dev/null; then
            echo ""
            log_success "forge installed"
            echo ""
            echo "  Run 'make setup' to continue."
            exit 0
        fi
        echo ""
        log_error "foundry install failed"
        echo ""
        echo "  Run 'make setup' to retry."
        exit 1
    else
        echo ""
        echo "  Run the commands above, then: make setup"
        exit 1
    fi
}

install_overmind() {
    section "Missing: overmind"
    echo "  Overmind v${OVERMIND_VERSION} is required for process management."
    echo "  Requires tmux as a dependency."
    echo ""
    echo "  Install commands:"
    echo -e "    ${CYAN}sudo apt install -y tmux${NC}"
    echo -e "    ${CYAN}curl -fsSL -o /tmp/overmind.gz https://github.com/DarthSim/overmind/releases/download/v${OVERMIND_VERSION}/overmind-v${OVERMIND_VERSION}-linux-amd64.gz${NC}"
    echo -e "    ${CYAN}gunzip /tmp/overmind.gz${NC}"
    echo -e "    ${CYAN}chmod +x /tmp/overmind && sudo mv /tmp/overmind /usr/local/bin/overmind${NC}"
    echo ""
    echo -e "  ${DIM}Docs: https://github.com/DarthSim/overmind${NC}"

    if ask_yn "Install now? (or N to install manually and re-run)"; then
        echo ""
        # Ensure tmux is installed first
        if ! command -v tmux &>/dev/null && $IS_DEBIAN; then
            spin_while "tmux (dependency)" sudo apt install -y tmux || true
        fi
        local tmp; tmp=$(mktemp -d)
        if spin_while "overmind v${OVERMIND_VERSION}" bash -c "curl -fsSL -o '$tmp/overmind.gz' 'https://github.com/DarthSim/overmind/releases/download/v${OVERMIND_VERSION}/overmind-v${OVERMIND_VERSION}-linux-amd64.gz' && gunzip '$tmp/overmind.gz' && chmod +x '$tmp/overmind' && sudo mv '$tmp/overmind' /usr/local/bin/overmind"; then
            rm -rf "$tmp"
            echo ""
            log_success "overmind v${OVERMIND_VERSION} installed"
            echo ""
            echo "  Run 'make setup' to continue."
            exit 0
        else
            rm -rf "$tmp"
            echo ""
            log_error "overmind install failed"
            echo ""
            echo "  Run 'make setup' to retry."
            exit 1
        fi
    else
        echo ""
        echo "  Run the commands above, then: make setup"
        exit 1
    fi
}

# ── Phase 1: Header + Prereq Scan ────────────

print_header() {
    echo ""
    echo "=========================================="
    echo "  Bridge Orchestration — Setup"
    echo "=========================================="
    echo "  Parent: $PARENT"
    echo "  OS:     $OS_PRETTY"
    echo ""
}

phase_prereqs() {
    echo "Checking prerequisites..."
    echo ""

    check_git
    check_python3
    check_node
    check_pnpm
    check_docker
    check_docker_compose
    check_forge
    check_overmind
    check_tmux
    check_jq
    check_bc
    check_curl

    # Display matrix
    local missing_names=()
    for i in "${!PREREQ_NAMES[@]}"; do
        local name="${PREREQ_NAMES[$i]}"
        local ver="${PREREQ_VERSIONS[$i]}"
        local status="${PREREQ_STATUSES[$i]}"
        local note="${PREREQ_NOTES[$i]}"

        local display_ver="$ver"
        if [ -n "$note" ] && [ "$status" != "ok" ]; then
            display_ver="$ver ($note)"
        fi

        case "$status" in
            ok)       ok "$(pad "$name" 20)$display_ver" ;;
            missing)  fail "$(pad "$name" 20)$display_ver"; missing_names+=("$name") ;;
            outdated) fail "$(pad "$name" 20)$display_ver"; missing_names+=("$name") ;;
        esac
    done

    echo ""

    if [ ${#missing_names[@]} -eq 0 ]; then
        log_success "All prerequisites found"
        return 0
    fi

    local count=${#missing_names[@]}
    local list; list=$(IFS=', '; echo "${missing_names[*]}")
    log_error "$count missing: $list"

    # ── Phase 2: Interactive Fix ──

    # Tier 1: Batch apt packages
    local -a apt_missing=()
    for name in "${missing_names[@]}"; do
        case "$name" in
            git|python3|tmux|jq|bc|curl) apt_missing+=("$name") ;;
            # python3 apt package name differs
        esac
    done

    if [ ${#apt_missing[@]} -gt 0 ] && $IS_DEBIAN; then
        # Map to actual apt package names
        local -a apt_pkgs=()
        for name in "${apt_missing[@]}"; do
            case "$name" in
                python3) apt_pkgs+=("python3" "python3-pip") ;;
                *)       apt_pkgs+=("$name") ;;
            esac
        done
        if install_apt_batch "${apt_pkgs[@]}"; then
            # Re-check: remove successfully installed from missing_names
            local -a remaining=()
            for name in "${missing_names[@]}"; do
                local found_in_apt=false
                for apt_name in "${apt_missing[@]}"; do
                    if [ "$name" = "$apt_name" ]; then found_in_apt=true; break; fi
                done
                if $found_in_apt && command -v "$name" &>/dev/null; then
                    continue  # successfully installed, drop from list
                elif $found_in_apt; then
                    remaining+=("$name")  # apt ran but binary not found
                else
                    remaining+=("$name")  # not an apt tool, keep
                fi
            done
            missing_names=("${remaining[@]}")
        else
            # User declined or install failed — exit
            exit 1
        fi
    fi

    # If nothing left, continue
    if [ ${#missing_names[@]} -eq 0 ]; then
        echo ""
        log_success "All prerequisites now installed"
        return 0
    fi

    # Tier 2: Custom installs (one at a time, exit with re-run)
    # Process in dependency order: docker → docker compose → node → pnpm → forge → overmind
    local -a ordered=(docker "docker compose" node pnpm forge overmind)
    for tool in "${ordered[@]}"; do
        local is_missing=false
        for name in "${missing_names[@]}"; do
            if [ "$name" = "$tool" ]; then is_missing=true; break; fi
        done
        $is_missing || continue

        case "$tool" in
            node)            install_node ;;
            pnpm)            install_pnpm ;;
            docker)          install_docker ;;
            "docker compose") install_docker_compose ;;
            forge)           install_forge ;;
            overmind)        install_overmind ;;
        esac
    done
}

# ── Phase 3: Clone Repos ─────────────────────

phase_clone() {
    echo ""
    echo "Cloning repositories..."
    echo ""

    local cloned=0 existed=0 failed=0
    local -a clone_dirs=() clone_urls=() clone_pids=() clone_logs=()
    local -a all_dirs=() all_states=()  # track display order (existing + cloning)
    local tmpdir; tmpdir=$(mktemp -d)
    local spinner_chars="$SPIN"

    # Print initial state for all repos and kick off parallel clones
    for entry in "${REPOS[@]}"; do
        IFS='|' read -r dir url flags <<< "$entry"
        all_dirs+=("$dir")

        if [ -d "$PARENT/$dir" ]; then
            all_states+=("exists")
            echo -e "  ${DIM}-${NC} ${DIM}$(pad "$dir" 23)already exists${NC}"
            ((existed++)) || true
        else
            all_states+=("cloning")
            echo -e "  ${YELLOW}|${NC} $(pad "$dir" 23)cloning..."
            local logfile="$tmpdir/$dir.log"
            # shellcheck disable=SC2086
            git clone $flags "$url" "$PARENT/$dir" >"$logfile" 2>&1 &
            clone_dirs+=("$dir")
            clone_urls+=("$url")
            clone_pids+=($!)
            clone_logs+=("$logfile")
        fi
    done

    # Animate spinners and update lines as clones complete
    if [ ${#clone_pids[@]} -gt 0 ]; then
        local total=${#clone_pids[@]} done_count=0 spin_idx=0
        local -a clone_rc=()
        for i in "${!clone_pids[@]}"; do clone_rc+=(""); done
        local num_lines=${#all_dirs[@]}

        while [ "$done_count" -lt "$total" ]; do
            spin_idx=$(( (spin_idx + 1) % ${#spinner_chars} ))
            local spin="${spinner_chars:$spin_idx:1}"

            # Check for newly completed clones
            for i in "${!clone_pids[@]}"; do
                [ -n "${clone_rc[$i]}" ] && continue
                if ! kill -0 "${clone_pids[$i]}" 2>/dev/null; then
                    local rc=0
                    wait "${clone_pids[$i]}" || rc=$?
                    clone_rc[$i]="$rc"
                    ((done_count++)) || true
                    if [ "$rc" -eq 0 ]; then
                        ((cloned++)) || true
                    else
                        ((failed++)) || true
                    fi
                fi
            done

            # Move cursor up to first line and redraw all
            printf "\033[%dA" "$num_lines"

            for j in "${!all_dirs[@]}"; do
                local dir="${all_dirs[$j]}"
                if [ "${all_states[$j]}" = "exists" ]; then
                    printf "\r  ${DIM}-${NC} ${DIM}%-23s already exists${NC}%-20s\n" "$dir" ""
                else
                    # Find this dir's index in clone arrays
                    local ci=""
                    for k in "${!clone_dirs[@]}"; do
                        if [ "${clone_dirs[$k]}" = "$dir" ]; then ci=$k; break; fi
                    done
                    if [ -n "$ci" ] && [ -n "${clone_rc[$ci]}" ]; then
                        if [ "${clone_rc[$ci]}" -eq 0 ]; then
                            printf "\r  ${GREEN}✓${NC} %-23s cloned%-30s\n" "$dir" ""
                        else
                            printf "\r  ${RED}✗${NC} %-23s clone failed%-24s\n" "$dir" ""
                        fi
                    else
                        printf "\r  ${YELLOW}%s${NC} %-23s cloning...%-26s\n" "$spin" "$dir" ""
                    fi
                fi
            done

            [ "$done_count" -lt "$total" ] && sleep 0.1
        done

        # Show error details for failures
        if [ "$failed" -gt 0 ]; then
            echo ""
            for i in "${!clone_dirs[@]}"; do
                if [ "${clone_rc[$i]}" -ne 0 ]; then
                    echo -e "  ${RED}${clone_dirs[$i]}:${NC}"
                    cat "${clone_logs[$i]}" 2>/dev/null | tail -3 | sed 's/^/    /'
                fi
            done
        fi
    fi

    rm -rf "$tmpdir"

    echo ""
    if [ "$failed" -gt 0 ]; then
        log_error "$failed clone(s) failed"
        echo ""
        echo -e "  ${DIM}Hint: verify SSH access with: ssh -T git@github.com${NC}"
        echo ""
        echo "  Fix SSH access, then: make setup"
        exit 1
    fi
    log_success "$cloned cloned, $existed already existed"
}

# ── Phase 4: Branch Display + Pause ──────────

phase_branches() {
    echo ""
    echo "Repository branches:"
    echo ""

    for entry in "${REPOS[@]}"; do
        IFS='|' read -r dir _ _ <<< "$entry"
        local repo_path="$PARENT/$dir"
        [ -d "$repo_path/.git" ] || continue

        local branch; branch=$(git -C "$repo_path" branch --show-current 2>/dev/null || echo "detached")
        echo -e "  ${BOLD}$dir${NC}     $repo_path"
        echo "    branch: $branch"

        # Show remote branches (max 10)
        local remotes; remotes=$(git -C "$repo_path" branch -r 2>/dev/null | grep -v HEAD | sed 's|origin/||;s/^[[:space:]]*//' | sort -u)
        local count; count=$(echo "$remotes" | wc -l)
        if [ "$count" -gt 10 ]; then
            local shown; shown=$(echo "$remotes" | head -10 | paste -sd', ')
            echo "    remote: $shown (+$((count - 10)) more)"
        elif [ -n "$remotes" ]; then
            local shown; shown=$(echo "$remotes" | paste -sd', ')
            echo "    remote: $shown"
        fi
        echo ""
    done

    echo -e "  Verify you're on the correct branches before continuing."
    echo -e "  ${DIM}For devnet: cd $PARENT/zephyr && git checkout fresh-dev-bootstrap${NC}"
    echo ""
    if ! $AUTO_YES; then
        printf "  Press Enter to continue (or Ctrl-C to check out branches first)..."
        read -r </dev/tty
    fi
}

# ── Phase 5: Install Dependencies ────────────

phase_deps() {
    echo ""
    echo "Installing dependencies..."
    echo ""

    local foundry_dir="$PARENT/zephyr-eth-foundry"
    local bridge_dir="$PARENT/zephyr-bridge"
    local engine_dir="$PARENT/zephyr-bridge-engine"

    # Build task lists
    TASK_NAMES=() TASK_CMDS=() TASK_STATES=()

    # Forge submodules
    if [ -d "$foundry_dir" ]; then
        TASK_NAMES+=("[forge] zephyr-eth-foundry")
        if [ -d "$foundry_dir/lib/forge-std/src" ]; then
            TASK_CMDS+=("true")
            TASK_STATES+=("skip")
        else
            TASK_CMDS+=("cd '$foundry_dir' && git submodule update --init --recursive")
            TASK_STATES+=("pending")
        fi
    fi

    # pnpm: zephyr-bridge
    # CI=1 prevents pnpm from aborting on no-TTY (background tasks have no TTY)
    if [ -d "$bridge_dir" ]; then
        TASK_NAMES+=("[pnpm]  zephyr-bridge")
        TASK_CMDS+=("cd '$bridge_dir' && CI=1 pnpm install --reporter=silent")
        TASK_STATES+=("pending")
    fi

    # pnpm: zephyr-bridge-engine
    if [ -d "$engine_dir" ]; then
        TASK_NAMES+=("[pnpm]  zephyr-bridge-engine")
        TASK_CMDS+=("cd '$engine_dir' && CI=1 pnpm install --reporter=silent")
        TASK_STATES+=("pending")

        if [ -d "$engine_dir/apps/web" ]; then
            TASK_NAMES+=("[pnpm]  engine/apps/web")
            TASK_CMDS+=("cd '$engine_dir/apps/web' && CI=1 pnpm install --reporter=silent")
            TASK_STATES+=("pending")
        fi
    fi

    # pnpm: status-dashboard
    if [ -d "$ROOT/status-dashboard" ]; then
        TASK_NAMES+=("[pnpm]  status-dashboard")
        TASK_CMDS+=("cd '$ROOT/status-dashboard' && CI=1 pnpm install --reporter=silent")
        TASK_STATES+=("pending")
    fi

    # Python: requests
    TASK_NAMES+=("[pip]   python3-requests")
    if python3 -c "import requests" 2>/dev/null; then
        TASK_CMDS+=("true")
        TASK_STATES+=("skip")
    else
        if $IS_DEBIAN; then
            TASK_CMDS+=("sudo apt install -y python3-requests")
        else
            TASK_CMDS+=("pip3 install requests")
        fi
        TASK_STATES+=("pending")
    fi

    local dep_failed=0
    run_parallel_tasks || dep_failed=$?

    echo ""
    if [ "$dep_failed" -gt 0 ]; then
        log_warn "$dep_failed dependency install(s) failed — review errors above"
    else
        log_success "All dependencies installed"
    fi
    echo ""
}

# ── Phase 5b: Zephyr Build Dependencies ──────

# Core packages to check (subset — if these are present, the rest likely are too)
ZEPHYR_CHECK_PKGS=(cmake libboost-dev libssl-dev libzmq3-dev libsodium-dev)

# Full install list for Ubuntu/Debian
ZEPHYR_BUILD_PKGS=(
    build-essential cmake pkg-config libssl-dev libzmq3-dev
    libunbound-dev libsodium-dev libunwind8-dev liblzma-dev
    libreadline6-dev libexpat1-dev libpgm-dev qttools5-dev-tools
    libhidapi-dev libusb-1.0-0-dev libprotobuf-dev protobuf-compiler
    libudev-dev libboost-chrono-dev libboost-date-time-dev
    libboost-filesystem-dev libboost-locale-dev
    libboost-program-options-dev libboost-regex-dev
    libboost-serialization-dev libboost-system-dev
    libboost-thread-dev ccache doxygen graphviz
)

phase_zephyr_deps() {
    echo ""
    echo -e "Zephyr C++ build dependencies"
    echo ""

    if ! [ -d "$PARENT/zephyr" ]; then
        dim "zephyr repo not cloned — skipping"
        return 0
    fi

    ok "Zephyr builds from source inside Docker (Ubuntu 24.04)"
    echo -e "  ${DIM}No host C++ dependencies required — 'make dev-init' handles everything.${NC}"
}

# ── Phase 5c: Verify Zephyr Repo ─────────────

phase_verify_zephyr() {
    echo ""
    echo "Verify Zephyr repo"
    echo ""

    if ! [ -d "$PARENT/zephyr" ]; then
        dim "zephyr repo not cloned — skipping"
        return 0
    fi

    if ! [ -d "$PARENT/zephyr/.git" ]; then
        fail "zephyr directory exists but is not a git repo"
        return 1
    fi

    ok "Zephyr repo found at $PARENT/zephyr"
    echo -e "  ${DIM}Binaries are built inside Docker on 'make dev-init' — no native build needed.${NC}"
}

# ── Phase 6: Key Generation ───────────────────

# Check if .env exists and has no unresolved <KEYGEN:> placeholders
env_is_valid() {
    [ -f "$ROOT/.env" ] && ! grep -q '<KEYGEN:' "$ROOT/.env"
}

phase_keygen() {
    echo ""
    echo "EVM key generation"
    echo ""

    # Already configured — skip
    if env_is_valid; then
        ok ".env already configured"
        return 0
    fi

    # cast required for keygen
    if ! command -v cast &>/dev/null; then
        dim "cast (Foundry) not found — skipping keygen"
        echo -e "  ${DIM}Run later: make keygen${NC}"
        return 0
    fi

    echo -e "  ${DIM}Generates EVM keys, secrets, and auto-detects ROOT + PATH.${NC}"
    echo -e "  ${DIM}Writes to .env from .env.example template.${NC}"

    if ask_yn "Generate keys now? (or N to run 'make keygen' later)"; then
        echo ""
        spin_while "Generating EVM keys + .env" \
            python3 "$SCRIPT_DIR/keygen.py" --write-env --force --quiet

        echo ""
        # Show key summary
        local root_val; root_val=$(grep '^ROOT=' "$ROOT/.env" 2>/dev/null | head -1 | cut -d= -f2-)
        local deployer; deployer=$(grep '^DEPLOYER_ADDRESS=' "$ROOT/.env" 2>/dev/null | head -1 | cut -d= -f2-)
        local signer; signer=$(grep '^BRIDGE_SIGNER_ADDRESS=' "$ROOT/.env" 2>/dev/null | head -1 | cut -d= -f2-)
        echo -e "  ${DIM}ROOT=${root_val}${NC}"
        echo -e "  ${DIM}Deployer: ${deployer}${NC}"
        echo -e "  ${DIM}Bridge signer: ${signer}${NC}"

        log_success ".env generated"
    else
        echo ""
        log_skip "Skipped — run later: make keygen"
    fi
}

# ── Phase 7: Summary + Next Steps ────────────

phase_summary() {
    echo "=========================================="
    echo "  Setup Complete"
    echo "=========================================="
    echo ""
    echo "  Repos:"

    for entry in "${REPOS[@]}"; do
        IFS='|' read -r dir _ _ <<< "$entry"
        local repo_path="$PARENT/$dir"
        if [ -d "$repo_path/.git" ]; then
            local branch; branch=$(git -C "$repo_path" branch --show-current 2>/dev/null || echo "?")
            printf "    %-25s %s\n" "$dir" "$branch"
        fi
    done

    echo ""
    echo "  Next steps:"
    echo ""
    if env_is_valid; then
        echo "    1. make dev-init && make dev-setup && make dev"
    else
        echo "    1. make keygen       (generates keys + auto-sets ROOT and PATH)"
        echo "    2. make dev-init && make dev-setup && make dev"
    fi
    echo ""
    echo -e "  ${DIM}Docs: docs/setup/dev.md${NC}"
    echo "=========================================="
    echo ""
}

# ── Main ──────────────────────────────────────

detect_os
print_header
phase_prereqs
phase_clone
phase_branches
phase_deps
phase_zephyr_deps
phase_verify_zephyr
phase_keygen
phase_summary
