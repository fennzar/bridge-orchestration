# Zephyr Reference

> **Troubleshooting:** For daemon busy errors, mining issues, and wallet balance problems, see **[troubleshooting.md](../troubleshooting.md#zephyr-daemon--wallets)**.

## Asset Conversion Syntax

Asset conversions use the `transfer` method with `source_asset` and `destination_asset` parameters:

```json
{
  "method": "transfer",
  "params": {
    "destinations": [{"address": "...", "amount": 50000000000000}],
    "source_asset": "ZPH",
    "destination_asset": "ZRS"
  }
}
```

**Important:** Parameters are `source_asset`/`destination_asset`, NOT `source`/`dest`.

## Conversion Requirements

| Conversion | Reserve Ratio | Status | Notes |
|------------|---------------|--------|-------|
| ZPH → ZSD | ≥ 4.0 | Requires high ratio | Mint stable |
| ZPH → ZRS | None | Always allowed | Mint reserve |
| ZSD → ZPH | None | Always allowed | Redeem stable |
| ZRS → ZPH | ≥ 2.0 | Requires minimum | Redeem reserve |
| ZSD → ZYS | None | Always allowed | Mint yield |
| ZYS → ZSD | None | Always allowed | Redeem yield |

## Querying Wallet Balances

**Important:** `get_balance` without `all_assets: true` only returns ZPH. Use `all_assets: true` or query per-asset:

```bash
curl -s http://127.0.0.1:48767/json_rpc \
  -d '{"jsonrpc":"2.0","id":"0","method":"get_balance","params":{"all_assets":true}}' \
  -H 'Content-Type: application/json' | jq '.result.balances'
```

## Verifying Conversions via Daemon

Conversion transactions can be verified using `get_transactions` with `decode_as_json: true`:

```bash
curl -s http://127.0.0.1:47767/get_transactions \
  -d '{"txs_hashes":["<txid>"],"decode_as_json":true}' \
  -H 'Content-Type: application/json' | jq -r '.txs[0].as_json' | jq '.'
```

Look for these fields:
- `amount_burnt`: Source asset amount (atomic units)
- `amount_minted`: Destination asset amount (atomic units)
- `pricing_record_height`: Block height of pricing data used

Regular transfers show `amount_burnt: 0` and `amount_minted: 0`.

## Wallet File Structure

Wallet files are stored in `$ROOT/zephyr-wallets/`:

Each wallet has two files:
- `.keys` file (~1.7KB): Private keys only
- Cache file (~22-23MB): Blockchain sync data and transaction history

Example:
- `localmining.keys` - Keys for mining wallet
- `localmining` - Mining wallet cache (synced to test chain)

Keys-only wallets (like `fennytestbridge.keys`) will create a new cache file when started, syncing from genesis or restore height.

## Asset Types

- **ZPH**: Native Zephyr (privacy coin)
- **ZSD**: Zephyr Stable Dollar (stablecoin pegged to USD)
- **ZRS**: Zephyr Reserve Share (volatile reserve asset)
- **ZYS**: Zephyr Yield Share (yield-bearing stablecoin)
