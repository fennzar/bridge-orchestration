# Zephyr Bridge Engine - Multi-stage build
#
# Targets:
#   web      - Next.js standalone (engine dashboard on port 7000)
#   watchers - MEXC/EVM/Zephyr watchers (tsx runtime)
#
# Build context: $ENGINE_REPO_PATH (zephyr-bridge-engine repo)
#
# Usage:
#   docker build --target web -t zephyr-engine-web .
#   docker build --target watchers -t zephyr-engine-watchers .

# --- Base ---
FROM node:22-alpine AS base
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate
WORKDIR /app

# --- Dependencies ---
FROM base AS deps
COPY pnpm-lock.yaml package.json ./
COPY apps/web/package.json apps/web/package.json
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
ENV PORT=7000
EXPOSE 7000
CMD ["node", "apps/web/server.js"]

# --- Target: watchers (tsx runtime) ---
FROM base AS watchers
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
CMD ["pnpm", "dev:watchers"]
