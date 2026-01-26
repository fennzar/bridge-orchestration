#!/bin/bash
set -euo pipefail

# ===========================================
# Fund Test Wallets (DEVNET)
# ===========================================
# Transfers funds from gov wallet to test/miner wallets using zephyr-cli.
# Supports all Zephyr asset types.
#
# Usage:
#   ./scripts/fund-wallets.sh                    # Default: 1000 ZPH to test wallet
#   ./scripts/fund-wallets.sh test 500           # 500 ZPH to test
#   ./scripts/fund-wallets.sh test 100 ZSD       # 100 ZSD to test
#   ./scripts/fund-wallets.sh miner 200 ZRS      # 200 ZRS to miner
#   ./scripts/fund-wallets.sh --balances         # Show all wallet balances

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SCRIPT_DIR/lib/devnet.sh"
resolve_fresh_devnet
require_zephyr_cli

# Show balances
if [[ "${1:-}" == "--balances" || "${1:-}" == "-b" ]]; then
    exec "$ZEPHYR_CLI" balances
fi

# Help
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
    echo "Usage: $0 [target_wallet] [amount] [asset]"
    echo ""
    echo "Transfer funds from gov wallet to a named wallet."
    echo ""
    echo "Arguments:"
    echo "  target_wallet  Destination wallet: test, miner (default: test)"
    echo "  amount         Amount to send (default: 1000)"
    echo "  asset          Asset type: ZPH, ZSD, ZRS, ZYS (default: ZPH)"
    echo ""
    echo "Options:"
    echo "  --balances, -b  Show all wallet balances"
    echo "  -h, --help      Show this help"
    echo ""
    echo "Examples:"
    echo "  $0                      # Send 1000 ZPH to test wallet"
    echo "  $0 test 500             # Send 500 ZPH to test wallet"
    echo "  $0 test 100 ZSD         # Send 100 ZSD to test wallet"
    echo "  $0 miner 200 ZRS        # Send 200 ZRS to miner wallet"
    echo ""
    echo "Show balances first:"
    echo "  $0 --balances"
    exit 0
fi

TARGET="${1:-test}"
AMOUNT="${2:-1000}"
ASSET="${3:-ZPH}"

echo "Sending $AMOUNT $ASSET: gov -> $TARGET"
echo ""
"$ZEPHYR_CLI" send gov "$TARGET" "$AMOUNT" "$ASSET"
echo ""
echo "Done. Check balances with: $0 --balances"
