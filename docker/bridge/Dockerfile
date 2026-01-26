# Zephyr Bridge - Multi-stage build
#
# Targets:
#   web      - Next.js standalone (bridge UI on port 7050)
#   api      - Express API server (port 7051)
#   watchers - Zephyr/EVM watchers (tsx runtime)
#
# Build context: $BRIDGE_REPO_PATH (zephyr-bridge monorepo)
#
# Usage:
#   docker build --target web -t zephyr-bridge-web .
#   docker build --target api -t zephyr-bridge-api .
#   docker build --target watchers -t zephyr-bridge-watchers .

# --- Base ---
FROM node:22-alpine AS base
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate
WORKDIR /app

# --- Dependencies ---
FROM base AS deps
# Copy workspace config + all package.json files for layer caching
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY apps/web/package.json apps/web/package.json
COPY apps/api/package.json apps/api/package.json
COPY packages/config/package.json packages/config/package.json
COPY packages/core/package.json packages/core/package.json
RUN pnpm install --frozen-lockfile

# --- Build ---
FROM deps AS build
COPY . .
RUN pnpm build

# --- Target: web (Next.js standalone) ---
FROM node:22-alpine AS web
WORKDIR /app
COPY --from=build /app/apps/web/.next/standalone ./
COPY --from=build /app/apps/web/.next/static apps/web/.next/static
COPY --from=build /app/apps/web/public apps/web/public
ENV PORT=7050
EXPOSE 7050
CMD ["node", "apps/web/server.js"]

# --- Target: api (Express) ---
FROM node:22-alpine AS api
WORKDIR /app
COPY --from=build /app/apps/api/dist ./dist
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/apps/api/package.json ./package.json
ENV PORT=7051
EXPOSE 7051
CMD ["node", "dist/index.js"]

# --- Target: watchers (tsx runtime) ---
FROM base AS watchers
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
CMD ["pnpm", "dev:watchers"]
