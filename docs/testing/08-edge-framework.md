# L5 Edge Test Framework

Execution framework for the integrated ZB edge-case catalog in [00-edge-case-scope.md](./00-edge-case-scope.md).

## Goal

Run all edge-case tests through a repeatable lifecycle:

1. Validate catalog integrity.
2. Run a logical pass over all tests (ready, expand, and TBC).
3. Execute runnable tests by lane.
4. Convert `SCOPED-TBC` items into executable runbooks.

## Runner

The framework runner is:

```bash
./scripts/run-l5-tests.py
```

### Core Commands

```bash
# Default: summary + lint + logical pass
./scripts/run-l5-tests.py

# Lint only
./scripts/run-l5-tests.py --lint

# Full list or filtered list
./scripts/run-l5-tests.py --list
./scripts/run-l5-tests.py --list --priority P0
./scripts/run-l5-tests.py --list --status SCOPED-TBC

# Logical run-through with per-test output
./scripts/run-l5-tests.py --logical --verbose

# Browser lane prerequisites
./scripts/run-l5-tests.py --browser-preflight

# Execute automated checks (ready + expand)
./scripts/run-l5-tests.py --execute --report-json .l5-execution-report.json

# Execute all tests with baseline checks (including TBC)
./scripts/run-l5-tests.py --execute --execute-tbc --report-json .l5-execution-report.json
```

Execution result semantics:

- `PASS`: automated check passed.
- `FAIL`: automated check ran and failed.
- `BLOCKED`: prerequisites missing (service/browser) or `SCOPED-TBC` withheld unless `--execute-tbc` is used.

## Execution Lanes

- `api-contract`: Bridge API, wallet RPC, EVM contract, DB consistency.
- `chaos-recovery`: Restarts, reorgs, duplication, race and lock behavior.
- `runtime-policy`: RR boundaries, stale-state gating, timeout/deadline behavior.
- `dex-routing`: route integrity, slippage, decimal handling, pool state.
- `browser`: wallet UX, multi-tab flows, SSE step UI resilience.
- `privacy-observability`: data exposure boundaries and logging hygiene.

## Browser Lane

For browser/MetaMask tests (`ZB-FE-*`), use a CDP-based Chrome workflow:

1. Run `--browser-preflight` to check prerequisites.
2. Launch Chrome with `--remote-debugging-port=9222` and the MetaMask profile.
3. Validate wallet unlock and account/network state.
4. Execute FE test scenarios from `docs/testing/04-full-stack-scenarios.md` and the integrated L5 catalog section.

## TBC Promotion Workflow

For each `SCOPED-TBC` test:

1. Add concrete preconditions and exact commands in the owning runbook doc.
2. Add pass/fail assertions (state + API + on-chain where applicable).
3. Reclassify in catalog from `SCOPED-TBC` to `SCOPED-EXPAND` or `SCOPED-READY`.
4. Re-run `./scripts/run-l5-tests.py --lint --logical`.

## Make Targets

```bash
# Core
make test-edge                   # Summary + lint + logical pass
make test-edge-lint
make test-edge-summary
make test-edge-browser-preflight
make test-edge-execute           # Run ready+expand checks
make test-edge-execute-all       # Run all checks including TBC

# Sublevel targets
make test-edge-sec               # L5.1 Security & Contracts (SEC + SC)
make test-edge-runtime           # L5.2 Runtime & Consistency (CONS + RR + CONC + SEED)
make test-edge-infra             # L5.3 Infra & Watchers (WATCH + CONF + REC)
make test-edge-asset             # L5.4 Asset & DEX (ASSET + DEX)
make test-edge-stress            # L5.5 Privacy & Load (PRIV + LOAD + TIME)
make test-edge-fe                # L5.6 Frontend (FE)
make test-edge-seed              # SEED checks (8 seeding verification tests)
```
