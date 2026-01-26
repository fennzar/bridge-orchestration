#!/bin/bash
set -euo pipefail

# ===========================================
# Zephyr Bridge Stack - Deploy Contracts
# ===========================================
# Deploys all contracts using orchestration .env configuration.
# Does NOT use repo-local scripts - this is the source of truth.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[OK]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Load environment safely (handles unquoted values like mnemonics)
source "$SCRIPT_DIR/lib/env.sh"
if ! load_env "$ORCH_DIR/.env"; then
    log_error ".env not found in $ORCH_DIR"
    exit 1
fi

# Validate required variables
: "${FOUNDRY_REPO_PATH:?FOUNDRY_REPO_PATH not set}"
: "${DEPLOYER_PRIVATE_KEY:?DEPLOYER_PRIVATE_KEY not set}"
: "${BRIDGE_SIGNER_ADDRESS:?BRIDGE_SIGNER_ADDRESS not set}"
: "${EVM_RPC_HTTP:?EVM_RPC_HTTP not set}"

echo "==========================================="
echo "  Deploy Contracts to Anvil"
echo "==========================================="
echo ""
echo "RPC:      $EVM_RPC_HTTP"
echo "Deployer: $DEPLOYER_ADDRESS"
echo "Signer:   $BRIDGE_SIGNER_ADDRESS"
echo ""

cd "$FOUNDRY_REPO_PATH"

# Check Anvil is running
if ! ~/.foundry/bin/cast block-number --rpc-url "$EVM_RPC_HTTP" &> /dev/null; then
    log_error "Anvil not running at $EVM_RPC_HTTP"
    log_info "Start with: cd $ORCH_DIR && docker compose up -d anvil"
    exit 1
fi

log_info "Current block: $(~/.foundry/bin/cast block-number --rpc-url "$EVM_RPC_HTTP")"

# Export for forge scripts
export RPC_URL="$EVM_RPC_HTTP"
export DEPLOYER_KEY="$DEPLOYER_PRIVATE_KEY"
export DEPLOYER_ADDR="$DEPLOYER_ADDRESS"
export MINT_ADDR="$DEPLOYER_ADDRESS"
export ADMIN="$DEPLOYER_ADDRESS"
export MINTER="$DEPLOYER_ADDRESS"
export SIGNER="$BRIDGE_SIGNER_ADDRESS"

# ===========================================
# Step 1: Deploy Mock USD tokens (USDC, USDT)
# ===========================================
log_info "Deploying mock USD tokens..."
~/.foundry/bin/forge script script/00_DeployMockUSD.sol:DeployMockUSD \
    --sig "run()" \
    --rpc-url "$RPC_URL" --private-key "$DEPLOYER_KEY" --broadcast -vvv

# ===========================================
# Step 2: Deploy Zephyr wrapped tokens
# ===========================================
log_info "Deploying Zephyr wrapped tokens (wZEPH, wZSD, wZRS, wZYS)..."
~/.foundry/bin/forge script script/01_DeployZephyrTokens.sol:DeployZephyrTokens \
    --sig "run()" \
    --rpc-url "$RPC_URL" --private-key "$DEPLOYER_KEY" --broadcast -vvv

# ===========================================
# Step 3: Mint initial token supplies
# ===========================================
log_info "Minting initial token supplies..."

TOKENS=("wZEPH:200000" "wZSD:200000" "wZYS:50000" "wZRS:50000")
for TOKEN_AMT in "${TOKENS[@]}"; do
    TOKEN="${TOKEN_AMT%%:*}"
    AMOUNT="${TOKEN_AMT##*:}"
    log_info "  Minting $AMOUNT $TOKEN..."
    ~/.foundry/bin/forge script script/02_Mint.s.sol:MintByTicker \
        --sig "run(string,string)" "$TOKEN" "$AMOUNT" \
        --rpc-url "$RPC_URL" --private-key "$DEPLOYER_KEY" --broadcast -vvv
done

# ===========================================
# Step 4: Deploy Uniswap V4 stack
# ===========================================
log_info "Deploying Uniswap V4 stack..."
# Pass existing Permit2 address if already deployed (avoids CREATE2 collision on redeploy)
EXISTING_PERMIT2=$(python3 -c "
import json, sys
try:
    d = json.load(open('.forge-snapshots/addresses.json'))
    print(d.get('contracts',{}).get('permit2',''))
except: pass
" 2>/dev/null || true)
if [ -n "$EXISTING_PERMIT2" ]; then
    log_info "Found existing Permit2 at: $EXISTING_PERMIT2"
    export PERMIT2_ADDRESS="$EXISTING_PERMIT2"
fi
~/.foundry/bin/forge script script/uniswap/00_DeployV4Stack.s.sol:DeployV4Stack \
    --sig "run()" \
    --rpc-url "$RPC_URL" --private-key "$DEPLOYER_KEY" --broadcast -vvv

# ===========================================
# Step 5: Create pools and add liquidity
# ===========================================
MARKETS=("USDT-USDC" "wZSD-USDT" "wZYS-wZSD" "wZEPH-wZSD" "wZRS-wZEPH")

for MARKET in "${MARKETS[@]}"; do
    log_info "Creating pool: $MARKET"
    MARKET="$MARKET" ~/.foundry/bin/forge script script/uniswap/01_CreatePoolFromJson.s.sol:CreatePoolFromJson \
        --sig "run()" \
        --rpc-url "$RPC_URL" --broadcast --private-key "$DEPLOYER_KEY" -vvv

    log_info "Adding liquidity: $MARKET"
    MARKET="$MARKET" ~/.foundry/bin/forge script script/uniswap/02_AddLiquidityFromJson.s.sol:AddLiquidityFromJson \
        --sig "run()" \
        --rpc-url "$RPC_URL" --broadcast --private-key "$DEPLOYER_KEY" -vvv
done

log_success "All contracts deployed"

# ===========================================
# Sync addresses to other repos
# ===========================================
if [ -f ".forge-snapshots/addresses.json" ]; then
    log_info "Syncing deployed addresses..."

    # Copy to orchestration config
    mkdir -p "$ORCH_DIR/config"
    cp .forge-snapshots/addresses.json "$ORCH_DIR/config/addresses.json"

    # Copy to bridge repo config package source (where the app reads from)
    BRIDGE_ADDR_DIR="$BRIDGE_REPO_PATH/packages/config/src/addresses"
    if [ -d "$BRIDGE_ADDR_DIR" ]; then
        cp .forge-snapshots/addresses.json "$BRIDGE_ADDR_DIR/addresses.local.json"
        log_info "Copied to $BRIDGE_ADDR_DIR/addresses.local.json"
    fi

    # Also copy to legacy location for backwards compat
    if [ -d "$BRIDGE_REPO_PATH/config" ]; then
        cp .forge-snapshots/addresses.json "$BRIDGE_REPO_PATH/config/addresses.local.json"
    fi

    # Update deployed-addresses.json (flat format for test runner)
    python3 -c "
import json
d = json.load(open('$ORCH_DIR/config/addresses.json'))
out = {name: info['address'] for name, info in d.get('tokens', {}).items()}
out['_source'] = 'config/addresses.json'
json.dump(out, open('$ORCH_DIR/deployed-addresses.json', 'w'), indent=2)
print()  # trailing newline
" 2>/dev/null && log_info "Updated deployed-addresses.json" || true

    log_success "Addresses synced to config/addresses.json"
fi

# ===========================================
# Create Anvil state snapshot
# ===========================================
log_info "Creating Anvil state snapshot..."
mkdir -p "$ANVIL_SNAPSHOT_DIR" 2>/dev/null || true
if ~/.foundry/bin/cast rpc anvil_dumpState --rpc-url "$EVM_RPC_HTTP" > "$ANVIL_SNAPSHOT_DIR/post-deploy.hex" 2>/dev/null; then
    log_success "Snapshot saved: $ANVIL_SNAPSHOT_DIR/post-deploy.hex"
else
    log_warn "Could not save Anvil snapshot (permission issue?)"
fi

echo ""
echo "==========================================="
log_success "Deployment complete"
echo "==========================================="
echo ""
echo "Block: $(~/.foundry/bin/cast block-number --rpc-url "$EVM_RPC_HTTP")"
echo "Addresses: $ORCH_DIR/config/addresses.json"
echo ""
