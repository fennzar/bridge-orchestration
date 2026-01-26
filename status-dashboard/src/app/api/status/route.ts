import { NextResponse } from "next/server";
import { DOCKER_SERVICES, OVERMIND_PROCESSES, DAEMON_PRIMARY_PORT } from "@/lib/constants";
import type { StatusResponse, LifecycleState, ChainVitals } from "@/lib/types";
import { getContainerStatuses, runDC } from "@/lib/docker";
import { getDaemonInfo, oracleGet, anvilBlockNumber } from "@/lib/rpc";
import { getOvmStatus, isOvermindRunning } from "@/lib/overmind";

export const dynamic = "force-dynamic";

export async function GET() {
  // Gather all data in parallel
  const [containerStatuses, ovmStatuses, ovmRunning, daemonInfo, oraclePrice, anvilBlock] =
    await Promise.all([
      getContainerStatuses(),
      getOvmStatus(),
      isOvermindRunning(),
      getDaemonInfo(DAEMON_PRIMARY_PORT),
      oracleGet(),
      anvilBlockNumber(),
    ]);

  // Count running Docker containers
  const infraRunning = DOCKER_SERVICES.filter((svc) => {
    const info = containerStatuses.get(svc.container);
    return info && info.state === "running";
  }).length;

  // Count running Overmind processes
  const appsRunning = OVERMIND_PROCESSES.filter((proc) => {
    return ovmStatuses.get(proc.name) === "running";
  }).length;

  // Detect checkpoint (saved height inside the gov wallet container)
  let checkpoint: number | null = null;
  try {
    const raw = await runDC("exec -T wallet-gov cat /checkpoint/height");
    if (raw) {
      const parsed = parseInt(raw, 10);
      if (!isNaN(parsed)) checkpoint = parsed;
    }
  } catch {
    // checkpoint file does not exist
  }

  // Determine lifecycle state
  let lifecycle: LifecycleState;
  if (infraRunning === 0) {
    lifecycle = "stopped";
  } else if (checkpoint === null) {
    lifecycle = "initializing";
  } else if (!ovmRunning) {
    lifecycle = "infra-only";
  } else {
    lifecycle = "running";
  }

  const chain: ChainVitals = {
    height: daemonInfo?.height ?? null,
    oraclePrice,
    anvilBlock,
    checkpoint,
    miningActive: daemonInfo?.miningActive ?? false,
  };

  const response: StatusResponse = {
    lifecycle,
    infraSummary: { running: infraRunning, total: DOCKER_SERVICES.length },
    appsSummary: { running: appsRunning, total: OVERMIND_PROCESSES.length },
    chain,
    timestamp: new Date().toISOString(),
  };

  return NextResponse.json(response);
}
