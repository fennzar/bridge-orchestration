# Zephyr node + wallet-rpc (single image, mode selected via ZEPHYR_MODE env)
#
# Build:
#   Copy binaries into docker/zephyr/bin/ first, then:
#   docker build -t zephyr-devnet docker/zephyr/
#
# Run as node:
#   docker run -e ZEPHYR_MODE=node zephyr-devnet --devnet --rpc-bind-port=47767 ...
#
# Run as wallet:
#   docker run -e ZEPHYR_MODE=wallet zephyr-devnet --rpc-bind-port=48769 ...

FROM ubuntu:24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    libboost-chrono1.83.0 \
    libboost-filesystem1.83.0 \
    libboost-program-options1.83.0 \
    libboost-thread1.83.0 \
    libboost-serialization1.83.0 \
    libzmq5 \
    libsodium23 \
    libreadline8t64 \
    libhidapi-libusb0 \
    libunbound8 \
    libssl3t64 \
    libprotobuf32t64 \
    libusb-1.0-0 \
    libevent-2.1-7t64 \
    libudev1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY bin/zephyrd bin/zephyr-wallet-rpc /usr/local/bin/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh /usr/local/bin/zephyrd /usr/local/bin/zephyr-wallet-rpc

ENV ZEPHYR_MODE=node

ENTRYPOINT ["/entrypoint.sh"]
