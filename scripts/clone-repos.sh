#!/usr/bin/env bash
set -euo pipefail

# Clone all required repos and install dependencies for the bridge-orchestration stack.
# Run from any directory — repos are cloned as siblings of bridge-orchestration.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PARENT="$(cd "$ROOT/.." && pwd)"

echo "=== Bridge Orchestration — Setup ==="
echo "Parent directory: $PARENT"
echo ""

# ─────────────────────────────────────────────
# Phase 1: Check prerequisites
# ─────────────────────────────────────────────

echo "=== Checking prerequisites ==="
echo ""

MISSING=0

require() {
    local name="$1"
    local label="${2:-$1}"
    local install_hint="$3"

    if command -v "$name" &>/dev/null; then
        local ver
        ver=$($name --version 2>/dev/null || $name -V 2>/dev/null || echo "")
        echo "  [ok]    $label  $(echo "$ver" | head -1)"
    else
        echo "  [MISS]  $label  — $install_hint"
        MISSING=1
    fi
}

require git      "git"      "sudo apt install git"
require python3  "python3"  "sudo apt install python3 python3-pip"
require node     "node"     "nvm install 22"
require pnpm     "pnpm"     "npm install -g pnpm"
require docker   "docker"   "see below: install-docker"
require forge    "forge"    "curl -L https://foundry.paradigm.xyz | bash && foundryup"
require overmind "overmind" "see below: install-overmind"
require tmux     "tmux"     "sudo apt install tmux"

# Check docker compose plugin separately (docker can exist without it)
if command -v docker &>/dev/null; then
    if docker compose version &>/dev/null; then
        echo "  [ok]    docker-compose  $(docker compose version --short 2>/dev/null)"
    else
        echo "  [MISS]  docker-compose  — see below: install-docker"
        MISSING=1
    fi
fi

echo ""

if [ "$MISSING" -eq 1 ]; then
    echo "ERROR: Missing prerequisites. Install the tools above and re-run."
    echo ""
    echo "── Install helpers ──────────────────────────"
    echo ""
    echo "install-docker (Docker CE + Compose plugin via official repo):"
    echo ""
    echo "  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker.gpg"
    echo "  echo \"deb [arch=amd64 signed-by=/usr/share/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \$(lsb_release -cs) stable\" > /etc/apt/sources.list.d/docker.list"
    echo "  apt update && apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin"
    echo ""
    echo "install-overmind (v2.5.1 + tmux dependency):"
    echo ""
    echo "  apt install -y tmux"
    echo "  wget -q https://github.com/DarthSim/overmind/releases/download/v2.5.1/overmind-v2.5.1-linux-amd64.gz"
    echo "  gunzip overmind-v2.5.1-linux-amd64.gz"
    echo "  chmod +x overmind-v2.5.1-linux-amd64 && mv overmind-v2.5.1-linux-amd64 /usr/local/bin/overmind"
    echo ""
    exit 1
fi

echo "All prerequisites found."
echo ""

# ─────────────────────────────────────────────
# Phase 2: Clone repos
# ─────────────────────────────────────────────

echo "=== Cloning repos ==="
echo ""

clone_or_skip() {
    local dir="$1"
    local url="$2"
    local flags="${3:-}"

    if [ -d "$PARENT/$dir" ]; then
        echo "  [skip]  $dir (already exists)"
    else
        echo "  [clone] $dir ← $url"
        git clone $flags "$url" "$PARENT/$dir"
    fi
}

# Private repos (SSH)
clone_or_skip "zephyr-eth-foundry"   "git@github.com:fennzar/zephyr-uniswap-v4-foundry.git" "--recursive"
clone_or_skip "zephyr-bridge"        "git@github.com:fennzar/zephyr-bridge.git"
clone_or_skip "zephyr-bridge-engine" "git@github.com:fennzar/zephyr-bridge-engine.git"

# Public repo (HTTPS, recursive for submodules)
clone_or_skip "zephyr" "git@github.com:fennzar/zephyr.git" "--recursive"

echo ""

# ─────────────────────────────────────────────
# Phase 3: Install dependencies
# ─────────────────────────────────────────────

echo "=== Installing dependencies ==="
echo ""

# Foundry (Solidity — forge-std, openzeppelin, uniswap-hooks, etc.)
echo "  [forge] zephyr-eth-foundry ..."
if [ -d "$PARENT/zephyr-eth-foundry/lib/forge-std/src" ]; then
    echo "          dependencies already installed"
else
    echo "          initializing submodules..."
    (cd "$PARENT/zephyr-eth-foundry" && git submodule update --init --recursive 2>&1 | tail -5)
fi

# Bridge (pnpm monorepo)
echo "  [pnpm]  zephyr-bridge ..."
(cd "$PARENT/zephyr-bridge" && pnpm install 2>&1 | tail -1)

# Engine
echo "  [pnpm]  zephyr-bridge-engine ..."
(cd "$PARENT/zephyr-bridge-engine" && pnpm install 2>&1 | tail -1)

# Python dependencies (zephyr-cli + orchestration scripts)
echo "  [apt]   python3-requests ..."
if python3 -c "import requests" 2>/dev/null; then
    echo "          already installed"
else
    sudo apt install -y python3-requests 2>&1 | tail -1
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Next steps:"
echo "  cd $PARENT/zephyr && git checkout fresh-dev-bootstrap"
echo "  cd $ROOT"
echo "  make keygen                            # Generate fresh keys → .env"
echo "  # Edit .env: set ROOT=$PARENT"
echo "  #            set PATH to include node/pnpm/foundry bins"
echo "  ./scripts/sync-zephyr-artifacts.sh     # Vendor Zephyr binaries"
echo "  make dev-init && make dev-setup        # Init chain + deploy contracts"
echo "  make dev                               # Start the stack"
echo ""

# ─────────────────────────────────────────────
# Zephyr C++ build dependencies (informational)
# ─────────────────────────────────────────────

echo "=== Zephyr build dependencies (optional) ==="
echo ""
echo "Only needed if compiling the Zephyr daemon from source."
echo ""

if [ -f /etc/os-release ]; then
    . /etc/os-release
fi

case "${ID:-unknown}" in
    ubuntu|debian)
        echo "Detected: Debian/Ubuntu ($PRETTY_NAME)"
        echo ""
        echo "  sudo apt update && sudo apt install \\"
        echo "    build-essential cmake pkg-config libssl-dev libzmq3-dev \\"
        echo "    libunbound-dev libsodium-dev libunwind8-dev liblzma-dev \\"
        echo "    libreadline6-dev libexpat1-dev libpgm-dev qttools5-dev-tools \\"
        echo "    libhidapi-dev libusb-1.0-0-dev libprotobuf-dev protobuf-compiler \\"
        echo "    libudev-dev libboost-chrono-dev libboost-date-time-dev \\"
        echo "    libboost-filesystem-dev libboost-locale-dev \\"
        echo "    libboost-program-options-dev libboost-regex-dev \\"
        echo "    libboost-serialization-dev libboost-system-dev \\"
        echo "    libboost-thread-dev python3 ccache doxygen graphviz"
        ;;
    arch|manjaro)
        echo "Detected: Arch ($PRETTY_NAME)"
        echo ""
        echo "  sudo pacman -Syu --needed base-devel cmake boost openssl zeromq \\"
        echo "    libpgm unbound libsodium libunwind xz readline expat gtest \\"
        echo "    python3 ccache doxygen graphviz qt5-tools hidapi libusb \\"
        echo "    protobuf systemd"
        ;;
    fedora)
        echo "Detected: Fedora ($PRETTY_NAME)"
        echo ""
        echo "  sudo dnf install gcc gcc-c++ cmake pkgconf boost-devel \\"
        echo "    openssl-devel zeromq-devel openpgm-devel unbound-devel \\"
        echo "    libsodium-devel libunwind-devel xz-devel readline-devel \\"
        echo "    expat-devel gtest-devel ccache doxygen graphviz qt5-linguist \\"
        echo "    hidapi-devel libusbx-devel protobuf-devel protobuf-compiler \\"
        echo "    systemd-devel"
        ;;
    opensuse*)
        echo "Detected: openSUSE ($PRETTY_NAME)"
        echo ""
        echo "  sudo zypper ref && sudo zypper in cppzmq-devel \\"
        echo "    libboost_chrono-devel libboost_date_time-devel \\"
        echo "    libboost_filesystem-devel libboost_locale-devel \\"
        echo "    libboost_program_options-devel libboost_regex-devel \\"
        echo "    libboost_serialization-devel libboost_system-devel \\"
        echo "    libboost_thread-devel libexpat-devel libminiupnpc-devel \\"
        echo "    libsodium-devel libunwind-devel unbound-devel cmake doxygen \\"
        echo "    ccache fdupes gcc-c++ libevent-devel libopenssl-devel \\"
        echo "    pkgconf-pkg-config readline-devel xz-devel \\"
        echo "    libqt5-qttools-devel patterns-devel-C-C++-devel_C_C++"
        ;;
    *)
        echo "Could not detect distro. Here are commands for common platforms:"
        echo ""
        echo "Debian/Ubuntu:"
        echo "  sudo apt update && sudo apt install \\"
        echo "    build-essential cmake pkg-config libssl-dev libzmq3-dev \\"
        echo "    libunbound-dev libsodium-dev libunwind8-dev liblzma-dev \\"
        echo "    libreadline6-dev libexpat1-dev libpgm-dev qttools5-dev-tools \\"
        echo "    libhidapi-dev libusb-1.0-0-dev libprotobuf-dev protobuf-compiler \\"
        echo "    libudev-dev libboost-chrono-dev libboost-date-time-dev \\"
        echo "    libboost-filesystem-dev libboost-locale-dev \\"
        echo "    libboost-program-options-dev libboost-regex-dev \\"
        echo "    libboost-serialization-dev libboost-system-dev \\"
        echo "    libboost-thread-dev python3 ccache doxygen graphviz"
        echo ""
        echo "Arch:"
        echo "  sudo pacman -Syu --needed base-devel cmake boost openssl zeromq \\"
        echo "    libpgm unbound libsodium libunwind xz readline expat gtest \\"
        echo "    python3 ccache doxygen graphviz qt5-tools hidapi libusb \\"
        echo "    protobuf systemd"
        echo ""
        echo "Fedora:"
        echo "  sudo dnf install gcc gcc-c++ cmake pkgconf boost-devel \\"
        echo "    openssl-devel zeromq-devel openpgm-devel unbound-devel \\"
        echo "    libsodium-devel libunwind-devel xz-devel readline-devel \\"
        echo "    expat-devel gtest-devel ccache doxygen graphviz qt5-linguist \\"
        echo "    hidapi-devel libusbx-devel protobuf-devel protobuf-compiler \\"
        echo "    systemd-devel"
        ;;
esac

echo ""
echo "macOS (via Homebrew):"
echo "  brew update && brew bundle --file=$PARENT/zephyr/contrib/brew/Brewfile"
echo ""
