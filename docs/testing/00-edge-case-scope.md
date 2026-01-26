# Edge-Case Test Scope (ZB Catalog)

Master scope index for the 138 ZB edge-case tests integrated across the testing docs.

## Integrated Locations

| Doc | Integrated Categories |
|---|---|
| `docs/testing/02-infra-checklist.md` | `ZB-CONF` |
| `docs/testing/03-bridge-scenarios.md` | `ZB-SEC`, `ZB-SC`, `ZB-CONC`, `ZB-REC`, `ZB-CONS`, `ZB-ASSET`, `ZB-TIME`, `ZB-PRIV` |
| `docs/testing/04-full-stack-scenarios.md` | `ZB-WATCH`, `ZB-DEX`, `ZB-FE` |
| `docs/testing/05-devnet-scenarios.md` | `ZB-RR`, `ZB-LOAD` |
| `docs/testing/06-engine-strategies.md` | Strategy-adjacent edge validations (`ZB-RR-007`, `ZB-RR-008`, `ZB-TIME-008`, etc.) |

## Runner

Use the L5 runner to lint, plan, and execute the catalog workflow:

```bash
# Full logical pass (summary + lint + execution plan)
./scripts/run-l5-tests.py

# List all P0 tests
./scripts/run-l5-tests.py --list --priority P0

# Browser lane preflight (MetaMask/CDP prerequisites)
./scripts/run-l5-tests.py --browser-preflight

# Execute automated checks and write report
./scripts/run-l5-tests.py --execute --report-json .l5-execution-report.json

# Execute by sublevel
./scripts/run-l5-tests.py --execute --sublevel L5.1 --verbose  # Security & Contracts
./scripts/run-l5-tests.py --execute --sublevel L5.2 --verbose  # Runtime & Consistency
./scripts/run-l5-tests.py --execute --sublevel L5.3 --verbose  # Infra & Watchers
./scripts/run-l5-tests.py --execute --sublevel L5.4 --verbose  # Asset & DEX
./scripts/run-l5-tests.py --execute --sublevel L5.5 --verbose  # Privacy & Load
./scripts/run-l5-tests.py --execute --sublevel L5.6 --verbose  # Frontend

# Execute by category
./scripts/run-l5-tests.py --execute --category SEC --verbose
./scripts/run-l5-tests.py --execute --category FE --verbose
```

See [08-edge-framework.md](./08-edge-framework.md) for the full framework.

## Sublevel Grouping

| Sublevel | Name | Categories | Tests |
|----------|------|------------|-------|
| L5.1 | Security & Contracts | SEC + SC | 24 |
| L5.2 | Runtime & Consistency | CONS + RR + CONC | 28 |
| L5.3 | Infra & Watchers | WATCH + CONF + REC | 32 |
| L5.4 | Asset & DEX | ASSET + DEX | 20 |
| L5.5 | Privacy & Load | PRIV + LOAD + TIME | 22 |
| L5.6 | Frontend | FE | 12 |

## Status Legend

- `SCOPED-READY`: already represented in current docs and can be run now.
- `SCOPED-EXPAND`: related coverage exists; add explicit edge/failure assertions.
- `SCOPED-TBC`: new scenario requiring additional runbook guidance or harness work.

## Coverage Snapshot

| Total | SCOPED-READY | SCOPED-EXPAND | SCOPED-TBC |
|---:|---:|---:|---:|
| 138 | 77 | 27 | 34 |

## Category Summary

| Category | Tests | Primary Doc |
|---|---:|---|
| Bridge Security (12) | 12 | `docs/testing/03-bridge-scenarios.md` |
| Smart Contract Edge Cases (12) | 12 | `docs/testing/03-bridge-scenarios.md` |
| Concurrency & Race Conditions (10) | 10 | `docs/testing/03-bridge-scenarios.md` |
| Failure Recovery (10) | 10 | `docs/testing/03-bridge-scenarios.md` |
| Data Consistency (10) | 10 | `docs/testing/03-bridge-scenarios.md` |
| RR Mode Boundaries (8) | 8 | `docs/testing/05-devnet-scenarios.md` |
| Watcher Reliability (12) | 12 | `docs/testing/04-full-stack-scenarios.md` |
| Multi-Asset Interactions (10) | 10 | `docs/testing/03-bridge-scenarios.md` |
| DEX Edge Cases (10) | 10 | `docs/testing/04-full-stack-scenarios.md` |
| Timeout & Deadline Handling (8) | 8 | `docs/testing/03-bridge-scenarios.md` |
| Configuration Errors (10) | 10 | `docs/testing/02-infra-checklist.md` |
| Load & Stress (8) | 8 | `docs/testing/05-devnet-scenarios.md` |
| Privacy Leaks (6) | 6 | `docs/testing/03-bridge-scenarios.md` |
| Frontend Edge Cases (12) | 12 | `docs/testing/04-full-stack-scenarios.md` |

## 1. Bridge Security (12)

| ID | Test | Priority | Severity | Status | Primary Doc | Next Action |
|---|---|---|---|---|---|---|
| `ZB-SEC-001` | Reject forged claim signature | P0 | Critical | `SCOPED-EXPAND` | `docs/testing/03-bridge-scenarios.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-SEC-002` | Reject claim signed for different to address | P0 | Critical | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-SEC-003` | Reject claim on wrong chainId (domain mismatch) | P1 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-SEC-004` | Prevent duplicate claim after wallet rescan/replay ingestion | P0 | High | `SCOPED-EXPAND` | `docs/testing/03-bridge-scenarios.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-SEC-005` | Multi-destination Zephyr tx: ensure no funds lost due to txHash-only idempotency | P0 | Critical | `SCOPED-TBC` | `docs/testing/03-bridge-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-SEC-006` | Same Zephyr tx includes multiple asset types: ensure no cross-asset "txHash lockout" | P0 | Critical | `SCOPED-TBC` | `docs/testing/03-bridge-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-SEC-007` | Unwrap payout must bind to burn event fields, not "prepare" fields | P0 | Critical | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-SEC-008` | Duplicate burn event ingestion must not double-send Zephyr funds | P0 | Critical | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-SEC-009` | Validate MINTER_ROLE not accidentally granted broadly (testnet guardrail) | P1 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-SEC-010` | Oracle signer rotation does not strand existing deposits | P0 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-SEC-011` | Admin endpoints must not be callable without token (avoid accidental tampering) | P2 | Medium | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Keep as regression in current suite. |
| `ZB-SEC-012` | Claim API must not leak signatures for other addresses | P1 | Medium | `SCOPED-EXPAND` | `docs/testing/03-bridge-scenarios.md` | Extend existing scenario with explicit edge assertions. |

## 2. Smart Contract Edge Cases (12)

| ID | Test | Priority | Severity | Status | Primary Doc | Next Action |
|---|---|---|---|---|---|---|
| `ZB-SC-001` | claimWithSignature and claimWithSig equivalence | P0 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-SC-002` | Deadline boundary conditions | P1 | Medium | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-SC-003` | Reject amount = 0 claim | P1 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-SC-004` | Reject burnWithData(amount=0) | P1 | Medium | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-SC-005` | Nonce replay protection exactness | P0 | Critical | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Keep as regression in current suite. |
| `ZB-SC-006` | Nonce uniqueness across tokens (should be per-token) | P1 | Medium | `SCOPED-TBC` | `docs/testing/03-bridge-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-SC-007` | ECDSA malleability test (high-s signatures) | P2 | Medium | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-SC-008` | Event correctness: MintedFromZephyr must include correct zephyrTxHash | P0 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-SC-009` | setOracleSigner access control | P2 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-SC-010` | Decimals fixed at 12 and matches bridge arithmetic | P0 | Critical | `SCOPED-EXPAND` | `docs/testing/03-bridge-scenarios.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-SC-011` | usedZephyrTx set only on success | P0 | Critical | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-SC-012` | mintFromZephyr respects replay protection | P1 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |

## 3. Concurrency & Race Conditions (10)

| ID | Test | Priority | Severity | Status | Primary Doc | Next Action |
|---|---|---|---|---|---|---|
| `ZB-CONC-001` | /bridge/address idempotency under concurrent requests (same EVM) | P0 | High | `SCOPED-TBC` | `docs/testing/03-bridge-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-CONC-002` | /bridge/address uniqueness under concurrent different EVMs | P0 | Critical | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-CONC-003` | Case normalization collision (EIP-55 vs lowercase) | P0 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-CONC-004` | Deposit arrives before /bridge/address response is stored | P0 | Critical | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-CONC-005` | Two browser tabs claim same voucher simultaneously | P0 | Critical | `SCOPED-EXPAND` | `docs/testing/03-bridge-scenarios.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-CONC-006` | Multiple unwrap prepares with same params (dedupe vs uniqueness) | P0 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-CONC-007` | Unwrap burn happens before prepare reconciliation completes | P0 | Critical | `SCOPED-TBC` | `docs/testing/03-bridge-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-CONC-008` | Two bridge instances running (lock contention) | P0 | Critical | `SCOPED-TBC` | `docs/testing/03-bridge-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-CONC-009` | Dev-reset while queues active | P0 | High | `SCOPED-TBC` | `docs/testing/03-bridge-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-CONC-010` | Engine evaluation concurrent with reserve mode change | P0 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |

## 4. Failure Recovery (10)

| ID | Test | Priority | Severity | Status | Primary Doc | Next Action |
|---|---|---|---|---|---|---|
| `ZB-REC-001` | Bridge API crash after ZephyrIncoming created but before Claim queued | P0 | High | `SCOPED-TBC` | `docs/testing/03-bridge-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-REC-002` | watcher-zephyr crash mid-poll | P0 | High | `SCOPED-EXPAND` | `docs/testing/03-bridge-scenarios.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-REC-003` | watcher-evm crash after Burned log seen but before payout sent | P0 | Critical | `SCOPED-EXPAND` | `docs/testing/03-bridge-scenarios.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-REC-004` | Crash during Zephyr transfer submission (unknown tx state) | P0 | Critical | `SCOPED-TBC` | `docs/testing/03-bridge-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-REC-005` | Wallet RPC unreachable (temporary) | P0 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-REC-006` | Primary daemon down; wallets failover behavior | P1 | High | `SCOPED-TBC` | `docs/testing/03-bridge-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-REC-007` | Postgres restart mid-processing | P0 | High | `SCOPED-TBC` | `docs/testing/03-bridge-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-REC-008` | Redis restart (cache + state streaming) | P1 | Medium | `SCOPED-TBC` | `docs/testing/03-bridge-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-REC-009` | Anvil WS disconnect + reconnect | P0 | Critical | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-REC-010` | Engine watchers restart: cursor-based recovery | P0 | High | `SCOPED-EXPAND` | `docs/testing/03-bridge-scenarios.md` | Extend existing scenario with explicit edge assertions. |

## 5. Data Consistency (10)

| ID | Test | Priority | Severity | Status | Primary Doc | Next Action |
|---|---|---|---|---|---|---|
| `ZB-CONS-001` | DB claim state must match on-chain ERC20 balances | P0 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Keep as regression in current suite. |
| `ZB-CONS-002` | TokenSupply cache correctness after mint/burn bursts | P1 | Medium | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-CONS-003` | Unwrap DB state must match ZephyrOutgoing wallet history | P0 | Critical | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Keep as regression in current suite. |
| `ZB-CONS-004` | Exactly-once ZephyrIncoming ingestion across rescans | P0 | High | `SCOPED-EXPAND` | `docs/testing/03-bridge-scenarios.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-CONS-005` | Confirmations monotonicity | P1 | Medium | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-CONS-006` | Out-of-order status transitions are rejected | P0 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-CONS-007` | Unwrap.id = txHash:logIndex uniqueness under same-tx multiple events | P1 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-CONS-008` | BridgeAccount uniqueness constraints | P0 | Critical | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-CONS-009` | SystemState + Lock TTL correctness | P0 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-CONS-010` | Engine DB snapshots align with current on-chain pool state | P0 | High | `SCOPED-EXPAND` | `docs/testing/03-bridge-scenarios.md` | Extend existing scenario with explicit edge assertions. |

## 6. RR Mode Boundaries (8)

| ID | Test | Priority | Severity | Status | Primary Doc | Next Action |
|---|---|---|---|---|---|---|
| `ZB-RR-001` | Exact boundary at RR = 400% (mode switch correctness) | P0 | High | `SCOPED-EXPAND` | `docs/testing/05-devnet-scenarios.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-RR-002` | RR just below 400% (399.99%) | P0 | High | `SCOPED-READY` | `docs/testing/05-devnet-scenarios.md` | Automated check implemented. |
| `ZB-RR-003` | RR just above 800% (ZRS mint constraints) | P1 | Medium | `SCOPED-READY` | `docs/testing/05-devnet-scenarios.md` | Automated check implemented. |
| `ZB-RR-004` | RR boundary at 200% and 199.99% | P0 | High | `SCOPED-READY` | `docs/testing/05-devnet-scenarios.md` | Keep as regression in current suite. |
| `ZB-RR-005` | Mode flapping stress (rapid oscillation) | P0 | High | `SCOPED-READY` | `docs/testing/05-devnet-scenarios.md` | Keep as regression in current suite. |
| `ZB-RR-006` | Mid-operation mode change during unwrap/wrap | P0 | Critical | `SCOPED-TBC` | `docs/testing/05-devnet-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-RR-007` | Engine runtime endpoint correctness for all op combinations | P0 | High | `SCOPED-READY` | `docs/testing/05-devnet-scenarios.md` | Keep as regression in current suite. |
| `ZB-RR-008` | Stale reserve snapshot handling | P0 | High | `SCOPED-READY` | `docs/testing/05-devnet-scenarios.md` | Automated check implemented. |

## 7. Watcher Reliability (12)

| ID | Test | Priority | Severity | Status | Primary Doc | Next Action |
|---|---|---|---|---|---|---|
| `ZB-WATCH-001` | get_transfers duplication tolerance (wallet RPC repeats) | P0 | High | `SCOPED-READY` | `docs/testing/04-full-stack-scenarios.md` | Automated check implemented. |
| `ZB-WATCH-002` | Partial transfer visibility (incoming appears without final fields) | P0 | High | `SCOPED-READY` | `docs/testing/04-full-stack-scenarios.md` | Automated check implemented. |
| `ZB-WATCH-003` | Zephyr reorg via pop_blocks removes a credited deposit | P0 | Critical | `SCOPED-TBC` | `docs/testing/04-full-stack-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-WATCH-004` | Zephyr reorg after claimable but before claim | P1 | High | `SCOPED-TBC` | `docs/testing/04-full-stack-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-WATCH-005` | EVM log duplication on WS reconnect | P0 | Critical | `SCOPED-EXPAND` | `docs/testing/04-full-stack-scenarios.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-WATCH-006` | EVM reorg (snapshot/revert) handling for Burned logs | P0 | Critical | `SCOPED-TBC` | `docs/testing/04-full-stack-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-WATCH-007` | Pool scan cursor off-by-one (known issue regression test) | P0 | High | `SCOPED-READY` | `docs/testing/04-full-stack-scenarios.md` | Keep as regression in current suite. |
| `ZB-WATCH-008` | Uniswap event backfill correctness under high activity | P1 | Medium | `SCOPED-TBC` | `docs/testing/04-full-stack-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-WATCH-009` | Missed block range recovery (watcher starts late) | P0 | Critical | `SCOPED-EXPAND` | `docs/testing/04-full-stack-scenarios.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-WATCH-010` | Multi-instance watchers and distributed locks | P1 | High | `SCOPED-TBC` | `docs/testing/04-full-stack-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-WATCH-011` | Wallet RPC inconsistent semantics (Monero-style pitfalls) | P0 | Critical | `SCOPED-READY` | `docs/testing/04-full-stack-scenarios.md` | Automated check implemented. |
| `ZB-WATCH-012` | Time-lock / unlock_time handling | P1 | Medium | `SCOPED-READY` | `docs/testing/04-full-stack-scenarios.md` | Automated check implemented. |

## 8. Multi-Asset Interactions (10)

| ID | Test | Priority | Severity | Status | Primary Doc | Next Action |
|---|---|---|---|---|---|---|
| `ZB-ASSET-001` | Wrap ZSD (not just ZPH) | P0 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Keep as regression in current suite. |
| `ZB-ASSET-002` | Wrap ZRS | P1 | Medium | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Keep as regression in current suite. |
| `ZB-ASSET-003` | Wrap ZYS | P1 | Medium | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Keep as regression in current suite. |
| `ZB-ASSET-004` | Unwrap wZSD | P0 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Keep as regression in current suite. |
| `ZB-ASSET-005` | Unwrap wZRS | P1 | Medium | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Keep as regression in current suite. |
| `ZB-ASSET-006` | Unwrap wZYS | P0 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Keep as regression in current suite. |
| `ZB-ASSET-007` | Reject legacy asset_type usage (ZEPH/ZEPHUSD/etc) | P0 | High | `SCOPED-EXPAND` | `docs/testing/03-bridge-scenarios.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-ASSET-008` | Minimum atomic amount (1 unit) through wrap and swap | P1 | Medium | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-ASSET-009` | Very large amount near wallet/erc20 limits | P1 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-ASSET-010` | Cross-asset engine pathing correctness (ZSD↔ZYS / ZRS↔ZPH) | P0 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |

## 9. DEX Edge Cases (10)

| ID | Test | Priority | Severity | Status | Primary Doc | Next Action |
|---|---|---|---|---|---|---|
| `ZB-DEX-001` | Swap when pool has zero liquidity | P1 | Medium | `SCOPED-READY` | `docs/testing/04-full-stack-scenarios.md` | Automated check implemented. |
| `ZB-DEX-002` | Swap exact input with slippage = 0 | P1 | Medium | `SCOPED-READY` | `docs/testing/04-full-stack-scenarios.md` | Automated check implemented. |
| `ZB-DEX-003` | Multi-hop route failure in intermediate hop | P0 | High | `SCOPED-EXPAND` | `docs/testing/04-full-stack-scenarios.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-DEX-004` | Tick spacing / initialization mismatch | P1 | Medium | `SCOPED-READY` | `docs/testing/04-full-stack-scenarios.md` | Automated check implemented. |
| `ZB-DEX-005` | Swap crossing multiple bands (large trade) | P0 | High | `SCOPED-READY` | `docs/testing/04-full-stack-scenarios.md` | Automated check implemented. |
| `ZB-DEX-006` | Approve rejection path | P2 | Low | `SCOPED-READY` | `docs/testing/04-full-stack-scenarios.md` | Automated check implemented. |
| `ZB-DEX-007` | Permit2 missing/misconfigured | P1 | Medium | `SCOPED-READY` | `docs/testing/04-full-stack-scenarios.md` | Automated check implemented. |
| `ZB-DEX-008` | Decimal mismatch across 6-dec and 12-dec tokens in routing | P0 | High | `SCOPED-EXPAND` | `docs/testing/04-full-stack-scenarios.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-DEX-009` | Uniswap watcher captures swaps and updates cached pool state | P0 | High | `SCOPED-READY` | `docs/testing/04-full-stack-scenarios.md` | Keep as regression in current suite. |
| `ZB-DEX-010` | Out-of-range LP positions and fee accounting visibility | P1 | Medium | `SCOPED-READY` | `docs/testing/04-full-stack-scenarios.md` | Automated check implemented. |

## 10. Timeout & Deadline Handling (8)

| ID | Test | Priority | Severity | Status | Primary Doc | Next Action |
|---|---|---|---|---|---|---|
| `ZB-TIME-001` | Claim expiry lifecycle | P0 | Medium | `SCOPED-EXPAND` | `docs/testing/03-bridge-scenarios.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-TIME-002` | Expiry does not mark usedZephyrTx | P0 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-TIME-003` | Prepared unwrap that is never burned (garbage collection) | P2 | Low | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-TIME-004` | Unwrap send retries with exponential backoff / bounded attempts | P1 | Medium | `SCOPED-TBC` | `docs/testing/03-bridge-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-TIME-005` | EVM tx pending for long time (mempool delay) | P1 | High | `SCOPED-EXPAND` | `docs/testing/03-bridge-scenarios.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-TIME-006` | Zephyr deposit confirmation rule vs reorg depth | P1 | High | `SCOPED-TBC` | `docs/testing/03-bridge-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-TIME-007` | SSE idle timeout and resume from last state | P2 | Low | `SCOPED-EXPAND` | `docs/testing/03-bridge-scenarios.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-TIME-008` | Engine staleness guard (market data age) | P0 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |

## 11. Configuration Errors (10)

| ID | Test | Priority | Severity | Status | Primary Doc | Next Action |
|---|---|---|---|---|---|---|
| `ZB-CONF-001` | Wrong Zephyr daemon RPC port | P0 | High | `SCOPED-EXPAND` | `docs/testing/02-infra-checklist.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-CONF-002` | Wrong wallet RPC port for gov wallet (unwrap fails) | P0 | High | `SCOPED-READY` | `docs/testing/02-infra-checklist.md` | Automated check implemented. |
| `ZB-CONF-003` | Wrong Anvil WS URL (watcher-evm) | P0 | Critical | `SCOPED-EXPAND` | `docs/testing/02-infra-checklist.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-CONF-004` | Wrong token addresses served by /bridge/tokens | P0 | Critical | `SCOPED-READY` | `docs/testing/02-infra-checklist.md` | Automated check implemented. |
| `ZB-CONF-005` | Wrong decimals configuration on frontend for wrapped tokens | P0 | High | `SCOPED-READY` | `docs/testing/02-infra-checklist.md` | Automated check implemented. |
| `ZB-CONF-006` | Fake oracle unreachable due to Docker network namespace changes | P1 | Medium | `SCOPED-READY` | `docs/testing/02-infra-checklist.md` | Automated check implemented. |
| `ZB-CONF-007` | Missing admin token env var / rotated token | P2 | Low | `SCOPED-READY` | `docs/testing/02-infra-checklist.md` | Automated check implemented. |
| `ZB-CONF-008` | Postgres schema mismatch / migration drift | P0 | High | `SCOPED-EXPAND` | `docs/testing/02-infra-checklist.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-CONF-009` | Engine MEXC configuration absent or invalid | P0 | High | `SCOPED-READY` | `docs/testing/02-infra-checklist.md` | Automated check implemented. |
| `ZB-CONF-010` | Wrong RR thresholds configured in engine | P0 | High | `SCOPED-EXPAND` | `docs/testing/02-infra-checklist.md` | Extend existing scenario with explicit edge assertions. |

## 12. Load & Stress (8)

| ID | Test | Priority | Severity | Status | Primary Doc | Next Action |
|---|---|---|---|---|---|---|
| `ZB-LOAD-001` | Burst create 10k bridge addresses | P1 | Medium | `SCOPED-TBC` | `docs/testing/05-devnet-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-LOAD-002` | Burst 1k deposits in 5 minutes | P0 | High | `SCOPED-TBC` | `docs/testing/05-devnet-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-LOAD-003` | Burst 1k burns in 5 minutes | P0 | High | `SCOPED-TBC` | `docs/testing/05-devnet-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-LOAD-004` | Rapid oracle price changes (10/sec) | P1 | Medium | `SCOPED-READY` | `docs/testing/05-devnet-scenarios.md` | Keep as regression in current suite. |
| `ZB-LOAD-005` | SSE fanout: 500 concurrent stream clients | P1 | Medium | `SCOPED-READY` | `docs/testing/05-devnet-scenarios.md` | Automated check implemented. |
| `ZB-LOAD-006` | Uniswap swap storm (10k swaps) | P1 | Medium | `SCOPED-TBC` | `docs/testing/05-devnet-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-LOAD-007` | Postgres slow queries / high latency injection | P0 | High | `SCOPED-TBC` | `docs/testing/05-devnet-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-LOAD-008` | Wallet RPC slow/timeout injection | P0 | High | `SCOPED-READY` | `docs/testing/05-devnet-scenarios.md` | Automated check implemented. |

## 13. Privacy Leaks (6)

| ID | Test | Priority | Severity | Status | Primary Doc | Next Action |
|---|---|---|---|---|---|---|
| `ZB-PRIV-001` | /claims/:evmAddress must not expose other users' Zephyr subaddresses | P1 | Medium | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-PRIV-002` | /details "My Activity" scoping | P1 | Medium | `SCOPED-EXPAND` | `docs/testing/03-bridge-scenarios.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-PRIV-003` | SSE stream authorization expectations | P2 | Low | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-PRIV-004` | Logs do not print full Zephyr destination addresses by default | P2 | Low | `SCOPED-TBC` | `docs/testing/03-bridge-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-PRIV-005` | Engine global state does not include private wallet seeds/keys | P1 | High | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |
| `ZB-PRIV-006` | Bridge DB exports don't leak unnecessary mapping | P2 | Low | `SCOPED-READY` | `docs/testing/03-bridge-scenarios.md` | Automated check implemented. |

## 14. Frontend Edge Cases (12)

| ID | Test | Priority | Severity | Status | Primary Doc | Next Action |
|---|---|---|---|---|---|---|
| `ZB-FE-001` | MetaMask connect rejection | P2 | Low | `SCOPED-TBC` | `docs/testing/04-full-stack-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-FE-002` | Wrong network (not 31337) handling | P0 | High | `SCOPED-EXPAND` | `docs/testing/04-full-stack-scenarios.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-FE-003` | Account switching mid wrap flow | P1 | Medium | `SCOPED-TBC` | `docs/testing/04-full-stack-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-FE-004` | Concurrent tabs: two wraps in parallel | P0 | High | `SCOPED-EXPAND` | `docs/testing/04-full-stack-scenarios.md` | Extend existing scenario with explicit edge assertions. |
| `ZB-FE-005` | User sends wrong asset to bridge address (ZSD instead of ZPH) | P0 | High | `SCOPED-TBC` | `docs/testing/04-full-stack-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-FE-006` | User sends multiple deposits before first claim completes | P0 | High | `SCOPED-TBC` | `docs/testing/04-full-stack-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-FE-007` | Claim tx rejected / reverted path | P1 | Medium | `SCOPED-TBC` | `docs/testing/04-full-stack-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-FE-008` | Unwrap destination validation (invalid Zephyr address / bytes) | P0 | Critical | `SCOPED-READY` | `docs/testing/04-full-stack-scenarios.md` | Keep as regression in current suite. |
| `ZB-FE-009` | Unwrap "burn without prepare" (advanced user path) | P0 | High | `SCOPED-TBC` | `docs/testing/04-full-stack-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-FE-010` | Swap quote mismatch vs execution (price moves) | P1 | Medium | `SCOPED-TBC` | `docs/testing/04-full-stack-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-FE-011` | Token approvals persisted correctly per token/router | P2 | Low | `SCOPED-TBC` | `docs/testing/04-full-stack-scenarios.md` | New scenario; add harness + exact commands (TBC). |
| `ZB-FE-012` | SSE reconnect logic: step UI never gets "stuck" | P0 | High | `SCOPED-EXPAND` | `docs/testing/04-full-stack-scenarios.md` | Extend existing scenario with explicit edge assertions. |

## Notes

- `SCOPED-TBC` tests are intentionally listed now so coverage gaps are visible; detailed command-level procedures can be added in the next pass.
- Use this catalog as the source of truth when promoting tests into executable L3/L4 runbooks.
