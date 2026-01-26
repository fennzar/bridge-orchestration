# MetaMask Test Wallet Setup

> **LOCAL DEV ONLY.** All keys, seeds, and passwords below are for local Anvil testing (Chain ID 31337). Never use them on mainnet or with real funds.

Test wallet for bridge E2E testing.

---

## Test Wallet

**Seed Phrase:**
```
maid cushion uncover wheel liquid swear olympic cactus radar aunt birth aunt
```

**Password:** `password`

**Accounts (HD derivation path m/44'/60'/0'/0/n):**

| # | Name | Address | Use Case |
|---|------|---------|----------|
| 0 | Account 1 | `0xbF152846f1e7e0f8181A106b593779A853aAdA0b` | Primary test user |
| 1 | Account 2 | `0xfD5dee1B34445B8DCE9A207d4d62ba2B2a9D6641` | Secondary user / recipient |
| 2 | Account 3 | `0x2A06Fb4111856c8DB57189EC7d89395511C393AB` | Multi-user testing |

---

## Network: Anvil Local

```
Network Name: Anvil Local
RPC URL: http://localhost:8545
Chain ID: 31337
Currency Symbol: ETH
```

---

## Browser Profile

MetaMask state is persisted in a persistent Chrome profile (see `.env.playwright` for path).

This profile has MetaMask installed, the wallet imported, all 3 accounts created, and the Anvil Local network configured.

### Launching Chrome with MetaMask

```bash
# Start Anvil (if not already running)
docker compose up -d anvil

# Launch Chrome with the MetaMask profile (CDP for automation)
google-chrome-stable \
  --remote-debugging-port=9222 \
  --user-data-dir=$CHROME_PROFILE_DIR \
  --no-first-run \
  --no-default-browser-check \
  about:blank &
```

### Funding Test Accounts

The test wallet accounts start with 0 ETH. Fund them from the Anvil deployer:

```bash
FUNDER_KEY="0x860875f05874e1ac2207f147a7a3e2a13d66520936cb598528e9104f2d5ec990"

cast send --private-key $FUNDER_KEY --rpc-url http://localhost:8545 --value 100ether 0xbF152846f1e7e0f8181A106b593779A853aAdA0b
cast send --private-key $FUNDER_KEY --rpc-url http://localhost:8545 --value 100ether 0xfD5dee1B34445B8DCE9A207d4d62ba2B2a9D6641
cast send --private-key $FUNDER_KEY --rpc-url http://localhost:8545 --value 100ether 0x2A06Fb4111856c8DB57189EC7d89395511C393AB
```

---

## Anvil Deployer Accounts

These are the Anvil-funded accounts (from the bridge stack mnemonic). Use them for contract deployment and funding test wallets — **not** for simulating user interactions.

| # | Address | Private Key |
|---|---------|-------------|
| 0 (Deployer) | `0x8a87522ff7a811Af2E1EDA0FB3d99c8F5400Cf4B` | `0x860875f05874e1ac2207f147a7a3e2a13d66520936cb598528e9104f2d5ec990` |
| 1 (Test User) | `0x8273E2C64415faCD40Db58181575B6f8f1337e22` | `0xdad112823784d70852482c06b20e6fae3f9a4b23fcb985930df6a57d17d31a27` |

**Note:** These are from the bridge stack's EVM mnemonic, separate from the MetaMask test wallet above.

---

## Security Note

All keys and seed phrases in this document are for **local testing only** on Anvil (Chain ID 31337). Never use them on mainnet or with real funds.
