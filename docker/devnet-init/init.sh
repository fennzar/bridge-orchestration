#!/bin/bash
# ===========================================
# DEVNET Init Container
# ===========================================
# One-shot bootstrap that replaces fresh-devnet's start.sh + setup-state.sh.
# Uses curl for all RPC calls (no zephyr-cli dependency).
#
# Expects these services to be healthy before running:
#   - fake-oracle (port 5555)
#   - zephyr-node1 (RPC 47767)
#   - zephyr-node2 (RPC 47867)
#   - wallet-gov (RPC 48769)
#   - wallet-miner (RPC 48767)
#   - wallet-test (RPC 48768)
#   - wallet-bridge (RPC 48770)

set -euo pipefail

# ===========================================
# Configuration
# ===========================================
NODE1_RPC="${NODE1_RPC:-http://zephyr-node1:47767}"
NODE2_RPC="${NODE2_RPC:-http://zephyr-node2:47867}"
GOV_WALLET_RPC="${GOV_WALLET_RPC:-http://wallet-gov:48769}"
MINER_WALLET_RPC="${MINER_WALLET_RPC:-http://wallet-miner:48767}"
TEST_WALLET_RPC="${TEST_WALLET_RPC:-http://wallet-test:48768}"
BRIDGE_WALLET_RPC="${BRIDGE_WALLET_RPC:-http://wallet-bridge:48770}"
ORACLE_URL="${ORACLE_URL:-http://fake-oracle:5555}"
CHECKPOINT_FILE="${CHECKPOINT_FILE:-/checkpoint/height}"

# Governance wallet keys (deterministic for DEVNET)
GOV_ADDRESS="ZPHSjqHRP2cPUoxHrVXe8K6rjdDdA9JF8WL549DrkDVtiYYbkfkJSvc4bQ6iXVb11Z3hcGETaNPgiMG5wu3fCPjviLk4Nu69oJy"
GOV_SPEND_KEY="dcf91a5b3e9913e0b78aa9460636f61ac9df37bbb003d795a555553214c83e09"
GOV_VIEW_KEY="0ad41f7f73ee411387fbcf722364db676022f08c54fa4bb4708b6eec8c6b1a00"

# Oracle price: $1.50 in atomic units (1e12)
DEFAULT_SPOT=1500000000000

# Mining
MINING_THREADS="${MINING_THREADS:-2}"

# ===========================================
# Helper Functions
# ===========================================
rpc_call() {
    local url="$1" method="$2" params="${3:-{}}"
    curl -sf --max-time 10 "${url}/json_rpc" \
        -H 'Content-Type: application/json' \
        -d "{\"jsonrpc\":\"2.0\",\"id\":\"0\",\"method\":\"${method}\",\"params\":${params}}"
}

rpc_other() {
    local url="$1" path="$2" data="${3:-{}}"
    curl -sf --max-time 10 "${url}/${path}" \
        -H 'Content-Type: application/json' \
        -d "${data}"
}

get_height() {
    rpc_call "$NODE1_RPC" "get_info" | jq -r '.result.height'
}

wait_for_height() {
    local target="$1"
    local current
    echo "  Waiting for height >= ${target}..."
    while true; do
        current=$(get_height 2>/dev/null || echo "0")
        if [ "$current" -ge "$target" ] 2>/dev/null; then
            echo "  Reached height ${current}"
            return
        fi
        sleep 2
    done
}

wait_blocks() {
    local blocks="${1:-10}"
    local current
    current=$(get_height)
    local target=$((current + blocks))
    echo "  Waiting ${blocks} blocks (current: ${current}, target: ${target})..."
    wait_for_height "$target"
}

get_wallet_address() {
    local wallet_rpc="$1"
    rpc_call "$wallet_rpc" "get_address" '{"account_index":0}' | jq -r '.result.address'
}

refresh_wallet() {
    local wallet_rpc="$1"
    rpc_call "$wallet_rpc" "refresh" '{}' >/dev/null 2>&1 || true
}

# Transfer ZPH between wallets
# Usage: transfer <from_wallet_rpc> <to_address> <amount_atomic>
transfer() {
    local from_rpc="$1" to_addr="$2" amount="$3" asset_type="${4:-ZPH}"
    refresh_wallet "$from_rpc"
    sleep 1

    local params
    params=$(cat <<JSON
{
    "destinations": [{"amount": ${amount}, "address": "${to_addr}"}],
    "source_asset": "${asset_type}",
    "destination_asset": "${asset_type}",
    "priority": 0,
    "ring_size": 2,
    "get_tx_key": true
}
JSON
)
    local result
    result=$(rpc_call "$from_rpc" "transfer" "$params")
    if echo "$result" | jq -e '.result.tx_hash' >/dev/null 2>&1; then
        echo "  TX: $(echo "$result" | jq -r '.result.tx_hash' | head -c 16)..."
    else
        echo "  WARNING: Transfer may have failed: $(echo "$result" | jq -r '.error.message // "unknown"')"
    fi
}

# Convert between asset types
# Usage: convert <wallet_rpc> <amount_atomic> <from_asset> <to_asset>
convert() {
    local wallet_rpc="$1" amount="$2" from_asset="$3" to_asset="$4"
    refresh_wallet "$wallet_rpc"
    sleep 1

    local params
    params=$(cat <<JSON
{
    "destinations": [{"amount": ${amount}, "address": ""}],
    "source_asset": "${from_asset}",
    "destination_asset": "${to_asset}",
    "priority": 0,
    "ring_size": 2,
    "get_tx_key": true
}
JSON
)
    # For conversions, dest address is self (empty string means self in wallet rpc)
    # Actually need to get own address first
    local self_addr
    self_addr=$(get_wallet_address "$wallet_rpc")
    params=$(cat <<JSON
{
    "destinations": [{"amount": ${amount}, "address": "${self_addr}"}],
    "source_asset": "${from_asset}",
    "destination_asset": "${to_asset}",
    "priority": 0,
    "ring_size": 2,
    "get_tx_key": true
}
JSON
)
    local result
    result=$(rpc_call "$wallet_rpc" "transfer" "$params")
    if echo "$result" | jq -e '.result.tx_hash' >/dev/null 2>&1; then
        echo "  TX: $(echo "$result" | jq -r '.result.tx_hash' | head -c 16)..."
    else
        echo "  WARNING: Convert may have failed: $(echo "$result" | jq -r '.error.message // "unknown"')"
    fi
}

# Atomic units: 1 ZEPH = 1e12 atomic
to_atomic() {
    echo "$1" | awk '{printf "%.0f", $1 * 1000000000000}'
}

echo "========================================="
echo "  DEVNET Init - Bootstrap Sequence"
echo "========================================="
echo ""

# ===========================================
# Step 1: Set oracle price
# ===========================================
echo "--- Step 1: Setting oracle price to \$1.50 ---"
curl -sf -X POST "${ORACLE_URL}/set-price" \
    -H 'Content-Type: application/json' \
    -d "{\"spot\": ${DEFAULT_SPOT}}" | jq -r '.status' || echo "WARNING: Oracle set-price failed"
echo ""

# ===========================================
# Step 2: Wait for node RPC readiness
# ===========================================
echo "--- Step 2: Waiting for node RPC ---"
for i in $(seq 1 60); do
    if rpc_call "$NODE1_RPC" "get_info" >/dev/null 2>&1; then
        echo "  Node1 RPC ready"
        break
    fi
    [ "$i" -eq 60 ] && { echo "ERROR: Node1 RPC not ready after 60s"; exit 1; }
    sleep 1
done
for i in $(seq 1 60); do
    if rpc_call "$NODE2_RPC" "get_info" >/dev/null 2>&1; then
        echo "  Node2 RPC ready"
        break
    fi
    [ "$i" -eq 60 ] && { echo "ERROR: Node2 RPC not ready after 60s"; exit 1; }
    sleep 1
done
echo ""

# ===========================================
# Step 3: Wait for wallet RPCs
# ===========================================
echo "--- Step 3: Waiting for wallet RPCs ---"
for wallet_name_rpc in "gov:${GOV_WALLET_RPC}" "miner:${MINER_WALLET_RPC}" "test:${TEST_WALLET_RPC}" "bridge:${BRIDGE_WALLET_RPC}"; do
    name="${wallet_name_rpc%%:*}"
    rpc="${wallet_name_rpc#*:}"
    for i in $(seq 1 30); do
        if rpc_call "$rpc" "get_version" >/dev/null 2>&1; then
            echo "  ${name} wallet RPC ready"
            break
        fi
        [ "$i" -eq 30 ] && { echo "ERROR: ${name} wallet RPC not ready after 30s"; exit 1; }
        sleep 1
    done
done
echo ""

# ===========================================
# Step 4: Restore governance wallet from keys
# ===========================================
echo "--- Step 4: Restoring governance wallet ---"
# Try open_wallet first (handles re-runs where wallet file already exists)
gov_open=$(rpc_call "$GOV_WALLET_RPC" "open_wallet" '{"filename":"gov","password":""}' 2>/dev/null)
if echo "$gov_open" | jq -e '.result' >/dev/null 2>&1; then
    echo "  Gov wallet: opened existing..."
else
    gov_result=$(rpc_call "$GOV_WALLET_RPC" "generate_from_keys" "{
        \"filename\": \"gov\",
        \"address\": \"${GOV_ADDRESS}\",
        \"spendkey\": \"${GOV_SPEND_KEY}\",
        \"viewkey\": \"${GOV_VIEW_KEY}\",
        \"password\": \"\",
        \"restore_height\": 0
    }")
    echo "  Gov wallet: $(echo "$gov_result" | jq -r '.result.address // "restored"' | head -c 20)..."
fi
echo ""

# ===========================================
# Step 5: Create miner and test wallets
# ===========================================
echo "--- Step 5: Creating miner, test, and bridge wallets ---"
# Try open first, create only if open fails
miner_open=$(rpc_call "$MINER_WALLET_RPC" "open_wallet" '{"filename":"miner","password":""}' 2>/dev/null)
if ! echo "$miner_open" | jq -e '.result' >/dev/null 2>&1; then
    rpc_call "$MINER_WALLET_RPC" "create_wallet" '{"filename":"miner","password":"","language":"English"}' >/dev/null 2>&1 || true
fi
sleep 1
test_open=$(rpc_call "$TEST_WALLET_RPC" "open_wallet" '{"filename":"test","password":""}' 2>/dev/null)
if ! echo "$test_open" | jq -e '.result' >/dev/null 2>&1; then
    rpc_call "$TEST_WALLET_RPC" "create_wallet" '{"filename":"test","password":"","language":"English"}' >/dev/null 2>&1 || true
fi
sleep 1
bridge_open=$(rpc_call "$BRIDGE_WALLET_RPC" "open_wallet" '{"filename":"bridge","password":""}' 2>/dev/null)
if ! echo "$bridge_open" | jq -e '.result' >/dev/null 2>&1; then
    rpc_call "$BRIDGE_WALLET_RPC" "create_wallet" '{"filename":"bridge","password":"","language":"English"}' >/dev/null 2>&1 || true
fi
sleep 1

MINER_ADDR=$(get_wallet_address "$MINER_WALLET_RPC")
TEST_ADDR=$(get_wallet_address "$TEST_WALLET_RPC")
BRIDGE_ADDR=$(get_wallet_address "$BRIDGE_WALLET_RPC")
echo "  Miner address:  ${MINER_ADDR:0:20}..."
echo "  Test address:   ${TEST_ADDR:0:20}..."
echo "  Bridge address: ${BRIDGE_ADDR:0:20}..."
echo ""

# ===========================================
# Step 6: Start mining
# ===========================================
echo "--- Step 6: Starting mining (${MINING_THREADS} threads) ---"
rpc_other "$NODE1_RPC" "start_mining" "{
    \"do_background_mining\": false,
    \"ignore_battery\": true,
    \"miner_address\": \"${MINER_ADDR}\",
    \"threads_count\": ${MINING_THREADS}
}" >/dev/null 2>&1 || true
echo "  Mining started on node1"
echo ""

# ===========================================
# Step 7: Wait for governance unlock (60 blocks)
# ===========================================
echo "--- Step 7: Waiting for block height >= 70 (governance unlock) ---"
wait_for_height 70
echo ""

# ===========================================
# Step 8: State setup - minting sequence
# ===========================================
echo "========================================="
echo "  State Setup - Minting Sequence"
echo "========================================="
echo ""
echo "Ring size is 2 for DEVNET. Sequential minting with waits."
echo ""

# Refresh gov wallet
refresh_wallet "$GOV_WALLET_RPC"
sleep 2

# Phase 1: Mint ZRS (3 rounds x 300,000 ZPH)
echo "--- Phase 1: Mint ZRS (3 x 300,000 ZPH -> ZRS) ---"
AMOUNT_300K=$(to_atomic 300000)
for i in 1 2 3; do
    echo "  ZRS mint ${i}/3:"
    convert "$GOV_WALLET_RPC" "$AMOUNT_300K" "ZPH" "ZRS"
    wait_blocks 12
done

echo ""
echo "--- Waiting for ZPH outputs to unlock ---"
wait_blocks 20

# Phase 2: Mint ZSD (3 rounds x 50,000 ZPH)
echo ""
echo "--- Phase 2: Mint ZSD (3 x 50,000 ZPH -> ZSD) ---"
AMOUNT_50K=$(to_atomic 50000)
for i in 1 2 3; do
    echo "  ZSD mint ${i}/3:"
    convert "$GOV_WALLET_RPC" "$AMOUNT_50K" "ZPH" "ZSD"
    wait_blocks 12
done

echo ""
echo "--- Waiting for ZSD outputs to unlock ---"
wait_blocks 20

# Phase 3: Mint ZYS (3 rounds x 25,000 ZSD)
echo ""
echo "--- Phase 3: Mint ZYS (3 x 25,000 ZSD -> ZYS) ---"
AMOUNT_25K=$(to_atomic 25000)
for i in 1 2 3; do
    echo "  ZYS mint ${i}/3:"
    convert "$GOV_WALLET_RPC" "$AMOUNT_25K" "ZSD" "ZYS"
    wait_blocks 12
done

echo ""
echo "--- Waiting for outputs to unlock ---"
wait_blocks 20

# Phase 4: Fund test and miner wallets
echo ""
echo "--- Phase 4: Fund test and miner wallets ---"
AMOUNT_10K=$(to_atomic 10000)
AMOUNT_5K=$(to_atomic 5000)
for i in 1 2 3; do
    echo "  ZPH send ${i}/3: 10,000 -> test"
    transfer "$GOV_WALLET_RPC" "$TEST_ADDR" "$AMOUNT_10K"
    wait_blocks 12
done
echo "  ZSD send: 5,000 -> test"
transfer "$GOV_WALLET_RPC" "$TEST_ADDR" "$AMOUNT_5K" "ZSD"
wait_blocks 12
echo "  ZPH send: 5,000 -> miner"
transfer "$GOV_WALLET_RPC" "$MINER_ADDR" "$AMOUNT_5K"
wait_blocks 12

# Phase 5: Ring diversity (self-sends)
echo ""
echo "--- Phase 5: Ring diversity (self-sends) ---"
GOV_ADDR=$(get_wallet_address "$GOV_WALLET_RPC")
AMOUNT_1K=$(to_atomic 1000)
AMOUNT_500=$(to_atomic 500)
for i in 1 2 3 4; do
    echo "  ZPH self-send ${i}/4: 1,000"
    transfer "$GOV_WALLET_RPC" "$GOV_ADDR" "$AMOUNT_1K"
    wait_blocks 10
done
for i in 1 2; do
    echo "  ZSD self-send ${i}/2: 500"
    transfer "$GOV_WALLET_RPC" "$GOV_ADDR" "$AMOUNT_500" "ZSD"
    wait_blocks 10
done

echo ""
echo "--- Final wait for all outputs to unlock ---"
wait_blocks 20

# ===========================================
# Step 9: Save checkpoint
# ===========================================
echo ""
echo "--- Step 9: Stopping mining ---"
rpc_other "$NODE1_RPC" "stop_mining" '{}' >/dev/null 2>&1 || true
echo "  Mining stopped"

echo ""
echo "--- Step 10: Saving checkpoint ---"
FINAL_HEIGHT=$(get_height)
mkdir -p "$(dirname "$CHECKPOINT_FILE")"
echo "$FINAL_HEIGHT" > "$CHECKPOINT_FILE"
echo "  Checkpoint saved at height: ${FINAL_HEIGHT}"

echo ""
echo "========================================="
echo "  DEVNET Init Complete!"
echo "  Chain height: ${FINAL_HEIGHT}"
echo "  Mining: stopped (use dashboard or CLI to start)"
echo "========================================="
