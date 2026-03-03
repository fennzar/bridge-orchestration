import { NextResponse } from "next/server";
import { DOCKER_SERVICES } from "@/lib/constants";
import type { ContainerStatus, InfraResponse } from "@/lib/types";
import { getContainerStatuses, getContainerLogs } from "@/lib/docker";
import { extractDockerErrors } from "@/lib/health";
import {
  getDaemonInfo,
  getWalletAddress,
  getWalletBalance,
  oracleGetStatus,
  anvilBlockNumber,
} from "@/lib/rpc";
import type { RouteMeta } from "@/lib/route-meta";

export const meta: RouteMeta = {
  title: "Infrastructure",
  category: "Status",
  description:
    "Detailed status of all Docker containers including per-service RPC data (daemon height, wallet balances, oracle price, Anvil block number).",
  response: [
    { name: "containers", type: "ContainerStatus[]", required: true, description: "Status of each Docker service with RPC details (height, mining, balance, price, blockNumber)" },
    { name: "timestamp", type: "string", required: true, description: "ISO 8601 timestamp" },
  ],
  curl: "curl localhost:7100/api/infra",
};

export const dynamic = "force-dynamic";

export async function GET() {
  const containerStatuses = await getContainerStatuses();

  // Filter optional services (e.g. Blockscout) that aren't running
  const activeServices = DOCKER_SERVICES.filter((svc) => {
    if (!("optional" in svc) || !svc.optional) return true;
    return containerStatuses.has(svc.container);
  });

  const containers: ContainerStatus[] = await Promise.all(
    activeServices.map(async (svc) => {
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
          const status = await oracleGetStatus();
          if (status?.price !== null && status?.price !== undefined) base.price = status.price;
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

      // Check recent logs for error patterns
      const logs = await getContainerLogs(svc.name, 50);
      const errors = extractDockerErrors(logs);
      if (errors.length > 0) {
        base.errors = errors;
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
