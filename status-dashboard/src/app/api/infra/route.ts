import { NextResponse } from "next/server";
import { DOCKER_SERVICES } from "@/lib/constants";
import type { ContainerStatus, InfraResponse } from "@/lib/types";
import { getContainerStatuses } from "@/lib/docker";
import {
  getDaemonInfo,
  getWalletAddress,
  getWalletBalance,
  oracleGet,
  anvilBlockNumber,
} from "@/lib/rpc";

export const dynamic = "force-dynamic";

export async function GET() {
  const containerStatuses = await getContainerStatuses();

  const containers: ContainerStatus[] = await Promise.all(
    DOCKER_SERVICES.map(async (svc) => {
      const info = containerStatuses.get(svc.container);
      const isRunning = info && info.state === "running";

      const base: ContainerStatus = {
        name: svc.name,
        container: svc.container,
        status: isRunning ? "running" : info ? "stopped" : "error",
        port: svc.port,
        type: svc.type,
        health: info?.health,
      };

      // Only query RPC details if container is running
      if (!isRunning) return base;

      switch (svc.type) {
        case "daemon": {
          const daemon = await getDaemonInfo(svc.port);
          if (daemon) {
            base.height = daemon.height;
            base.mining = {
              active: daemon.miningActive ?? false,
              threads: daemon.miningThreads,
              speed: daemon.miningSpeed,
            };
          }
          break;
        }
        case "wallet": {
          const [address, balance] = await Promise.all([
            getWalletAddress(svc.port),
            getWalletBalance(svc.port),
          ]);
          if (address) base.address = address;
          if (balance) base.balance = balance;
          break;
        }
        case "oracle": {
          const price = await oracleGet();
          if (price !== null) base.price = price;
          break;
        }
        case "evm": {
          const blockNum = await anvilBlockNumber();
          if (blockNum !== null) base.blockNumber = blockNum;
          break;
        }
        // "infra" and "orderbook" types: just Docker health status, no extra RPC
        default:
          break;
      }

      return base;
    })
  );

  const response: InfraResponse = {
    containers,
    timestamp: new Date().toISOString(),
  };

  return NextResponse.json(response);
}
