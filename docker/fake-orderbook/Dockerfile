# Fake MEXC-compatible orderbook that tracks fake oracle price
#
# Source: services/fake-orderbook/ in bridge-orchestration repo

FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm ci --production 2>/dev/null || npm install --production

COPY . .

ENV FAKE_ORDERBOOK_PORT=5556
ENV FAKE_ORACLE_URL=http://fake-oracle:5555

EXPOSE 5556

HEALTHCHECK --interval=5s --timeout=3s --retries=5 --start-period=3s \
  CMD wget -qO- http://127.0.0.1:5556/status || exit 1

CMD ["node", "index.js"]
