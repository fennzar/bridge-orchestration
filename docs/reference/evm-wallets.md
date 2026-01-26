# EVM Wallet Setup and Testing

> **LOCAL DEV ONLY.** All keys and addresses below are for local Anvil testing (Chain ID 31337). Never use them on mainnet or with real funds.

Guide for EVM wallet usage on Anvil. This project uses a **custom mnemonic** (not the default Foundry one) — see account details below.

---

## Wallet Tools

| Tool | Use Case | Setup |
|------|----------|-------|
| **Cast CLI** | Scripting, automation, CI | Installed with Foundry (`foundryup`) |
| **MetaMask** | Browser UI testing, dApp interaction | See [metamask.md](./metamask.md) |


---

## Anvil Accounts (Custom Mnemonic)

This project uses a project-specific mnemonic (`EVM_DEV_MNEMONIC` in `.env`). The accounts below are derived from it.

**Do NOT use the default Foundry mnemonic** (`test test test...junk`) — it produces different addresses.

### Key Accounts

| # | Role | Address | Private Key |
|---|------|---------|-------------|
| 0 | Deployer | `0x8a87522ff7a811Af2E1EDA0FB3D99c8F5400Cf4B` | `0x860875f05874e1ac2207f147a7a3e2a13d66520936cb598528e9104f2d5ec990` |
| 1 | Bridge Signer | `0x8273E2C64415faCD40Db58181575B6f8f1337e22` | `0xdad112823784d70852482c06b20e6fae3f9a4b23fcb985930df6a57d17d31a27` |

20 accounts total are created by Anvil, each pre-funded with 10,000 ETH.

### MetaMask Test Wallet (Separate Seed)

For UI/browser testing, there's a separate MetaMask test wallet with its own seed phrase. See [metamask.md](./metamask.md) for:
- Seed phrase, password, 3 derived accounts
- Anvil network config
- Funding commands

---

## Cast CLI Setup

```bash
# Verify installation
cast --version

# Set default RPC
export ETH_RPC_URL=http://localhost:8545

# Set account aliases
export DEPLOYER_ADDR=0x8a87522ff7a811Af2E1EDA0FB3D99c8F5400Cf4B
export DEPLOYER_KEY=0x860875f05874e1ac2207f147a7a3e2a13d66520936cb598528e9104f2d5ec990
export SIGNER_ADDR=0x8273E2C64415faCD40Db58181575B6f8f1337e22
export SIGNER_KEY=0xdad112823784d70852482c06b20e6fae3f9a4b23fcb985930df6a57d17d31a27
```

---

## Verify Anvil

```bash
# Check Anvil is running
cast block-number --rpc-url http://localhost:8545

# Check deployer balance
cast balance $DEPLOYER_ADDR --rpc-url http://localhost:8545
# Expected: 10000000000000000000000 (10000 ETH in wei)

# Check chain ID
cast chain-id --rpc-url http://localhost:8545
# Expected: 31337
```

---

## Token Operations

### Prerequisites

- Anvil running: `docker compose up -d anvil`
- Contracts deployed: `./scripts/deploy-contracts.sh`
- Addresses synced: `./scripts/sync-env.sh`

### Get Contract Addresses

```bash
cat config/addresses.local.json | jq '.tokens'
```

### Check Token Balance

```bash
WZEPH=$(cat config/addresses.local.json | jq -r '.tokens.wZEPH')
cast call $WZEPH "balanceOf(address)(uint256)" $DEPLOYER_ADDR --rpc-url http://localhost:8545
```

### Transfer Tokens

```bash
# Transfer 1 wZEPH (12 decimals) from deployer to signer
cast send $WZEPH "transfer(address,uint256)" $SIGNER_ADDR 1000000000000 \
  --private-key $DEPLOYER_KEY --rpc-url http://localhost:8545
```

### Approve + TransferFrom

```bash
# Approve signer to spend deployer's tokens
cast send $WZEPH "approve(address,uint256)" $SIGNER_ADDR 1000000000000 \
  --private-key $DEPLOYER_KEY --rpc-url http://localhost:8545

# Check allowance
cast call $WZEPH "allowance(address,address)(uint256)" $DEPLOYER_ADDR $SIGNER_ADDR --rpc-url http://localhost:8545
```

### Burn Tokens (for Unwrap)

```bash
cast send $WZEPH "burn(uint256)" 1000000000000 \
  --private-key $DEPLOYER_KEY --rpc-url http://localhost:8545
```

### Send ETH

```bash
cast send $SIGNER_ADDR --value 1ether --private-key $DEPLOYER_KEY --rpc-url http://localhost:8545
```

---

## Troubleshooting

### Anvil Not Responding
```bash
docker ps | grep anvil
docker compose restart anvil
```

### Balance Shows 0
Likely using wrong account addresses. This project uses a custom mnemonic — verify you're checking the correct addresses (see table above).

### "Nonce Too Low"
Common after Anvil reset. Check current nonce:
```bash
cast nonce $DEPLOYER_ADDR --rpc-url http://localhost:8545
```

### Contracts Not Found
Redeploy and sync:
```bash
./scripts/deploy-contracts.sh
./scripts/sync-env.sh
```

### Full Reset
```bash
docker compose down anvil
docker compose up -d anvil
./scripts/deploy-contracts.sh
./scripts/sync-env.sh
```

---

## Security

- All keys and addresses in this document are for **local testing only** (Anvil, Chain ID 31337)
- NEVER use these keys on mainnet or with real funds
- Keep private keys in env variables, not in code
- Use different keys for different environments (local, Sepolia, mainnet)
