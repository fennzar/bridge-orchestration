# DEVNET bootstrap container - one-shot init that sets up wallets, mining, and initial state
#
# Replaces fresh-devnet's start.sh + setup-state.sh logic using only curl for RPC calls.
# Runs after all Zephyr services are healthy, then exits.

FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    jq \
    bc \
    && rm -rf /var/lib/apt/lists/*

COPY init.sh /init.sh
RUN chmod +x /init.sh

ENTRYPOINT ["/init.sh"]
