#!/bin/bash
# ===========================================
# Start mining via node2 (fallback)
# ===========================================
# After pop_blocks, node1 can get stuck with synchronized=False.
# Mining a few blocks on node2 forces node1 to resync and become
# synchronized, after which normal mining via node1 can resume.
#
# This script:
# 1. Gets the miner wallet address
# 2. Starts mining on node2 (port 47867)
# 3. Waits for node1 to sync (synchronized=True)
# 4. Stops mining on node2
# 5. Starts mining on node1 (normal path)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_DIR="$(dirname "$SCRIPT_DIR")"

source "$SCRIPT_DIR/lib/env.sh"
load_env "$ORCH_DIR/.env" 2>/dev/null || true

ZEPHYR_CLI="${ZEPHYR_REPO_PATH:-$(dirname "$ORCH_DIR")/zephyr}/tools/zephyr-cli/cli"
NODE1_RPC="http://127.0.0.1:47767"
NODE2_RPC="http://127.0.0.1:47867"
MINER_WALLET_RPC="http://127.0.0.1:48767"

# Get miner address
MINER_ADDR=$(curl -sf "$MINER_WALLET_RPC/json_rpc" \
    -d '{"jsonrpc":"2.0","id":"0","method":"get_address","params":{"account_index":0}}' \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['result']['address'])")

if [ -z "$MINER_ADDR" ]; then
    echo "Could not get miner address"
    exit 1
fi

# Start mining on node2
RESULT=$(curl -sf "$NODE2_RPC/start_mining" \
    -d "{\"do_background_mining\":false,\"ignore_battery\":true,\"miner_address\":\"$MINER_ADDR\",\"threads_count\":2}" \
    | python3 -c "import json,sys; print(json.load(sys.stdin).get('status','FAIL'))")

if [ "$RESULT" != "OK" ]; then
    echo "Failed to start mining on node2: $RESULT"
    exit 1
fi

# Wait for node1 to sync (max 30s)
for i in $(seq 1 30); do
    SYNCED=$(curl -sf "$NODE1_RPC/json_rpc" \
        -d '{"jsonrpc":"2.0","id":"0","method":"get_info"}' \
        | python3 -c "import json,sys; print(json.load(sys.stdin)['result'].get('synchronized',False))" 2>/dev/null || echo "False")
    if [ "$SYNCED" = "True" ]; then
        break
    fi
    sleep 1
done

# Stop mining on node2
curl -sf "$NODE2_RPC/stop_mining" -d '{}' >/dev/null 2>&1 || true

# Now start mining on node1 (should work since it's synchronized)
"$ZEPHYR_CLI" mine start --threads 2 2>/dev/null || true
