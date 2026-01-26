# Zephyr Testing Tips

## Known Issues

### Daemon Busy Error
**Issue:** Transfers fail with "daemon is busy" error after starting/stopping mining.

**Symptoms:**
- Wallet RPC calls return: `{"code": -3, "message": "daemon is busy"}`
- Occurs even after mining is stopped
- Persists until daemon is restarted

**Solution:** Restart the zephyrd daemon: `docker compose restart zephyr-node1 zephyr-node2` and wait ~15 seconds.

**Prevention:**
- Use separate daemons for mining (node1) and wallets (node2)
- Point mining wallet to node1 (DEVNET port 47767; mainnet-fork port 48081 is DEPRECATED)
- Point all other wallets to node2 (DEVNET port 47867; mainnet-fork port 17867 is DEPRECATED)
- This prevents mining activity from blocking wallet operations

### Mining Requires `miner_address`

**Issue:** `start_mining` returns `"Failed, wrong address"`.

**Cause:** The `start_mining` daemon REST endpoint requires `miner_address` in the request body.

**Solution:**
```bash
# Get address from mining wallet first
# DEVNET port 48767 (mainnet-fork port 17776 is DEPRECATED)
MINER_ADDR=$(curl -s http://127.0.0.1:48767/json_rpc \
  -d '{"jsonrpc":"2.0","id":"0","method":"get_address"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['address'])")

# Then start mining with the address
# DEVNET port 47867 (mainnet-fork port 17867 is DEPRECATED)
curl -s http://127.0.0.1:47867/start_mining \
  -H 'Content-Type: application/json' \
  -d "{\"do_background_mining\":false,\"threads_count\":4,\"miner_address\":\"$MINER_ADDR\"}"
```

**Note:** `start_mining` and `stop_mining` are daemon REST endpoints (DEVNET port 47867 or 47767), not wallet JSON-RPC endpoints (DEVNET port 48767).

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

**Test chain note:** The test chain (forked at block 697605) has a reserve ratio of ~2.47, which means ZPH→ZSD conversions will fail with a reserve ratio error. ZPH→ZRS conversions appear to succeed on-chain (tx confirms) but the wallet may not detect the resulting ZRS outputs even after `rescan_blockchain`. This limits multi-asset bridge testing to assets the test user wallet already holds.

## Querying Wallet Balances

**Important:** `get_balance` without `asset_type` parameter only returns ZPH.

To query all assets:
```bash
# DEVNET port 48767 (mainnet-fork port 17776 is DEPRECATED)
for asset in ZPH ZSD ZRS ZYS; do
  curl -s http://localhost:48767/json_rpc \
    -d "{\"jsonrpc\":\"2.0\",\"id\":\"0\",\"method\":\"get_balance\",\"params\":{\"asset_type\":\"$asset\"}}" \
    -H 'Content-Type: application/json' | jq '.result'
done
```

## Verifying Conversions via Daemon

Conversion transactions can be verified on the daemon using `get_transactions` with `decode_as_json: true`:

```bash
# DEVNET port 47767 (mainnet-fork port 48081 is DEPRECATED)
curl -s http://localhost:47767/get_transactions \
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
