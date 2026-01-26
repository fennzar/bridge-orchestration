# Status Dashboard - Next.js standalone
#
# Build context: bridge-orchestration/status-dashboard/
#
# Usage:
#   docker build -t zephyr-dashboard -f docker/dashboard/Dockerfile status-dashboard/

FROM node:22-alpine AS base
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate
WORKDIR /app

# --- Dependencies ---
FROM base AS deps
COPY pnpm-lock.yaml package.json ./
RUN pnpm install --frozen-lockfile

# --- Build ---
FROM deps AS build
COPY . .
RUN pnpm build

# --- Production ---
FROM node:22-alpine
WORKDIR /app
COPY --from=build /app/.next/standalone ./
COPY --from=build /app/.next/static .next/static
COPY --from=build /app/public public
ENV PORT=7100
EXPOSE 7100
CMD ["node", "server.js"]
