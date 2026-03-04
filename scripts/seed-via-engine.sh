#!/bin/bash
set -euo pipefail

# ===========================================
# Seed Liquidity via Engine's Native Pool Seeder
# ===========================================
# Replaces the monolithic seed-liquidity.py with:
#   0. Fund engine + CEX with ETH   → cast send --value 10ether
#   1. Fund engine Zephyr wallet    → seed-liquidity.py --fund-only
#   2. Mint mock USDC/USDT          → cast send mint()
#   3. Run engine seeder            → pnpm cli setup
#   4. Save Anvil snapshot           → cast rpc anvil_dumpState
#
# The engine handles: wrap → wait for claims → claimWithSignature → LP
# The bridge watcher auto-mines in devnet mode (no manual mining needed).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

# Load shared libraries
source "$SCRIPT_DIR/lib/logging.sh"
source "$SCRIPT_DIR/lib/env.sh"
source "$SCRIPT_DIR/lib/prereqs.sh"
load_env "$ORCH_DIR/.env" || { echo "Error: .env not found"; exit 1; }

require_tool cast
require_tool python3

echo "==========================================="
echo "  Seed Liquidity (Engine Native Seeder)"
echo "==========================================="
echo ""

RPC_URL="${EVM_RPC_HTTP:-http://127.0.0.1:8545}"
ENGINE_ADDR="${ENGINE_ADDRESS}"
ENGINE_KEY="${ENGINE_PK}"
DEPLOYER_KEY="${DEPLOYER_PRIVATE_KEY}"
SNAPSHOT_DIR="${ANVIL_SNAPSHOT_DIR:-$ORCH_DIR/snapshots/anvil}"
BRIDGE_API="${BRIDGE_API_URL:-http://127.0.0.1:7051}"
CAST="cast"
ZEPHYR_CLI="${ZEPHYR_REPO_PATH}/tools/zephyr-cli/cli"

log_info "Engine EVM:  $ENGINE_ADDR"
log_info "RPC:         $RPC_URL"
log_info "Bridge API:  $BRIDGE_API"
echo ""

# ===========================================
# Step 0: Fund engine + CEX EVM wallets with ETH (10 each)
# ===========================================
log_info "Step 0: Funding EVM wallets with ETH..."

ENGINE_WEI=$($CAST balance "$ENGINE_ADDR" --rpc-url "$RPC_URL" 2>/dev/null | tr -d ' \n' || echo "0")
if [ "${ENGINE_WEI:-0}" = "0" ]; then
    $CAST send "$ENGINE_ADDR" --value 10ether \
        --private-key "$DEPLOYER_KEY" --rpc-url "$RPC_URL" >/dev/null 2>&1
    log_success "Sent 10 ETH to engine"
else
    log_success "Engine already has ETH, skipping"
fi

CEX_ADDR="${CEX_ADDRESS}"
CEX_WEI=$($CAST balance "$CEX_ADDR" --rpc-url "$RPC_URL" 2>/dev/null | tr -d ' \n' || echo "0")
if [ "${CEX_WEI:-0}" = "0" ]; then
    $CAST send "$CEX_ADDR" --value 10ether \
        --private-key "$DEPLOYER_KEY" --rpc-url "$RPC_URL" >/dev/null 2>&1
    log_success "Sent 10 ETH to CEX"
else
    log_success "CEX already has ETH, skipping"
fi
echo ""

# ===========================================
# Step 1: Fund engine Zephyr wallet
# ===========================================
log_info "Step 1: Funding engine Zephyr wallet..."
"$SCRIPT_DIR/seed-liquidity.py" --fund-only
echo ""

# ===========================================
# Step 2: Mint mock USDs to engine EVM wallet
# ===========================================
log_info "Step 2: Minting mock USD tokens..."

ADDR_FILE="$ORCH_DIR/config/addresses.json"
if [ ! -f "$ADDR_FILE" ]; then
    ADDR_FILE="$ORCH_DIR/config/addresses.local.json"
fi

USDC_ADDR=$(python3 -c "import json; d=json.load(open('$ADDR_FILE')); print(d['tokens']['USDC']['address'])")
USDT_ADDR=$(python3 -c "import json; d=json.load(open('$ADDR_FILE')); print(d['tokens']['USDT']['address'])")
USDC_DECIMALS=$(python3 -c "import json; d=json.load(open('$ADDR_FILE')); print(d['tokens']['USDC']['decimals'])")
USDT_DECIMALS=$(python3 -c "import json; d=json.load(open('$ADDR_FILE')); print(d['tokens']['USDT']['decimals'])")

# Read dynamic amounts from seeding config in addresses.json
SEED_USDC=$(python3 -c "
import json
try:
    d = json.load(open('$ADDR_FILE'))
    print(d.get('seeding', {}).get('funding', {}).get('USDC', 10000))
except: print(10000)
" 2>/dev/null)
SEED_USDT=$(python3 -c "
import json
try:
    d = json.load(open('$ADDR_FILE'))
    print(d.get('seeding', {}).get('funding', {}).get('USDT', 70000))
except: print(70000)
" 2>/dev/null)

# Mint USDC
USDC_AMOUNT=$(python3 -c "print($SEED_USDC * 10**$USDC_DECIMALS)")
USDC_BAL=$($CAST call "$USDC_ADDR" "balanceOf(address)(uint256)" "$ENGINE_ADDR" --rpc-url "$RPC_URL" 2>/dev/null | tr -d ' ' || echo "0")
if [ "${USDC_BAL:-0}" -gt 0 ] 2>/dev/null; then
    log_success "Engine already has USDC, skipping mint"
else
    $CAST send "$USDC_ADDR" "mint(address,uint256)" "$ENGINE_ADDR" "$USDC_AMOUNT" \
        --private-key "$DEPLOYER_KEY" --rpc-url "$RPC_URL" >/dev/null 2>&1
    log_success "Minted $SEED_USDC USDC"
fi

# Mint USDT
USDT_AMOUNT=$(python3 -c "print($SEED_USDT * 10**$USDT_DECIMALS)")
USDT_BAL=$($CAST call "$USDT_ADDR" "balanceOf(address)(uint256)" "$ENGINE_ADDR" --rpc-url "$RPC_URL" 2>/dev/null | tr -d ' ' || echo "0")
if [ "${USDT_BAL:-0}" -gt 0 ] 2>/dev/null; then
    log_success "Engine already has USDT, skipping mint"
else
    $CAST send "$USDT_ADDR" "mint(address,uint256)" "$ENGINE_ADDR" "$USDT_AMOUNT" \
        --private-key "$DEPLOYER_KEY" --rpc-url "$RPC_URL" >/dev/null 2>&1
    log_success "Minted $SEED_USDT USDT"
fi
echo ""

# ===========================================
# Step 2.5: Fund CEX wallets (ZEPH.x + USDT)
# ===========================================
log_info "Step 2.5: Funding CEX wallets..."

# CEX_ADDR already set in Step 0
CEX_KEY="${CEX_PK}"

# Mint USDT to CEX EVM wallet (10K USDT for ~$10K)
SEED_CEX_USDT=${SEED_CEX_USDT:-10000}
CEX_USDT_AMOUNT=$(python3 -c "print($SEED_CEX_USDT * 10**$USDT_DECIMALS)")
CEX_USDT_BAL=$($CAST call "$USDT_ADDR" "balanceOf(address)(uint256)" "$CEX_ADDR" --rpc-url "$RPC_URL" 2>/dev/null | tr -d ' ' || echo "0")
if [ "${CEX_USDT_BAL:-0}" -gt 0 ] 2>/dev/null; then
    log_success "CEX already has USDT, skipping mint"
else
    $CAST send "$USDT_ADDR" "mint(address,uint256)" "$CEX_ADDR" "$CEX_USDT_AMOUNT" \
        --private-key "$DEPLOYER_KEY" --rpc-url "$RPC_URL" >/dev/null 2>&1
    log_success "Minted $SEED_CEX_USDT USDT to CEX"
fi

# Fund CEX Zephyr wallet with ZEPH (~$10K USD worth, dynamic from oracle)
# Uses named wallet "cex" from CLI config (port 48772)
SEED_CEX_ZEPH=$(python3 -c "
import json
try:
    d = json.load(open('$ADDR_FILE'))
    print(d.get('seeding', {}).get('cexZeph', 6667))
except: print(6667)
" 2>/dev/null)
"$ZEPHYR_CLI" send gov cex "$SEED_CEX_ZEPH" 2>&1 || log_warn "CEX ZEPH send failed (may already be funded)"
log_success "Sent $SEED_CEX_ZEPH ZEPH to CEX wallet"

# Mine 12 blocks for CEX ZEPH output unlock (10-block standard transfer maturity)
log_info "Mining 12 blocks for CEX fund maturity..."
python3 -c "
import sys; sys.path.insert(0, '$SCRIPT_DIR')
from lib.seed_helpers import mine_blocks
mine_blocks(12)
"
log_success "Blocks mined, CEX funds maturing"
echo ""

# ===========================================
# Step 3: Run engine seeder (wrap → claim → LP)
# ===========================================
# Refresh bridge wallet so it's caught up with blocks mined during funding.
# Without this, the watcher's get_transfers may not see incoming deposits.
log_info "Step 3: Refreshing bridge wallet before engine seeder..."
curl -sf "http://localhost:48770/json_rpc" \
    -d '{"jsonrpc":"2.0","id":"0","method":"refresh"}' >/dev/null 2>&1 || true
sleep 2

log_info "Running engine seeder (wrap → claim → LP)..."
log_info "  Bridge watcher will auto-mine blocks for confirmations"
cd "$ENGINE_REPO_PATH" && pnpm engine setup
echo ""

# ===========================================
# Step 4: Save Anvil snapshot
# ===========================================
log_info "Step 4: Saving Anvil snapshot..."
mkdir -p "$SNAPSHOT_DIR"
SNAPSHOT_FILE="$SNAPSHOT_DIR/post-seed.hex"
$CAST rpc anvil_dumpState --rpc-url "$RPC_URL" > "$SNAPSHOT_FILE" 2>/dev/null || true
if [ -s "$SNAPSHOT_FILE" ]; then
    log_success "Snapshot saved: $SNAPSHOT_FILE"
else
    log_warn "Snapshot save failed (non-fatal)"
fi

# ===========================================
# Step 5: Refresh wallets so balances show unlocked
# ===========================================
log_info "Step 5: Refreshing wallets..."
for PORT in 48769 48767 48768 48770 48771 48772; do
    curl -sf "http://localhost:$PORT/json_rpc" \
        -d '{"jsonrpc":"2.0","id":"0","method":"refresh"}' >/dev/null 2>&1 || true
done
sleep 2
log_success "Wallets refreshed"

echo ""
echo "==========================================="
log_success "Liquidity seeding complete (engine native)"
echo "==========================================="
echo ""
