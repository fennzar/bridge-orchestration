import { NextResponse } from "next/server";
import { OVERMIND_PROCESSES } from "@/lib/constants";
import type { AppStatus, AppsResponse } from "@/lib/types";
import { getOvmStatus, getProcessLogs } from "@/lib/overmind";

export const dynamic = "force-dynamic";

export async function GET() {
  const ovmStatuses = await getOvmStatus();

  const processes: AppStatus[] = await Promise.all(
    OVERMIND_PROCESSES.map(async (proc) => {
      const status = ovmStatuses.get(proc.name) ?? "stopped";
      const logs = status === "running" ? await getProcessLogs(proc.name) : [];

      return {
        name: proc.name,
        status,
        port: proc.port,
        group: proc.group,
        logs,
      };
    })
  );

  const response: AppsResponse = {
    processes,
    timestamp: new Date().toISOString(),
  };

  return NextResponse.json(response);
}
