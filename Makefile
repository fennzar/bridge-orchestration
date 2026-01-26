# ===========================================
# Zephyr Bridge Stack - Unified CLI
# ===========================================
#
# Dev workflow:
#   make dev          # Main entry point (auto-inits if fresh, then starts)
#   make dev-reset    # Reset all layers to post-init state (~30 sec)
#   make dev-init     # Nuclear wipe + rebuild from scratch
#   make dev-stop     # Stop everything
#
# Selective apps:
#   make dev APPS=bridge          Only bridge processes
#   make dev APPS=bridge,engine   Bridge + engine (no dashboard)
#
# Testnet workflow:
#   make testnet-build
#   make testnet-up PROFILE=full
#   make testnet-down

SHELL := /bin/bash
.DEFAULT_GOAL := help

# ===========================================
# Configuration
# ===========================================
COMPOSE_BASE := docker/compose.base.yml
COMPOSE_DEV  := docker/compose.dev.yml
COMPOSE_TEST := docker/compose.testnet.yml
COMPOSE_PROD := docker/compose.prod.yml

DC_DEV  := docker compose --env-file .env -f $(COMPOSE_BASE) -f $(COMPOSE_DEV)
DC_TEST := docker compose --env-file .env -f $(COMPOSE_BASE) -f $(COMPOSE_TEST)

# Paths (loaded from .env if available)
# Save system PATH before .env overrides it
SYSTEM_PATH := $(PATH)
-include .env
# Restore PATH (the .env PATH uses $PATH which doesn't expand in Make)
export PATH := $(SYSTEM_PATH)
ORCH_DIR        := $(CURDIR)
PROCFILE        := $(ORCH_DIR)/Procfile.dev
OVERMIND_SOCK   := $(ORCH_DIR)/.overmind-dev.sock


# ===========================================
# Build
# ===========================================

.PHONY: build build-zephyr build-oracle build-orderbook build-init sync-zephyr

## Build all Docker images
build: build-zephyr build-oracle build-orderbook build-init

## Build Zephyr node/wallet image (uses vendored binaries)
build-zephyr:
	@echo "=== Building zephyr-devnet image ==="
	@if [ ! -f "docker/zephyr/bin/zephyrd" ]; then \
		echo "Error: zephyrd not found at docker/zephyr/bin/zephyrd"; \
		echo "Run: ./scripts/sync-zephyr-artifacts.sh"; \
		exit 1; \
	fi
	docker build -t zephyr-devnet docker/zephyr/

## Build fake oracle image (uses vendored oracle files)
build-oracle:
	@echo "=== Building zephyr-fake-oracle image ==="
	@if [ ! -f "docker/fake-oracle/server.js" ]; then \
		echo "Error: oracle files not found. Run: ./scripts/sync-zephyr-artifacts.sh"; \
		exit 1; \
	fi
	docker build -t zephyr-fake-oracle docker/fake-oracle/

## Sync all artifacts from Zephyr repo
sync-zephyr:
	./scripts/sync-zephyr-artifacts.sh

## Build fake orderbook image
build-orderbook:
	@echo "=== Building zephyr-fake-orderbook image ==="
	docker build -t zephyr-fake-orderbook -f docker/fake-orderbook/Dockerfile services/fake-orderbook/

## Build devnet-init image
build-init:
	@echo "=== Building zephyr-devnet-init image ==="
	docker build -t zephyr-devnet-init docker/devnet-init/

# ===========================================
# Dev Environment
# ===========================================

.PHONY: dev dev-init dev-delete dev-apps dev-stop dev-reset dev-reset-zephyr dev-reset-evm dev-reset-db dev-checkpoint status logs clean

## Main entry point — auto-inits on first run, then starts everything
dev:
	@# Clean stale Overmind socket if process is dead
	@if [ -S "$(OVERMIND_SOCK)" ] && ! overmind status -s $(OVERMIND_SOCK) >/dev/null 2>&1; then \
		echo "Cleaning stale Overmind socket..."; \
		rm -f $(OVERMIND_SOCK); \
	fi
	@# Build images if missing
	@if ! docker image inspect zephyr-devnet >/dev/null 2>&1; then \
		echo "=== Docker images not found — building ==="; \
		$(MAKE) build; \
	fi
	@# Start infrastructure
	@echo "=== Starting Docker infrastructure ==="
	@$(DC_DEV) up -d
	@# Auto-init if chain is uninitialized (first run or wiped volumes)
	@# Check both: checkpoint file exists AND chain height > 1
	@NEEDS_INIT=false; \
	if ! $(DC_DEV) exec -T wallet-gov cat /checkpoint/height >/dev/null 2>&1; then \
		NEEDS_INIT=true; \
	else \
		HEIGHT=$$(curl -sf http://127.0.0.1:47767/json_rpc \
			-d '{"jsonrpc":"2.0","id":"0","method":"get_info"}' 2>/dev/null | \
			python3 -c "import sys,json; print(json.load(sys.stdin)['result']['height'])" 2>/dev/null || echo "0"); \
		if [ "$$HEIGHT" -le 1 ] 2>/dev/null; then \
			echo "  Warning: checkpoint exists but chain is at height $$HEIGHT — re-initializing"; \
			NEEDS_INIT=true; \
		fi; \
	fi; \
	if [ "$$NEEDS_INIT" = "true" ]; then \
		echo ""; \
		echo "=== First run detected — initializing DEVNET ==="; \
		echo ""; \
		docker rm zephyr-devnet-init 2>/dev/null || true; \
		$(DC_DEV) --profile init up devnet-init; \
		echo ""; \
		echo "=== Resetting Anvil for fresh deploy ==="; \
		$(DC_DEV) exec -T anvil rm -f /data/anvil-state.json 2>/dev/null || true; \
		$(DC_DEV) restart anvil; \
		echo "  Waiting for Anvil..."; \
		for i in $$(seq 1 20); do cast block-number --rpc-url http://127.0.0.1:8545 >/dev/null 2>&1 && break; sleep 0.5; done; \
		echo "=== Deploying EVM contracts ==="; \
		$(MAKE) deploy-contracts; \
		echo ""; \
		echo "=== Pushing database schemas ==="; \
		cd $(BRIDGE_REPO_PATH)/packages/db && DATABASE_URL=$(DATABASE_URL_BRIDGE) npx prisma db push 2>&1 | tail -1; \
		cd $(ENGINE_REPO_PATH) && DATABASE_URL=$(DATABASE_URL_ENGINE) pnpm prisma db push --schema=src/infra/prisma/schema.prisma --skip-generate 2>&1 | tail -1; \
		echo ""; \
	fi
	@# Start apps
	@$(MAKE) dev-apps APPS=$(APPS)
	@echo ""
	@echo "=== Dev stack running ==="
	@if [ -n "$(APPS)" ]; then echo "  Apps: $(APPS)"; fi
	@echo "  Bridge UI:  http://localhost:7050"
	@echo "  Bridge API: http://localhost:7051"
	@echo "  Engine:     http://localhost:7000"
	@echo "  Dashboard:  http://localhost:7100"

## Nuclear wipe + re-init (destroys all volumes, rebuilds from scratch)
dev-init:
	@echo "=== Nuclear wipe + re-init ==="
	@# 1. Stop Overmind
	@if [ -S "$(OVERMIND_SOCK)" ]; then \
		echo "  Stopping Overmind..."; \
		overmind quit -s $(OVERMIND_SOCK) 2>/dev/null || true; \
		for i in $$(seq 1 10); do [ ! -S "$(OVERMIND_SOCK)" ] && break; sleep 0.5; done; \
	fi
	@rm -f $(OVERMIND_SOCK)
	@# 2. Tear down containers + volumes
	@echo "  Removing containers and volumes..."
	@$(DC_DEV) down -v 2>/dev/null || true
	@# Also remove any orphaned volumes (handles project-name mismatches)
	@docker volume ls -q --filter name=docker_zephyr | xargs -r docker volume rm 2>/dev/null || true
	@docker volume ls -q --filter name=docker_redis | xargs -r docker volume rm 2>/dev/null || true
	@docker volume ls -q --filter name=docker_postgres | xargs -r docker volume rm 2>/dev/null || true
	@docker volume ls -q --filter name=docker_anvil | xargs -r docker volume rm 2>/dev/null || true
	@# 3. Rebuild images
	@$(MAKE) build
	@# 4. Start infrastructure
	@echo ""
	@echo "=== Starting Docker infrastructure ==="
	@$(DC_DEV) up -d
	@# 5. Run devnet init (unconditionally — this is nuclear)
	@echo ""
	@echo "=== Initializing DEVNET ==="
	@docker rm zephyr-devnet-init 2>/dev/null || true
	@$(DC_DEV) --profile init up devnet-init
	@# 6. Reset Anvil + deploy contracts
	@echo ""
	@echo "=== Resetting Anvil for fresh deploy ==="
	@$(DC_DEV) exec -T anvil rm -f /data/anvil-state.json 2>/dev/null || true
	@$(DC_DEV) restart anvil
	@echo "  Waiting for Anvil..."
	@for i in $$(seq 1 20); do cast block-number --rpc-url http://127.0.0.1:8545 >/dev/null 2>&1 && break; sleep 0.5; done
	@echo "=== Deploying EVM contracts ==="
	@$(MAKE) deploy-contracts
	@# 7. Push database schemas
	@echo ""
	@echo "=== Pushing database schemas ==="
	@cd $(BRIDGE_REPO_PATH)/packages/db && DATABASE_URL=$(DATABASE_URL_BRIDGE) npx prisma db push 2>&1 | tail -1
	@cd $(ENGINE_REPO_PATH) && DATABASE_URL=$(DATABASE_URL_ENGINE) pnpm prisma db push --schema=src/infra/prisma/schema.prisma --skip-generate 2>&1 | tail -1
	@# 8. Start apps
	@echo ""
	@$(MAKE) dev-apps APPS=$(APPS)
	@echo ""
	@echo "=== Dev stack running (fresh init) ==="
	@if [ -n "$(APPS)" ]; then echo "  Apps: $(APPS)"; fi
	@echo "  Bridge UI:  http://localhost:7050"
	@echo "  Bridge API: http://localhost:7051"
	@echo "  Engine:     http://localhost:7000"
	@echo "  Dashboard:  http://localhost:7100"

## Start Docker infrastructure only
dev-infra:
	@echo "=== Starting Docker infrastructure ==="
	$(DC_DEV) up -d

## Start native apps via Overmind (usage: make dev-apps APPS=bridge)
dev-apps:
	@echo "=== Starting apps (Overmind) ==="
	@# Clean stale socket if Overmind is dead
	@if [ -S "$(OVERMIND_SOCK)" ] && ! overmind status -s $(OVERMIND_SOCK) >/dev/null 2>&1; then \
		rm -f $(OVERMIND_SOCK); \
	fi
	@if [ -S "$(OVERMIND_SOCK)" ]; then \
		echo "  Overmind already running"; \
	elif [ -n "$(APPS)" ]; then \
		FORM="bridge-web=0,bridge-api=0,bridge-watchers=0,engine-web=0,engine-watchers=0,dashboard=0"; \
		IFS=',' read -ra APP_LIST <<< "$(APPS)"; \
		for grp in "$${APP_LIST[@]}"; do \
			case "$$grp" in \
				bridge)    FORM=$$(echo "$$FORM" | sed 's/bridge-web=0/bridge-web=1/;s/bridge-api=0/bridge-api=1/;s/bridge-watchers=0/bridge-watchers=1/') ;; \
				engine)    FORM=$$(echo "$$FORM" | sed 's/engine-web=0/engine-web=1/;s/engine-watchers=0/engine-watchers=1/') ;; \
				dashboard) FORM=$$(echo "$$FORM" | sed 's/dashboard=0/dashboard=1/') ;; \
				*)         echo "Error: Unknown app group '$$grp'. Valid groups: bridge, engine, dashboard"; exit 1 ;; \
			esac; \
		done; \
		echo "  Formation: $$FORM"; \
		cd $(ORCH_DIR) && OVERMIND_FORMATION="$$FORM" overmind start -D -f $(PROCFILE) -s $(OVERMIND_SOCK); \
		echo "  Overmind started"; \
	else \
		cd $(ORCH_DIR) && overmind start -D -f $(PROCFILE) -s $(OVERMIND_SOCK); \
		echo "  Overmind started"; \
	fi

## Stop everything (apps + infra), preserves all data
dev-stop:
	@echo "=== Stopping apps ==="
	@if [ -S "$(OVERMIND_SOCK)" ]; then \
		overmind quit -s $(OVERMIND_SOCK) 2>/dev/null || true; \
		for i in $$(seq 1 10); do [ ! -S "$(OVERMIND_SOCK)" ] && break; sleep 0.5; done; \
	fi
	@rm -f $(OVERMIND_SOCK)
	@echo "=== Stopping Docker infrastructure ==="
	$(DC_DEV) down
	@echo "=== Stopped ==="

## Delete everything — containers, volumes, images. No rebuild, no restart.
dev-delete:
	@echo "=== Deleting all dev state ==="
	@# Stop Overmind
	@if [ -S "$(OVERMIND_SOCK)" ]; then \
		echo "  Stopping Overmind..."; \
		overmind quit -s $(OVERMIND_SOCK) 2>/dev/null || true; \
		for i in $$(seq 1 10); do [ ! -S "$(OVERMIND_SOCK)" ] && break; sleep 0.5; done; \
	fi
	@rm -f $(OVERMIND_SOCK)
	@# Remove containers + volumes
	@echo "  Removing containers and volumes..."
	@$(DC_DEV) down -v 2>/dev/null || true
	@# Remove orphaned volumes (handles project-name mismatches)
	@docker volume ls -q --filter name=docker_zephyr | xargs -r docker volume rm 2>/dev/null || true
	@docker volume ls -q --filter name=docker_redis | xargs -r docker volume rm 2>/dev/null || true
	@docker volume ls -q --filter name=docker_postgres | xargs -r docker volume rm 2>/dev/null || true
	@docker volume ls -q --filter name=docker_anvil | xargs -r docker volume rm 2>/dev/null || true
	@# Remove built images
	@echo "  Removing Docker images..."
	@docker rmi zephyr-devnet zephyr-fake-oracle zephyr-fake-orderbook zephyr-devnet-init 2>/dev/null || true
	@echo "=== Deleted ==="

## Full coordinated reset: Zephyr + Anvil + DB + Redis (~30 sec)
dev-reset:
	./scripts/dev-reset.sh

## Reset Zephyr chain only (pop blocks to checkpoint)
dev-reset-zephyr:
	./scripts/dev-reset.sh --zephyr-only

## Reset EVM only (Anvil wipe + redeploy contracts)
dev-reset-evm:
	./scripts/dev-reset.sh --evm-only

## Reset databases only (Postgres + Redis)
dev-reset-db:
	./scripts/dev-reset.sh --db-only

## Save current height as checkpoint
dev-checkpoint:
	@echo "=== Saving checkpoint ==="
	@HEIGHT=$$(curl -sf http://localhost:47767/json_rpc \
		-d '{"jsonrpc":"2.0","id":"0","method":"get_info"}' | jq -r '.result.height') && \
	$(DC_DEV) exec -T wallet-gov sh -c "echo $$HEIGHT > /checkpoint/height" && \
	echo "  Checkpoint saved at height: $$HEIGHT"

## Check health of all services
status:
	@echo "=== Docker Containers ==="
	@$(DC_DEV) ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || echo "  No containers running"
	@echo ""
	@echo "=== Overmind Processes ==="
	@if [ -S "$(OVERMIND_SOCK)" ]; then \
		overmind status -s $(OVERMIND_SOCK) 2>/dev/null || echo "  Not running"; \
	else \
		echo "  Not running"; \
	fi
	@echo ""
	@echo "=== Chain Status ==="
	@printf "  Anvil:  " && curl -sf http://localhost:8545 -X POST \
		-H 'Content-Type: application/json' \
		-d '{"jsonrpc":"2.0","method":"eth_blockNumber","id":1}' 2>/dev/null | jq -r '.result' || echo "not running"
	@printf "  Zephyr: " && curl -sf http://localhost:47767/json_rpc \
		-d '{"jsonrpc":"2.0","id":"0","method":"get_info"}' 2>/dev/null | jq -r '"height \(.result.height)"' || echo "not running"
	@printf "  Oracle: " && curl -sf http://localhost:5555/status 2>/dev/null | jq -r '"$$\(.spot / 1000000000000) (running)"' || echo "not running"

## Tail logs for a service (usage: make logs SERVICE=zephyr-node1)
logs:
	$(DC_DEV) logs -f $(SERVICE)

# ===========================================
# Oracle / Scenario Control
# ===========================================

.PHONY: set-price set-scenario fund

## Set oracle price (usage: make set-price PRICE=1.50)
set-price:
	@if [ -z "$(PRICE)" ]; then echo "Usage: make set-price PRICE=<usd>"; exit 1; fi
	@ATOMIC=$$(echo "$(PRICE)" | awk '{printf "%.0f", $$1 * 1000000000000}') && \
	echo "Setting oracle price to $(PRICE) USD ($$ATOMIC atomic)" && \
	curl -sf -X POST http://localhost:5555/set-price \
		-H 'Content-Type: application/json' \
		-d "{\"spot\": $$ATOMIC}" | jq .

## Set scenario preset (usage: make set-scenario SCENARIO=crisis)
set-scenario:
	@if [ -z "$(SCENARIO)" ]; then echo "Usage: make set-scenario SCENARIO=<preset>"; echo "Presets: normal, defensive, crisis, recovery, high-rr, volatility"; exit 1; fi
	@case "$(SCENARIO)" in \
		normal)     PRICE=15.00; SPREAD=50 ;; \
		defensive)  PRICE=0.80;  SPREAD=100 ;; \
		crisis)     PRICE=0.40;  SPREAD=300 ;; \
		recovery)   PRICE=2.00;  SPREAD=50 ;; \
		high-rr)    PRICE=25.00; SPREAD=50 ;; \
		volatility) PRICE=5.00;  SPREAD=150 ;; \
		*) echo "Unknown scenario: $(SCENARIO)"; exit 1 ;; \
	esac && \
	ATOMIC=$$(echo "$$PRICE" | awk '{printf "%.0f", $$1 * 1000000000000}') && \
	echo "Setting scenario '$(SCENARIO)': price=$${PRICE} USD, spread=$${SPREAD}bps" && \
	curl -sf -X POST http://localhost:5555/set-price \
		-H 'Content-Type: application/json' \
		-d "{\"spot\": $$ATOMIC}" | jq . && \
	curl -sf -X POST http://localhost:5556/set-spread \
		-H 'Content-Type: application/json' \
		-d "{\"spreadBps\": $$SPREAD}" | jq . 2>/dev/null || true

## Fund a wallet (usage: make fund WALLET=test AMOUNT=1000 ASSET=ZPH)
fund:
	@WALLET=$${WALLET:-test}; AMOUNT=$${AMOUNT:-1000}; ASSET=$${ASSET:-ZPH}; \
	ATOMIC=$$(echo "$$AMOUNT" | awk '{printf "%.0f", $$1 * 1000000000000}') && \
	echo "Funding $$WALLET with $$AMOUNT $$ASSET" && \
	case "$$WALLET" in \
		test)  DEST_PORT=48768 ;; \
		miner) DEST_PORT=48767 ;; \
		*)     echo "Unknown wallet: $$WALLET (use test or miner)"; exit 1 ;; \
	esac && \
	DEST_ADDR=$$(curl -sf http://localhost:$$DEST_PORT/json_rpc \
		-d '{"jsonrpc":"2.0","id":"0","method":"get_address","params":{"account_index":0}}' | jq -r '.result.address') && \
	curl -sf http://localhost:48769/json_rpc \
		-d '{"jsonrpc":"2.0","id":"0","method":"refresh"}' >/dev/null 2>&1 && \
	sleep 1 && \
	curl -sf http://localhost:48769/json_rpc \
		-H 'Content-Type: application/json' \
		-d "{\"jsonrpc\":\"2.0\",\"id\":\"0\",\"method\":\"transfer\",\"params\":{\"destinations\":[{\"amount\":$$ATOMIC,\"address\":\"$$DEST_ADDR\"}],\"source_asset\":\"$$ASSET\",\"destination_asset\":\"$$ASSET\",\"priority\":0,\"ring_size\":2,\"get_tx_key\":true}}" | jq '.result.tx_hash'

# ===========================================
# Contract Deployment + Env Sync
# ===========================================

.PHONY: deploy-contracts sync-env

## Deploy EVM contracts (runs on host via forge)
deploy-contracts:
	./scripts/deploy-contracts.sh

## Sync .env to sub-repos
sync-env:
	./scripts/sync-env.sh

# ===========================================
# Test Framework
# ===========================================

.PHONY: test test-l1 test-l2 test-l3 test-l4 test-l1-l2 test-l3-l4 test-l5 test-l5-lint test-l5-summary test-l5-browser-preflight test-l5-execute test-l5-execute-all test-l5-sec test-l5-runtime test-l5-infra test-l5-asset test-l5-stress test-l5-fe

## Run all L1-L4 tests
test:
	./scripts/run-tests.py

## Run L1 infrastructure tests only
test-l1:
	./scripts/run-tests.py --level L1

## Run L2 smoke tests only
test-l2:
	./scripts/run-tests.py --level L2

## Run L3 component tests only
test-l3:
	./scripts/run-tests.py --level L3

## Run L4 E2E tests only
test-l4:
	./scripts/run-tests.py --level L4

## Run L1/L2 infrastructure + smoke tests (legacy, delegates to run-tests.py)
test-l1-l2:
	./scripts/run-tests.py --level L1 --level L2

## Run L3/L4 component + e2e tests (legacy, delegates to run-tests.py)
test-l3-l4:
	./scripts/run-tests.py --level L3 --level L4

## Run L5 edge-case framework default pass (summary + lint + logical)
test-l5:
	./scripts/run-l5-tests.py

## L5 catalog lint
test-l5-lint:
	./scripts/run-l5-tests.py --lint

## L5 catalog summary
test-l5-summary:
	./scripts/run-l5-tests.py --summary

## L5 browser lane preflight
test-l5-browser-preflight:
	./scripts/run-l5-tests.py --browser-preflight

## L5 execution pass (runs ready+expand, blocks TBC)
test-l5-execute:
	./scripts/run-l5-tests.py --execute --report-json .l5-execution-report.json

## L5 execution pass including TBC baseline checks
test-l5-execute-all:
	./scripts/run-l5-tests.py --execute --execute-tbc --report-json .l5-execution-report.json

## L5.1 Security & Contracts (SEC + SC)
test-l5-sec:
	./scripts/run-l5-tests.py --execute --sublevel L5.1 --verbose

## L5.2 Runtime & Consistency (CONS + RR + CONC)
test-l5-runtime:
	./scripts/run-l5-tests.py --execute --sublevel L5.2 --verbose

## L5.3 Infra & Watchers (WATCH + CONF + REC)
test-l5-infra:
	./scripts/run-l5-tests.py --execute --sublevel L5.3 --verbose

## L5.4 Asset & DEX (ASSET + DEX)
test-l5-asset:
	./scripts/run-l5-tests.py --execute --sublevel L5.4 --verbose

## L5.5 Privacy & Load (PRIV + LOAD + TIME)
test-l5-stress:
	./scripts/run-l5-tests.py --execute --sublevel L5.5 --verbose

## L5.6 Frontend (FE)
test-l5-fe:
	./scripts/run-l5-tests.py --execute --sublevel L5.6 --verbose

# ===========================================
# Cleanup
# ===========================================

.PHONY: clean

## Alias for dev-delete
clean: dev-delete

# ===========================================
# Testnet
# ===========================================

.PHONY: testnet-build testnet-up testnet-down testnet-logs

## Build all app images for testnet
testnet-build: build
	@echo "=== Building app images ==="
	docker build -t zephyr-bridge-web --target web -f docker/bridge/Dockerfile $(BRIDGE_REPO_PATH)
	docker build -t zephyr-bridge-api --target api -f docker/bridge/Dockerfile $(BRIDGE_REPO_PATH)
	docker build -t zephyr-bridge-watchers --target watchers -f docker/bridge/Dockerfile $(BRIDGE_REPO_PATH)
	docker build -t zephyr-engine-web --target web -f docker/engine/Dockerfile $(ENGINE_REPO_PATH)
	docker build -t zephyr-engine-watchers --target watchers -f docker/engine/Dockerfile $(ENGINE_REPO_PATH)
	docker build -t zephyr-dashboard -f docker/dashboard/Dockerfile status-dashboard/

## Start testnet stack (usage: make testnet-up APPS=bridge or PROFILE=full)
testnet-up:
	@if [ -n "$(APPS)" ]; then \
		PROFILES=""; \
		IFS=','; for grp in $(APPS); do \
			case $$grp in \
				bridge|engine|full) PROFILES="$$PROFILES --profile $$grp" ;; \
				dashboard) PROFILES="$$PROFILES --profile full"; echo "Note: dashboard only available in 'full' profile" ;; \
				*) echo "Error: Unknown app group '$$grp'. Valid: bridge, engine, full"; exit 1 ;; \
			esac; \
		done; \
		$(DC_TEST) $$PROFILES up -d; \
	elif [ -n "$(PROFILE)" ]; then \
		$(DC_TEST) --profile $(PROFILE) up -d; \
	else \
		$(DC_TEST) --profile full up -d; \
	fi

## Stop testnet stack
testnet-down:
	$(DC_TEST) down

## Tail testnet logs
testnet-logs:
	$(DC_TEST) logs -f $(SERVICE)

# ===========================================
# Help
# ===========================================

.PHONY: help

## Show this help
help:
	@echo "Zephyr Bridge Stack"
	@echo ""
	@echo "Dev workflow:"
	@echo "  make dev              Main entry point (auto-inits if needed, then starts)"
	@echo "  make dev APPS=bridge  Start specific app groups (bridge,engine,dashboard)"
	@echo "  make dev-reset        Reset all layers to post-init state (~30 sec)"
	@echo "  make dev-reset-zephyr   Zephyr chain only (pop to checkpoint)"
	@echo "  make dev-reset-evm      EVM only (Anvil wipe + redeploy)"
	@echo "  make dev-reset-db       Databases only (Postgres + Redis)"
	@echo "  make dev-init         Nuclear wipe + rebuild from scratch"
	@echo "  make dev-stop         Stop everything (preserves data)"
	@echo "  make dev-delete       Delete everything (containers, volumes, images)"
	@echo "  make dev-checkpoint   Save current height as checkpoint"
	@echo "  make status         Check health of all services"
	@echo "  make logs SERVICE=x Tail logs for a Docker service"
	@echo ""
	@echo "Oracle/Scenario:"
	@echo "  make set-price PRICE=1.50"
	@echo "  make set-scenario SCENARIO=crisis"
	@echo "  make fund WALLET=test AMOUNT=1000 ASSET=ZPH"
	@echo ""
	@echo "Other:"
	@echo "  make deploy-contracts  Deploy EVM contracts"
	@echo "  make sync-env          Sync .env to sub-repos"
	@echo "  make sync-zephyr       Copy artifacts from Zephyr repo"
	@echo "  make test              Run all L1-L4 tests"
	@echo "  make test-l1           Run L1 infrastructure tests"
	@echo "  make test-l2           Run L2 smoke tests"
	@echo "  make test-l3           Run L3 component tests"
	@echo "  make test-l4           Run L4 E2E tests"
	@echo "  make test-l1-l2        Run L1+L2 (legacy alias)"
	@echo "  make test-l3-l4        Run L3+L4 (legacy alias)"
	@echo "  make test-l5           Run L5 edge framework pass"
	@echo "  make test-l5-lint      L5 catalog integrity checks"
	@echo "  make test-l5-summary   L5 catalog counts"
	@echo "  make test-l5-browser-preflight  Browser lane prerequisites"
	@echo "  make test-l5-execute   Execute L5 ready/expand checks"
	@echo "  make test-l5-execute-all  Execute L5 including TBC baseline"
	@echo "  make test-l5-sec         L5.1 Security & Contracts"
	@echo "  make test-l5-runtime     L5.2 Runtime & Consistency"
	@echo "  make test-l5-infra       L5.3 Infra & Watchers"
	@echo "  make test-l5-asset       L5.4 Asset & DEX"
	@echo "  make test-l5-stress      L5.5 Privacy & Load"
	@echo "  make test-l5-fe          L5.6 Frontend"
	@echo ""
	@echo "Testnet:"
	@echo "  make testnet-build     Build all app images"
	@echo "  make testnet-up PROFILE=full"
	@echo "  make testnet-up APPS=bridge,engine"
	@echo "  make testnet-down"
