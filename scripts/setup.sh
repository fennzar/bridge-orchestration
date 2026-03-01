#!/usr/bin/env bash
set -euo pipefail

# ===========================================
# Bridge Orchestration — Interactive Setup
# ===========================================
# Checks prerequisites, offers auto-install, clones repos,
# installs dependencies, and prints next steps.
#
# Idempotent — safe to run repeatedly.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PARENT="$(cd "$ROOT/.." && pwd)"

source "$SCRIPT_DIR/lib/logging.sh"

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
        local ver; ver=$(forge --version 2>/dev/null | head -1 | sed 's/forge //')
        add_result "forge" "$ver" "ok"
    else
        add_result "forge" "not found" "missing"
    fi
}

check_overmind() {
    if command -v overmind &>/dev/null; then
        local ver; ver=$(overmind --version 2>/dev/null | head -1 | sed 's/.*v//')
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
        # Install one at a time with per-package feedback
        local all_ok=true
        for pkg in "${pkgs[@]}"; do
            printf "    %-20s " "$pkg"
            local output rc=0
            output=$(sudo apt install -y "$pkg" 2>&1) || rc=$?
            if [ "$rc" -eq 0 ]; then
                echo -e "${GREEN}✓${NC}"
            else
                echo -e "${RED}✗${NC}"
                echo "$output" | tail -3 | sed 's/^/      /'
                all_ok=false
            fi
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
        echo "  Installing nvm..."
        local nvm_rc=0
        curl -o- "https://raw.githubusercontent.com/nvm-sh/nvm/v${NVM_VERSION}/install.sh" 2>/dev/null | bash 2>&1 | tail -3 || nvm_rc=$?
        if [ "$nvm_rc" -eq 0 ]; then
            export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
            # shellcheck disable=SC1091
            . "$NVM_DIR/nvm.sh" 2>/dev/null || true
            echo "  Installing node ${NODE_MIN}..."
            nvm install "$NODE_MIN" 2>&1 | tail -3
            local ver; ver=$(node --version 2>/dev/null | sed 's/^v//')
            if [ -n "$ver" ]; then
                log_success "node $ver installed via nvm"
                echo ""
                echo "  Run 'make setup' to continue."
                exit 0
            fi
        fi
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
        local pnpm_output pnpm_rc=0
        pnpm_output=$(npm install -g pnpm 2>&1) || pnpm_rc=$?
        echo "$pnpm_output" | tail -3
        if [ "$pnpm_rc" -eq 0 ] && command -v pnpm &>/dev/null; then
            local ver; ver=$(pnpm --version 2>/dev/null)
            log_success "pnpm $ver installed"
            echo ""
            echo "  Run 'make setup' to continue."
            exit 0
        else
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
        echo "  Installing Docker CE (this may take a minute)..."
        local output rc=0
        output=$(curl -fsSL https://get.docker.com | sh 2>&1) || rc=$?
        if [ "$rc" -eq 0 ] && command -v docker &>/dev/null; then
            local ver; ver=$(docker --version 2>/dev/null | sed 's/Docker version \([^,]*\).*/\1/')
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
            echo "$output" | tail -5
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
            if sudo apt install -y docker-compose-plugin 2>&1 | tail -3; then
                local ver; ver=$(docker compose version --short 2>/dev/null)
                log_success "docker compose $ver installed"
            else
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
        echo "  Installing foundryup..."
        local foundry_rc=0
        curl -L https://foundry.paradigm.xyz 2>/dev/null | bash 2>&1 | tail -3 || foundry_rc=$?
        if [ "$foundry_rc" -eq 0 ]; then
            export PATH="$HOME/.foundry/bin:$PATH"
            echo "  Running foundryup..."
            foundryup 2>&1 | tail -5
            if command -v forge &>/dev/null; then
                log_success "forge installed"
                echo ""
                echo "  Run 'make setup' to continue."
                exit 0
            fi
        fi
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
            echo "  Installing tmux..."
            sudo apt install -y tmux 2>&1 | tail -1
        fi
        echo "  Downloading overmind v${OVERMIND_VERSION}..."
        local tmp; tmp=$(mktemp -d)
        if curl -fsSL -o "$tmp/overmind.gz" "https://github.com/DarthSim/overmind/releases/download/v${OVERMIND_VERSION}/overmind-v${OVERMIND_VERSION}-linux-amd64.gz" && \
           gunzip "$tmp/overmind.gz" && \
           chmod +x "$tmp/overmind" && \
           sudo mv "$tmp/overmind" /usr/local/bin/overmind; then
            rm -rf "$tmp"
            log_success "overmind v${OVERMIND_VERSION} installed"
            echo ""
            echo "  Run 'make setup' to continue."
            exit 0
        else
            rm -rf "$tmp"
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

    local cloned=0 existed=0

    for entry in "${REPOS[@]}"; do
        IFS='|' read -r dir url flags <<< "$entry"

        if [ -d "$PARENT/$dir" ]; then
            dim "$(pad "$dir" 23)already exists"
            ((existed++)) || true
        else
            local clone_output clone_rc=0
            # shellcheck disable=SC2086
            clone_output=$(git clone $flags "$url" "$PARENT/$dir" 2>&1) || clone_rc=$?
            if [ "$clone_rc" -eq 0 ]; then
                ok "$(pad "$dir" 23)cloned"
                ((cloned++)) || true
            else
                echo "$clone_output" | tail -3
                fail "$(pad "$dir" 23)clone failed"
                echo ""
                echo -e "  ${DIM}Hint: verify SSH access with: ssh -T git@github.com${NC}"
                echo ""
                echo "  Fix SSH access, then: make setup"
                exit 1
            fi
        fi
    done

    echo ""
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
    printf "  Press Enter to continue (or Ctrl-C to check out branches first)..."
    read -r </dev/tty
}

# ── Phase 5: Install Dependencies ────────────

phase_deps() {
    echo ""
    echo "Installing dependencies..."
    echo ""

    # Helper: run install command, capture exit code
    run_install() {
        local output rc=0
        output=$("$@" 2>&1) || rc=$?
        if [ "$rc" -ne 0 ]; then
            echo "FAILED"
            echo "$output" | tail -5
            log_warn "Install failed (exit $rc) — continuing"
        else
            echo "done"
        fi
    }

    # Forge submodules
    local foundry_dir="$PARENT/zephyr-eth-foundry"
    if [ -d "$foundry_dir" ]; then
        printf "  [forge] zephyr-eth-foundry .......... "
        if [ -d "$foundry_dir/lib/forge-std/src" ]; then
            echo "already installed"
        else
            echo ""
            run_install bash -c "cd '$foundry_dir' && git submodule update --init --recursive"
        fi
    fi

    # pnpm: zephyr-bridge
    local bridge_dir="$PARENT/zephyr-bridge"
    if [ -d "$bridge_dir" ]; then
        printf "  [pnpm]  zephyr-bridge ............... "
        run_install bash -c "cd '$bridge_dir' && pnpm install --reporter=silent"
    fi

    # pnpm: zephyr-bridge-engine
    local engine_dir="$PARENT/zephyr-bridge-engine"
    if [ -d "$engine_dir" ]; then
        printf "  [pnpm]  zephyr-bridge-engine ........ "
        run_install bash -c "cd '$engine_dir' && pnpm install --reporter=silent"

        if [ -d "$engine_dir/apps/web" ]; then
            printf "  [pnpm]  zephyr-bridge-engine/apps/web  "
            run_install bash -c "cd '$engine_dir/apps/web' && pnpm install --reporter=silent"
        fi
    fi

    # pnpm: status-dashboard
    if [ -d "$ROOT/status-dashboard" ]; then
        printf "  [pnpm]  status-dashboard ............ "
        run_install bash -c "cd '$ROOT/status-dashboard' && pnpm install --reporter=silent"
    fi

    # Python: requests
    printf "  [pip]   python3-requests ............ "
    if python3 -c "import requests" 2>/dev/null; then
        echo "already installed"
    else
        if $IS_DEBIAN; then
            run_install sudo apt install -y python3-requests
        else
            run_install pip3 install requests
        fi
    fi

    echo ""
}

# ── Phase 6: Summary + Next Steps ────────────

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
    echo "    1. make keygen"
    echo "    2. Edit .env — set ROOT=$PARENT"
    echo "    3. ./scripts/sync-zephyr-artifacts.sh"
    echo "    4. make dev-init && make dev-setup && make dev"
    echo ""
    echo -e "  ${DIM}Docs: docs/setup/dev.md${NC}"
    echo -e "  ${DIM}Zephyr C++ build deps (if compiling from source): see docs/setup/dev.md${NC}"
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
phase_summary
