import { NextResponse } from "next/server";
import { stopAllProcesses } from "@/lib/overmind";
import type { RouteMeta } from "@/lib/route-meta";

export const meta: RouteMeta = {
  title: "Stop All Apps",
  category: "Apps",
  description: "Stop all Overmind-managed app processes.",
  response: [
    { name: "success", type: "boolean", required: true, description: "Whether all processes were stopped" },
  ],
  curl: "curl -X POST localhost:7100/api/apps/stop",
};

export const dynamic = "force-dynamic";

export async function POST() {
  const success = await stopAllProcesses();
  if (!success) {
    return NextResponse.json(
      { success: false, error: "Failed to stop processes" },
      { status: 500 }
    );
  }
  return NextResponse.json({ success: true });
}
