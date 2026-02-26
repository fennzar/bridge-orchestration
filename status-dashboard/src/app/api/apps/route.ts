import { NextResponse } from "next/server";
import { OVERMIND_PROCESSES } from "@/lib/constants";
import type { AppStatus, AppsResponse } from "@/lib/types";
import { getOvmStatus, getProcessLogs } from "@/lib/overmind";
import { checkPortListening, checkHttpHealth, extractErrors } from "@/lib/health";
import type { RouteMeta } from "@/lib/route-meta";

export const meta: RouteMeta = {
  title: "App Processes",
  category: "Status",
  description:
    "Status of all Overmind-managed app processes with recent log lines for running processes.",
  response: [
    { name: "processes", type: "AppStatus[]", required: true, description: "Status and recent logs of each app process" },
    { name: "timestamp", type: "string", required: true, description: "ISO 8601 timestamp" },
  ],
  curl: "curl localhost:7100/api/apps",
};

export const dynamic = "force-dynamic";

export async function GET() {
  const ovmStatuses = await getOvmStatus();

  const processes: AppStatus[] = await Promise.all(
    OVERMIND_PROCESSES.map(async (proc) => {
      const ovmStatus = ovmStatuses.get(proc.name) ?? "stopped";
      const logs = ovmStatus === "running" ? await getProcessLogs(proc.name) : [];

      if (ovmStatus !== "running") {
        return {
          name: proc.name,
          status: "stopped" as const,
          port: proc.port,
          group: proc.group,
          logs,
        };
      }

      // Run health checks in parallel for running processes
      const [portListening, httpOk] = await Promise.all([
        proc.port ? checkPortListening(proc.port) : Promise.resolve(null),
        proc.name === "bridge-api"
          ? checkHttpHealth(proc.port!, "/health")
          : Promise.resolve(null),
      ]);
      const errors = extractErrors(logs);

      const hasError =
        (portListening === false) ||
        (httpOk === false) ||
        errors.length > 0;

      return {
        name: proc.name,
        status: hasError ? ("error" as const) : ("running" as const),
        port: proc.port,
        group: proc.group,
        logs,
        health: { portListening, httpOk, errors },
      };
    })
  );

  const response: AppsResponse = {
    processes,
    timestamp: new Date().toISOString(),
  };

  return NextResponse.json(response);
}
