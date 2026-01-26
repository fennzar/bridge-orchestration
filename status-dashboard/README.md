# Bridge Stack Status Dashboard

Real-time monitoring dashboard for the Zephyr bridge development environment. Shows health status of all services, process logs, and test results.

**URL:** http://localhost:7100

## What It Monitors

- **Infrastructure:** Anvil (EVM chain), Redis, PostgreSQL
- **Zephyr Chain:** Daemon nodes, wallet RPCs, mining status
- **Applications:** Bridge UI/API, Engine, watchers
- **Tests:** L3/L4 automated test results (via `/api/tests`)

## Running

The dashboard is managed by Overmind as part of the bridge stack:

```bash
# Start with full stack
make dev              # Start infra + apps (after init)
make dev-init         # Full DEVNET bootstrap (first time)

# View logs
overmind connect status-dashboard
```

It can also run standalone for development:

```bash
cd status-dashboard
pnpm install
pnpm dev    # http://localhost:7100
```

## Stack

- Next.js 16 (App Router) + React 19
- Tailwind CSS + shadcn/ui (Radix primitives)
- TypeScript

## Key Components

| Component | Purpose |
|-----------|---------|
| `status-dashboard.tsx` | Main layout, service health polling |
| `processes-panel.tsx` | Overmind process list + status |
| `terminal-view.tsx` | Live log viewer for selected process |
| `tests-panel.tsx` | L3/L4 test results display |
| `test-card.tsx` | Individual test scenario card |

## API Routes

| Route | Description |
|-------|-------------|
| `/api/tests` | Returns latest L3/L4 test run results |
