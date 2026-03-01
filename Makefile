# ===========================================
# Zephyr Bridge Stack - Unified CLI
# ===========================================
#
# Dev workflow (staged setup):
#   make dev-init     # Base Zephyr devnet, then stop (~4 min)
#   make dev-setup    # Bridge infra on top, then stop (~4 min)
#   make dev          # Start everything (~10 sec)
#   make dev-stop     # Stop everything, preserves data
#
# Reset:
#   make dev-reset       # Reset to post-setup state, then stop
#   make dev-reset-hard  # Reset to post-init state, then stop
#
# Selective apps:
#   make dev APPS=bridge          Only bridge processes
#   make dev APPS=bridge,engine   Bridge + engine (no dashboard)
#
# Testnet V2 (Production Build Mode):
#   make testnet-v2-build
#   make testnet-v2
#   make testnet-v2-stop
#
# Testnet V3 (Sepolia):
#   make testnet-v3-up
#   make testnet-v3-down
#
# Explorer (Blockscout — on by default):
#   make dev                   Includes Blockscout at :4000
#   make dev EXPLORER=0        Skip Blockscout
#   make dev-explorer          Start Blockscout standalone (infra must be running)

SHELL := /bin/bash
.DEFAULT_GOAL := help

# ===========================================
# Configuration
# ===========================================

# Paths (loaded from .env if available)
# Save system PATH before .env overrides it
SYSTEM_PATH := $(PATH)
-include .env
# Restore PATH (the .env PATH uses $PATH which doesn't expand in Make)
export PATH := $(SYSTEM_PATH)

ORCH_DIR        := $(CURDIR)
PROCFILE        ?= $(ORCH_DIR)/Procfile.dev
OVERMIND_SOCK   ?= $(ORCH_DIR)/.overmind-dev.sock
export PROCFILE OVERMIND_SOCK ORCH_DIR
ZEPHYR_CLI      := $(or $(wildcard tools/zephyr-cli/cli),$(ZEPHYR_REPO_PATH)/tools/zephyr-cli/cli)

# Zephyr base compose files (from Zephyr repo)
ZEPHYR_BASE   := $(ZEPHYR_REPO_PATH)/docker/compose.yml
ZEPHYR_PUBLIC := $(ZEPHYR_REPO_PATH)/docker/compose.public.yml

# Bridge-orch compose files
COMPOSE_BRIDGE := docker/compose.bridge.yml
COMPOSE_ENGINE := docker/compose.engine.yml
COMPOSE_DEV    := docker/compose.dev.yml
COMPOSE_BS     := docker/compose.blockscout.yml
COMPOSE_V2     := docker/compose.testnet-v2.yml
COMPOSE_V3     := docker/compose.testnet-v3.yml
COMPOSE_PROD   := docker/compose.prod.yml

# Guard: verify Zephyr base exists
$(if $(wildcard $(ZEPHYR_BASE)),,$(warning Zephyr compose.yml not found at $(ZEPHYR_BASE). Check ZEPHYR_REPO_PATH in .env))

# Compose commands (Blockscout always in chain — profiled, won't start unless activated)
DC_DEV := docker compose -p bridge-orch --env-file .env \
  -f $(ZEPHYR_BASE) -f $(COMPOSE_BRIDGE) -f $(COMPOSE_ENGINE) \
  -f $(COMPOSE_DEV) -f $(COMPOSE_BS)

DC_V2 := docker compose -p bridge-orch --env-file .env \
  -f $(ZEPHYR_BASE) -f $(ZEPHYR_PUBLIC) -f $(COMPOSE_BRIDGE) -f $(COMPOSE_ENGINE) \
  -f $(COMPOSE_V2) -f $(COMPOSE_BS)

DC_V3 := docker compose -p bridge-v3 --env-file .env \
  -f $(ZEPHYR_BASE) -f $(ZEPHYR_PUBLIC) -f $(COMPOSE_BRIDGE) -f $(COMPOSE_ENGINE) \
  -f $(COMPOSE_V3)

# ===========================================
# Build
# ===========================================

.PHONY: setup reset keygen build build-zephyr build-oracle build-orderbook build-init sync-zephyr docs-dashboard docs-dashboard-check

## One-time setup: check prereqs, clone repos, install deps
setup:
	./scripts/setup.sh

## Full reset: dev-delete + remove cloned repos (interactive)
reset:
	@$(MAKE) dev-delete
	@PARENT="$(dir $(ORCH_DIR))"; \
	REPOS=""; \
	for dir in zephyr zephyr-bridge zephyr-bridge-engine zephyr-eth-foundry; do \
		if [ -d "$$PARENT/$$dir" ]; then \
			REPOS="$$REPOS  $$PARENT/$$dir\n"; \
		fi; \
	done; \
	if [ -z "$$REPOS" ]; then \
		echo "No sibling repos found to remove."; \
	else \
		echo ""; \
		echo "The following repos will be permanently deleted:"; \
		echo -e "$$REPOS"; \
		printf "Continue? [y/N] "; \
		read -r ans; \
		case "$$ans" in \
			[yY]) \
				for dir in zephyr zephyr-bridge zephyr-bridge-engine zephyr-eth-foundry; do \
					if [ -d "$$PARENT/$$dir" ]; then \
						echo "  Removing $$PARENT/$$dir..."; \
						rm -rf "$$PARENT/$$dir"; \
					fi; \
				done; \
				echo "=== Reset complete ===" ;; \
			*) echo "Aborted." ;; \
		esac; \
	fi

## Generate fresh keys and write to .env
keygen:
	./scripts/keygen.py --write-env

## Build all Docker images
build: build-zephyr build-oracle build-orderbook build-init

## Build Zephyr node/wallet image (uses vendored binaries)
## Usage: make build-zephyr [DEVNET_MODE=mirror]
build-zephyr:
	@BIN_DIR=$$([ "$(DEVNET_MODE)" = "mirror" ] && echo "docker/zephyr/bin-mirror" || echo "docker/zephyr/bin"); \
	echo "=== Building zephyr-devnet image ($$BIN_DIR) ==="; \
	if [ ! -f "$$BIN_DIR/zephyrd" ]; then \
		echo "Error: zephyrd not found at $$BIN_DIR/zephyrd"; \
		echo "Run: ./scripts/sync-zephyr-artifacts.sh"; \
		exit 1; \
	fi; \
	docker build --build-arg BIN_DIR=$$BIN_DIR -f docker/zephyr/Dockerfile -t zephyr-devnet .

## Build fake oracle image (uses vendored oracle files)
build-oracle:
	@echo "=== Building zephyr-fake-oracle image ==="
	@if [ ! -f "docker/fake-oracle/server.js" ]; then \
		echo "Error: oracle files not found. Run: ./scripts/sync-zephyr-artifacts.sh"; \
		exit 1; \
	fi
	docker build -t zephyr-fake-oracle docker/fake-oracle/

## Generate dashboard API docs from route meta
docs-dashboard:
	node status-dashboard/scripts/generate-api-doc.mjs

## CI check: all routes have meta + docs are up to date
docs-dashboard-check:
	@node status-dashboard/scripts/generate-api-doc.mjs
	@if ! git diff --quiet docs/dashboard-api.md 2>/dev/null; then \
		echo ""; \
		echo "ERROR: docs/dashboard-api.md is out of date."; \
		echo "Run 'make docs-dashboard' and commit the result."; \
		echo ""; \
		git diff --stat docs/dashboard-api.md; \
		exit 1; \
	fi
	@echo "Dashboard API docs are up to date."

## Sync all artifacts from Zephyr repo
sync-zephyr:
	./scripts/sync-zephyr-artifacts.sh

## Build fake orderbook image
build-orderbook:
	@echo "=== Building zephyr-fake-orderbook image ==="
	docker build -t zephyr-fake-orderbook -f docker/fake-orderbook/Dockerfile services/fake-orderbook/

## Build devnet-init image (context = repo root so it can COPY tools/zephyr-cli + utils/python-rpc)
build-init:
	@echo "=== Building zephyr-devnet-init image ==="
	docker build -t zephyr-devnet-init -f docker/devnet-init/Dockerfile .

# ===========================================
# Dev Environment
# ===========================================

.PHONY: dev dev-start dev-init dev-init-mirror dev-setup dev-delete dev-apps dev-stop dev-explorer dev-reset dev-reset-hard dev-checkpoint status logs clean seed-engine scan-pools

## Start the stack (no init, no setup — just start)
dev: dev-start
dev-start:
	@if [ ! -f .env ]; then \
		echo "ERROR: .env not found. Run: make keygen"; \
		exit 1; \
	fi
	@if grep -q '<KEYGEN:' .env 2>/dev/null; then \
		echo "ERROR: .env contains unresolved <KEYGEN:> placeholders."; \
		echo "Run: make keygen"; \
		exit 1; \
	fi
	@# Check prerequisites
	@if ! docker volume ls -q --filter name=zephyr-checkpoint | grep -q .; then \
		echo "ERROR: Chain not initialized. Run: make dev-init"; \
		exit 1; \
	fi
	@if [ ! -f config/addresses.json ]; then \
		echo "ERROR: Contracts not deployed. Run: make dev-setup"; \
		exit 1; \
	fi
	@# Clean stale Overmind socket if process is dead
	@if [ -S "$(OVERMIND_SOCK)" ] && ! overmind status -s $(OVERMIND_SOCK) >/dev/null 2>&1; then \
		echo "Cleaning stale Overmind socket..."; \
		rm -f $(OVERMIND_SOCK); \
	fi
	@# Start infrastructure (Blockscout on by default, EXPLORER=0 to skip)
	@echo "=== Starting Docker infrastructure ==="
	@if [ "$(EXPLORER)" = "0" ]; then \
		$(DC_DEV) up -d; \
	else \
		$(DC_DEV) --profile explorer up -d; \
	fi
	@# Anvil loads state via --load-state CLI (entrypoint wrapper checks for snapshot file)
	@# Open wallets (wallet RPCs don't auto-load after container restart)
	@./scripts/open-wallets.sh
	@# Mining is NOT auto-started. Use: $(ZEPHYR_CLI) mine start --threads 2
	@# Push database schemas (idempotent — applies any pending migrations)
	@cd $(BRIDGE_REPO_PATH)/packages/db && DATABASE_URL=$(DATABASE_URL_BRIDGE) npx prisma db push 2>&1 | tail -1
	@cd $(ENGINE_REPO_PATH) && DATABASE_URL=$(DATABASE_URL_ENGINE) pnpm prisma db push --schema=src/infra/prisma/schema.prisma --skip-generate 2>&1 | tail -1
	@# Start apps
	@$(MAKE) dev-apps APPS=$(APPS)
	@echo ""
	@echo "=== Dev stack running ==="
	@if [ -n "$(APPS)" ]; then echo "  Apps: $(APPS)"; fi
	@echo "  Bridge UI:  http://localhost:7050"
	@echo "  Bridge API: http://localhost:7051"
	@echo "  Engine:     http://localhost:7000"
	@echo "  Dashboard:  http://localhost:7100"
	@if [ "$(EXPLORER)" != "0" ]; then echo "  Explorer:   http://localhost:4000"; fi

## Base Zephyr devnet init, then stop (~4 min). Use DEVNET_MODE=mirror for mainnet supply.
dev-init:
	@if [ ! -f .env ]; then \
		echo "ERROR: .env not found. Run: make keygen"; \
		exit 1; \
	fi
	@if grep -q '<KEYGEN:' .env 2>/dev/null; then \
		echo "ERROR: .env contains unresolved <KEYGEN:> placeholders."; \
		echo "Run: make keygen"; \
		exit 1; \
	fi
	@echo "=== Dev Init — Base Zephyr Devnet ==="
	@# 1. Stop Overmind
	@if [ -S "$(OVERMIND_SOCK)" ]; then \
		echo "  Stopping Overmind..."; \
		overmind quit -s $(OVERMIND_SOCK) 2>/dev/null || true; \
		for i in $$(seq 1 10); do [ ! -S "$(OVERMIND_SOCK)" ] && break; sleep 0.5; done; \
	fi
	@rm -f $(OVERMIND_SOCK)
	@# 2. Tear down containers + volumes
	@echo "  Removing containers and volumes..."
	@$(DC_DEV) --profile explorer down -v 2>/dev/null || true
	@# Also remove any orphaned volumes (handles project-name mismatches)
	@docker volume ls -q --filter name=zephyr- | xargs -r docker volume rm 2>/dev/null || true
	@docker volume ls -q --filter name=orch- | xargs -r docker volume rm 2>/dev/null || true
	@# Legacy volumes (pre-migration prefixes)
	@docker volume ls -q --filter name=bridge-redis | xargs -r docker volume rm 2>/dev/null || true
	@docker volume ls -q --filter name=bridge-postgres | xargs -r docker volume rm 2>/dev/null || true
	@docker volume ls -q --filter name=bridge-anvil | xargs -r docker volume rm 2>/dev/null || true
	@docker volume ls -q --filter name=bridge-blockscout | xargs -r docker volume rm 2>/dev/null || true
	@docker volume ls -q --filter name=docker_ | xargs -r docker volume rm 2>/dev/null || true
	@# 3. Preflight: check for leftover containers and port conflicts
	@CONFLICTS=""; STALE_IDS=""; \
	for cname in $$($(DC_DEV) --profile explorer config 2>/dev/null | grep 'container_name:' | awk '{print $$2}'); do \
		cid=$$(docker ps -aq --filter "name=^/$${cname}$$" 2>/dev/null | head -1); \
		if [ -n "$$cid" ]; then \
			CONFLICTS="$$CONFLICTS  container $$cname ($$cid)\n"; \
			STALE_IDS="$$STALE_IDS $$cid"; \
		fi; \
	done; \
	for port in $$($(DC_DEV) --profile explorer config 2>/dev/null | grep 'published:' | sed 's/.*published: *"\?\([0-9]*\)"\?.*/\1/' | sort -n | uniq); do \
		owner=$$(docker ps --format '{{.ID}} {{.Names}}' --filter "publish=$$port" 2>/dev/null | head -1); \
		if [ -n "$$owner" ]; then \
			oid=$$(echo "$$owner" | awk '{print $$1}'); \
			oname=$$(echo "$$owner" | awk '{print $$2}'); \
			CONFLICTS="$$CONFLICTS  port $$port ← container $$oname ($$oid)\n"; \
			echo "$$STALE_IDS" | grep -q "$$oid" || STALE_IDS="$$STALE_IDS $$oid"; \
		elif ss -tlnH 2>/dev/null | awk '{print $$4}' | grep -q ":$$port$$"; then \
			pid=$$(ss -tlnpH 2>/dev/null | grep ":$$port " | head -1 | sed 's/.*pid=\([0-9]*\).*/\1/'); \
			pname=$$(ps -p "$$pid" -o comm= 2>/dev/null); \
			CONFLICTS="$$CONFLICTS  port $$port ← process $${pname:-pid $$pid}\n"; \
		fi; \
	done; \
	if [ -n "$$CONFLICTS" ]; then \
		echo ""; \
		echo "ERROR: Conflicts remain after teardown:"; \
		echo -e "$$CONFLICTS"; \
		if [ -n "$$STALE_IDS" ]; then \
			echo "Fix: docker rm -f$$STALE_IDS && make dev-init"; \
		else \
			echo "Fix: stop the process(es) above, then re-run make dev-init"; \
		fi; \
		exit 1; \
	fi
	@# 4. Remove stale addresses (setup not done yet)
	@rm -f config/addresses.json deployed-addresses.json
	@# 4. Rebuild images (pass DEVNET_MODE for mirror binary selection)
	@$(MAKE) build DEVNET_MODE=$(or $(DEVNET_MODE),custom)
	@# 5. Start infrastructure
	@echo ""
	@echo "=== Starting Docker infrastructure ==="
	@$(DC_DEV) up -d
	@# 6. Wait for Postgres + push schemas
	@echo ""
	@echo "  Waiting for Postgres..."
	@for i in $$(seq 1 30); do $(DC_DEV) exec -T postgres pg_isready -U postgres >/dev/null 2>&1 && break; sleep 0.5; done
	@echo "=== Pushing database schemas ==="
	@cd $(BRIDGE_REPO_PATH)/packages/db && DATABASE_URL=$(DATABASE_URL_BRIDGE) npx prisma db push 2>&1 | tail -1
	@cd $(ENGINE_REPO_PATH) && DATABASE_URL=$(DATABASE_URL_ENGINE) pnpm prisma db push --schema=src/infra/prisma/schema.prisma --skip-generate 2>&1 | tail -1
	@# 7. Run devnet init (CLI-based: gov/miner/test wallets only)
	@echo ""
	@echo "=== Initializing DEVNET (mode: $(or $(DEVNET_MODE),custom)) ==="
	@docker rm zephyr-devnet-init 2>/dev/null || true
	@DEVNET_MODE=$(or $(DEVNET_MODE),custom) $(DC_DEV) --profile init up devnet-init
	@# 8. Stop daemons + save LMDB snapshots (must be stopped for consistent LMDB copy)
	@echo ""
	@echo "=== Saving chain snapshots ==="
	@mkdir -p snapshots/chain
	@echo "$(or $(DEVNET_MODE),custom)" > snapshots/chain/mode
	@$(DC_DEV) stop zephyr-node1 zephyr-node2
	@docker run --rm -v zephyr-node1-data:/data alpine tar czf - -C /data --exclude='lmdb/lock.mdb' lmdb > snapshots/chain/node1-lmdb.tar.gz
	@docker run --rm -v zephyr-node2-data:/data alpine tar czf - -C /data --exclude='lmdb/lock.mdb' lmdb > snapshots/chain/node2-lmdb.tar.gz
	@echo "  Snapshots saved ($$(du -sh snapshots/chain/ | cut -f1))"
	@# 9. Stop everything (volumes persist)
	@echo ""
	@echo "=== Stopping infrastructure ==="
	@$(DC_DEV) --profile explorer down
	@echo ""
	@echo "=== Dev init complete (mode: $(or $(DEVNET_MODE),custom), everything stopped) ==="
	@echo "  Next: make dev-setup"

## Init in mirror mode (convenience for: make dev-init DEVNET_MODE=mirror)
dev-init-mirror:
	$(MAKE) dev-init DEVNET_MODE=mirror

## Bridge infrastructure setup on top of dev-init, then stop (~4 min)
dev-setup:
	@if [ ! -f .env ]; then \
		echo "ERROR: .env not found. Run: make keygen"; \
		exit 1; \
	fi
	./scripts/dev-setup.sh

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
	@# Sync env vars to sub-repos before starting (keygen passwords, etc.)
	@if [ ! -S "$(OVERMIND_SOCK)" ]; then \
		./scripts/sync-env.sh; \
	fi
	@if [ -S "$(OVERMIND_SOCK)" ]; then \
		echo "  Overmind already running"; \
	elif [ -n "$(APPS)" ]; then \
		FORM="bridge-web=0,bridge-api=0,bridge-watchers=0,engine-web=0,engine-watchers=0,engine-run=0,dashboard=0"; \
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
	$(DC_DEV) --profile explorer down
	@echo "=== Stopped ==="

## Start Blockscout explorer (infra must be running)
dev-explorer:
	@echo "=== Starting Blockscout explorer ==="
	$(DC_DEV) --profile explorer up -d blockscout-db blockscout-backend blockscout-frontend blockscout-proxy
	@echo "  Explorer: http://localhost:4000"

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
	@$(DC_DEV) --profile explorer down -v 2>/dev/null || true
	@docker rm zephyr-devnet-init 2>/dev/null || true
	@# Remove orphaned volumes (handles project-name mismatches)
	@docker volume ls -q --filter name=zephyr- | xargs -r docker volume rm 2>/dev/null || true
	@docker volume ls -q --filter name=orch- | xargs -r docker volume rm 2>/dev/null || true
	@# Legacy volumes (pre-migration prefixes)
	@docker volume ls -q --filter name=bridge-redis | xargs -r docker volume rm 2>/dev/null || true
	@docker volume ls -q --filter name=bridge-postgres | xargs -r docker volume rm 2>/dev/null || true
	@docker volume ls -q --filter name=bridge-anvil | xargs -r docker volume rm 2>/dev/null || true
	@docker volume ls -q --filter name=bridge-blockscout | xargs -r docker volume rm 2>/dev/null || true
	@docker volume ls -q --filter name=docker_ | xargs -r docker volume rm 2>/dev/null || true
	@# Remove local state files
	@rm -f config/addresses.json deployed-addresses.json
	@# Remove built images
	@echo "  Removing Docker images..."
	@docker rmi zephyr-devnet zephyr-fake-oracle zephyr-fake-orderbook zephyr-devnet-init 2>/dev/null || true
	@echo "=== Deleted ==="

## Reset to post-setup state, then stop (~15 sec)
dev-reset:
	./scripts/dev-reset.sh

## Reset to post-init state, then stop (~10 sec)
dev-reset-hard:
	./scripts/dev-reset.sh --hard

## Save current height as checkpoint
dev-checkpoint:
	@echo "=== Saving checkpoint ==="
	@HEIGHT=$$($(ZEPHYR_CLI) height) && \
	$(DC_DEV) exec -T wallet-gov sh -c "echo $$HEIGHT > /checkpoint/height" && \
	echo "  Checkpoint saved at height: $$HEIGHT"

## Post-setup sanity check (usage: make sanity-check [PRICE=1.50])
sanity-check:
	@python3 ./scripts/sanity-check-post-setup-state.py $(if $(PRICE),--price $(PRICE),)

## Check health of all services and pipeline state
status:
	@./scripts/status.sh

## Tail logs for a service (usage: make logs SERVICE=zephyr-node1)
logs:
	$(DC_DEV) logs -f $(SERVICE)

# ===========================================
# Oracle / Scenario Control
# ===========================================

.PHONY: set-price set-scenario set-ma set-ma-mode supply-sync supply-status fund

## Set oracle price (usage: make set-price PRICE=1.50)
set-price:
	@if [ -z "$(PRICE)" ]; then echo "Usage: make set-price PRICE=<usd>"; exit 1; fi
	@$(ZEPHYR_CLI) price $(PRICE)

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
	echo "Setting scenario '$(SCENARIO)': price=$${PRICE} USD, spread=$${SPREAD}bps" && \
	$(ZEPHYR_CLI) price $$PRICE && \
	curl -sf -X POST http://localhost:5556/set-spread \
		-H 'Content-Type: application/json' \
		-d "{\"spreadBps\": $$SPREAD}" | jq . 2>/dev/null || true

## Set oracle moving average (usage: make set-ma MA=1.50)
set-ma:
	@if [ -z "$(MA)" ]; then echo "Usage: make set-ma MA=<usd>"; exit 1; fi
	@$(ZEPHYR_CLI) oracle ma $(MA)

## Set oracle MA mode (usage: make set-ma-mode MA_MODE=ema [EMA_ALPHA=0.05])
set-ma-mode:
	@if [ -z "$(MA_MODE)" ]; then echo "Usage: make set-ma-mode MA_MODE=spot|manual|ema|mirror [EMA_ALPHA=0.1]"; exit 1; fi
	@$(ZEPHYR_CLI) oracle ma-mode $(MA_MODE) $(if $(EMA_ALPHA),--alpha $(EMA_ALPHA),)

## Enable supply sync mode (mirrors mainnet supply via gov wallet)
supply-sync:
	@$(ZEPHYR_CLI) oracle supply-sync

## Check supply sync state
supply-status:
	@$(ZEPHYR_CLI) oracle supply-status

## Fund a wallet (usage: make fund WALLET=test AMOUNT=1000 ASSET=ZPH)
fund:
	@$(ZEPHYR_CLI) send gov $(or $(WALLET),test) $(or $(AMOUNT),1000) $(or $(ASSET),ZPH)

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

## Seed liquidity via engine's native pool seeder
seed-engine:
	./scripts/seed-via-engine.sh

## Seed liquidity via legacy Python script (fallback)
seed-engine-legacy:
	./scripts/seed-liquidity.py

## Trigger bridge-api pool scan (discovers Uniswap V4 pools)
scan-pools:
	@curl -sf -X POST http://localhost:7051/admin/uniswap/v4/scan \
		-H "Content-Type: application/json" \
		-H "x-admin-token: $(ADMIN_TOKEN)" \
		-d '{}' | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  Scanned: {len(d.get(\"pools\",[]))} pools')"

# ===========================================
# Test Framework
# ===========================================

.PHONY: test test-l1 test-l2 test-l3 test-l4 test-l1-l2 test-l3-l4 test-l5 test-l5-lint test-l5-summary test-l5-browser-preflight test-l5-execute test-l5-execute-all test-l5-sec test-l5-runtime test-l5-infra test-l5-asset test-l5-stress test-l5-fe test-l5-seed test-engine test-engine-verbose typecheck-tests

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
	@mkdir -p reports
	./scripts/run-l5-tests.py --execute --report-json reports/l5-execution-report.json

## L5 execution pass including TBC baseline checks
test-l5-execute-all:
	@mkdir -p reports
	./scripts/run-l5-tests.py --execute --execute-tbc --report-json reports/l5-execution-report.json

## L5.1 Security & Contracts (SEC + SC)
test-l5-sec:
	./scripts/run-l5-tests.py --execute --sublevel L5.1 --verbose

## L5.2 Runtime & Consistency (CONS + RR + CONC + SEED)
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

## SEED checks (part of L5.2, also runnable standalone)
test-l5-seed:
	./scripts/run-l5-tests.py --execute --category SEED --verbose

## Run engine strategy tests (332 tests)
test-engine:
	python3 scripts/engine_tests/runner.py

## Run engine tests verbose
test-engine-verbose:
	python3 scripts/engine_tests/runner.py --verbose

## Type-check test suite with pyright
typecheck-tests:
	pyright

# ===========================================
# Cleanup
# ===========================================

.PHONY: clean

## Alias for dev-delete
clean: dev-delete

# ===========================================
# Testnet V2 (Production Build Mode)
# ===========================================
# Same infra as dev, but apps run from production builds (pnpm build -> pnpm start).
# Uses Procfile.prod + separate Overmind socket so it can't coexist with dev.

.PHONY: testnet-v2-build testnet-v2-init testnet-v2-setup testnet-v2 testnet-v2-stop testnet-v2-reset testnet-v2-reset-hard testnet-v2-delete testnet-v2-logs

PROD_PROCFILE := $(ORCH_DIR)/Procfile.prod
PROD_SOCK     := $(ORCH_DIR)/.overmind-prod.sock

## Build all apps for production (pnpm build)
testnet-v2-build:
	@echo "=== Syncing env files ==="
	./scripts/sync-env.sh
	@echo "=== Building bridge ==="
	source scripts/lib/env.sh && load_env .env && load_env "$(BRIDGE_REPO_PATH)/.env.local" && cd "$(BRIDGE_REPO_PATH)" && pnpm build
	@echo "=== Building engine ==="
	source scripts/lib/env.sh && load_env .env && cd "$(ENGINE_REPO_PATH)" && pnpm build:web
	@echo "=== Building dashboard ==="
	source scripts/lib/env.sh && load_env .env && cd "$(ORCH_DIR)/status-dashboard" && pnpm build

## Init base Zephyr devnet (same as dev-init)
testnet-v2-init:
	$(MAKE) dev-init

## Setup bridge infra with production Procfile
testnet-v2-setup:
	$(MAKE) dev-setup PROCFILE=$(PROD_PROCFILE) OVERMIND_SOCK=$(PROD_SOCK)

## Start stack with production builds
testnet-v2:
	$(MAKE) dev PROCFILE=$(PROD_PROCFILE) OVERMIND_SOCK=$(PROD_SOCK) APPS=$(APPS) EXPLORER=$(EXPLORER)

## Stop testnet V2 stack
testnet-v2-stop:
	$(MAKE) dev-stop OVERMIND_SOCK=$(PROD_SOCK)

## Reset to post-setup state
testnet-v2-reset:
	$(MAKE) dev-reset PROCFILE=$(PROD_PROCFILE) OVERMIND_SOCK=$(PROD_SOCK)

## Reset to post-init state
testnet-v2-reset-hard:
	$(MAKE) dev-reset-hard PROCFILE=$(PROD_PROCFILE) OVERMIND_SOCK=$(PROD_SOCK)

## Delete all testnet V2 state
testnet-v2-delete:
	$(MAKE) dev-delete OVERMIND_SOCK=$(PROD_SOCK)

## Tail testnet V2 logs
testnet-v2-logs:
	$(MAKE) logs SERVICE=$(SERVICE)

# ===========================================
# Testnet V3 (Sepolia)
# ===========================================

.PHONY: testnet-v3-build testnet-v3-up testnet-v3-down testnet-v3-logs

## Build testnet V3 Docker images
testnet-v3-build: build
	@echo "=== Building app images ==="
	docker build -t zephyr-bridge-web --target web -f docker/bridge/Dockerfile $(BRIDGE_REPO_PATH)
	docker build -t zephyr-bridge-api --target api -f docker/bridge/Dockerfile $(BRIDGE_REPO_PATH)
	docker build -t zephyr-bridge-watchers --target watchers -f docker/bridge/Dockerfile $(BRIDGE_REPO_PATH)
	docker build -t zephyr-engine-web --target web -f docker/engine/Dockerfile $(ENGINE_REPO_PATH)
	docker build -t zephyr-engine-watchers --target watchers -f docker/engine/Dockerfile $(ENGINE_REPO_PATH)
	docker build -t zephyr-dashboard -f docker/dashboard/Dockerfile status-dashboard/

## Start testnet V3 stack (usage: make testnet-v3-up APPS=bridge)
testnet-v3-up:
	@if [ -n "$(APPS)" ]; then \
		PROFILES=""; \
		IFS=','; for grp in $(APPS); do \
			case $$grp in \
				bridge|engine|full) PROFILES="$$PROFILES --profile $$grp" ;; \
				dashboard) PROFILES="$$PROFILES --profile full"; echo "Note: dashboard only available in 'full' profile" ;; \
				*) echo "Error: Unknown app group '$$grp'. Valid: bridge, engine, full"; exit 1 ;; \
			esac; \
		done; \
		$(DC_V3) $$PROFILES up -d; \
	elif [ -n "$(PROFILE)" ]; then \
		$(DC_V3) --profile $(PROFILE) up -d; \
	else \
		$(DC_V3) --profile full up -d; \
	fi

## Stop testnet V3 stack
testnet-v3-down:
	$(DC_V3) down

## Tail testnet V3 logs
testnet-v3-logs:
	$(DC_V3) logs -f $(SERVICE)

# ===========================================
# Help
# ===========================================

.PHONY: help

## Show this help
help:
	@echo "Zephyr Bridge Stack"
	@echo ""
	@echo "First-time setup:"
	@echo "  make setup                      Check prereqs, clone repos, install deps"
	@echo "  make keygen                     Generate fresh EVM keys → .env"
	@echo "  make reset                      Full reset: dev-delete + remove cloned repos"
	@echo ""
	@echo "Dev workflow (staged setup):"
	@echo "  make dev-init                   Base Zephyr devnet, then stop (~4 min)"
	@echo "  make dev-init-mirror            Init with mainnet-like supply (~8-15 min)"
	@echo "  make dev-setup                  Bridge infra on top, then stop (~4 min)"
	@echo "  make dev                        Start the stack (~10 sec)"
	@echo "  make dev APPS=bridge            Start specific app groups (bridge,engine,dashboard)"
	@echo "  make dev EXPLORER=0             Skip Blockscout explorer"
	@echo "  make dev-stop                   Stop everything (preserves data)"
	@echo ""
	@echo "Reset:"
	@echo "  make dev-reset                  Reset to post-setup state, then stop (~15 sec)"
	@echo "  make dev-reset-hard             Reset to post-init state, then stop (~10 sec)"
	@echo ""
	@echo "Lifecycle:"
	@echo "  make dev-delete                 Delete everything (containers, volumes, images)"
	@echo "  make dev-checkpoint             Save current height as checkpoint"
	@echo "  make dev-explorer               Start Blockscout (infra must be running)"
	@echo "  make status                     Check health of all services"
	@echo "  make logs SERVICE=x             Tail logs for a Docker service"
	@echo ""
	@echo "Oracle/Scenario:"
	@echo "  make set-price PRICE=1.50"
	@echo "  make set-scenario SCENARIO=crisis"
	@echo "  make set-ma MA=1.20             Set oracle moving average"
	@echo "  make set-ma-mode MA_MODE=ema    Set MA mode (spot|manual|ema|mirror)"
	@echo "  make supply-sync                Enable runtime supply sync"
	@echo "  make supply-status              Check supply sync state"
	@echo "  make fund WALLET=test AMOUNT=1000 ASSET=ZPH"
	@echo ""
	@echo "Testnet V2 (Production Build Mode):"
	@echo "  make testnet-v2-build           Build all apps (pnpm build)"
	@echo "  make testnet-v2-init            Init base devnet (same as dev-init)"
	@echo "  make testnet-v2-setup           Setup bridge infra"
	@echo "  make testnet-v2                 Start stack with production builds"
	@echo "  make testnet-v2 APPS=bridge     Start specific app groups"
	@echo "  make testnet-v2-stop            Stop everything"
	@echo "  make testnet-v2-reset           Reset to post-setup state"
	@echo "  make testnet-v2-reset-hard      Reset to post-init state"
	@echo "  make testnet-v2-delete          Delete everything"
	@echo "  make testnet-v2-logs SERVICE=x  Tail logs"
	@echo ""
	@echo "Testnet V3 (Sepolia):"
	@echo "  make testnet-v3-build           Build all app images"
	@echo "  make testnet-v3-up              Start full stack"
	@echo "  make testnet-v3-up APPS=bridge  Start specific app groups"
	@echo "  make testnet-v3-down            Stop everything"
	@echo "  make testnet-v3-logs SERVICE=x  Tail logs"
	@echo ""
	@echo "Other:"
	@echo "  make deploy-contracts           Deploy EVM contracts"
	@echo "  make seed-engine                Seed liquidity via bridge wrap flow"
	@echo "  make scan-pools                 Trigger bridge-api pool scan"
	@echo "  make keygen                     Generate fresh keys and write to .env"
	@echo "  make sync-env                   Sync .env to sub-repos"
	@echo "  make sync-zephyr                Copy artifacts from Zephyr repo"
	@echo "  make test                       Run all L1-L4 tests"
	@echo "  make test-l5                    Run L5 edge framework pass"
