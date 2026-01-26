# Fake oracle for Zephyr DEVNET - provides signed, controllable price data
#
# Source files are copied from $ZEPHYR_REPO_PATH/tools/fake-oracle/ at build time.
# See Makefile build-oracle target.

FROM node:22-alpine

WORKDIR /app

COPY server.js oracle_private.pem oracle_public.pem ./

ENV ORACLE_PORT=5555

EXPOSE 5555

HEALTHCHECK --interval=5s --timeout=3s --retries=5 --start-period=3s \
  CMD wget -qO- http://127.0.0.1:5555/status || exit 1

CMD ["node", "server.js"]
