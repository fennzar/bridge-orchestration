import { NextResponse } from "next/server";
import { DOCKER_SERVICES, OVERMIND_PROCESSES, DAEMON_PRIMARY_PORT } from "@/lib/constants";
import type { StatusResponse, LifecycleState, ChainVitals } from "@/lib/types";
import { getContainerStatuses, readCheckpointHeight } from "@/lib/docker";
import { getDaemonInfo, oracleGetStatus, anvilBlockNumber } from "@/lib/rpc";
import { getOvmStatus, isOvermindRunning, getProcessLogs } from "@/lib/overmind";
import { checkPortListening, checkHttpHealth, extractErrors } from "@/lib/health";
import type { RouteMeta } from "@/lib/route-meta";

export const meta: RouteMeta = {
  title: "System Status",
  category: "Status",
  description:
    "High-level system status including lifecycle state, infrastructure/app counts, and chain vitals (height, oracle price, mining, checkpoint).",
  response: [
    { name: "lifecycle", type: '"stopped" | "initializing" | "infra-only" | "degraded" | "running"', required: true, description: "Current system lifecycle state" },
    { name: "infraSummary", type: "{ running: number, total: number }", required: true, description: "Docker container counts" },
    { name: "appsSummary", type: "{ running: number, healthy: number, total: number }", required: true, description: "Overmind process counts with health status" },
    { name: "chain", type: "{ height, oraclePrice, anvilBlock, checkpoint, miningActive }", required: true, description: "Chain vitals" },
    { name: "timestamp", type: "string", required: true, description: "ISO 8601 timestamp" },
  ],
  curl: "curl localhost:7100/api/status",
};

export const dynamic = "force-dynamic";

export async function GET() {
  // Gather all data in parallel
  const [containerStatuses, ovmStatuses, ovmRunning, daemonInfo, oracleStatus, anvilBlock] =
    await Promise.all([
      getContainerStatuses(),
      getOvmStatus(),
      isOvermindRunning(),
      getDaemonInfo(DAEMON_PRIMARY_PORT),
      oracleGetStatus(),
      anvilBlockNumber(),
    ]);

  // Filter optional services (e.g. Blockscout) that aren't present
  const activeDockerServices = DOCKER_SERVICES.filter((svc) => {
    if (!("optional" in svc) || !svc.optional) return true;
    return containerStatuses.has(svc.container);
  });

  // Count running Docker containers
  const infraRunning = activeDockerServices.filter((svc) => {
    const info = containerStatuses.get(svc.container);
    return info && info.state === "running";
  }).length;

  // Count running Overmind processes and check health
  const appsRunning = OVERMIND_PROCESSES.filter((proc) => {
    return ovmStatuses.get(proc.name) === "running";
  }).length;

  // Health checks for running processes (port + HTTP + log errors)
  const healthResults = await Promise.all(
    OVERMIND_PROCESSES.map(async (proc) => {
      if (ovmStatuses.get(proc.name) !== "running") return false;
      const [portOk, httpOk, logs] = await Promise.all([
        proc.port ? checkPortListening(proc.port) : Promise.resolve(true),
        proc.name === "bridge-api"
          ? checkHttpHealth(proc.port!, "/health")
          : Promise.resolve(true),
        getProcessLogs(proc.name),
      ]);
      const errors = extractErrors(logs);
      return portOk && httpOk && errors.length === 0;
    })
  );
  const appsHealthy = healthResults.filter(Boolean).length;

  // Detect checkpoint (saved height inside the gov wallet container)
  const checkpoint = await readCheckpointHeight();

  // Determine lifecycle state
  let lifecycle: LifecycleState;
  if (infraRunning === 0) {
    lifecycle = "stopped";
  } else if (checkpoint === null) {
    lifecycle = "initializing";
  } else if (!ovmRunning) {
    lifecycle = "infra-only";
  } else if (appsHealthy < appsRunning) {
    lifecycle = "degraded";
  } else {
    lifecycle = "running";
  }

  const chain: ChainVitals = {
    height: daemonInfo?.height ?? null,
    oraclePrice: oracleStatus?.price ?? null,
    anvilBlock,
    checkpoint,
    miningActive: daemonInfo?.miningActive ?? false,
  };

  const response: StatusResponse = {
    lifecycle,
    infraSummary: { running: infraRunning, total: activeDockerServices.length },
    appsSummary: { running: appsRunning, healthy: appsHealthy, total: OVERMIND_PROCESSES.length },
    chain,
    timestamp: new Date().toISOString(),
  };

  return NextResponse.json(response);
}
