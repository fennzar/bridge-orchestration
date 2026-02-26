import { NextResponse } from "next/server";
import { DAEMON_PRIMARY_PORT } from "@/lib/constants";
import { zephyrRpc } from "@/lib/rpc";
import { saveCheckpointHeight } from "@/lib/docker";
import type { RouteMeta } from "@/lib/route-meta";

export const meta: RouteMeta = {
  title: "Save Checkpoint",
  category: "Chain",
  description: "Save the current chain height as the checkpoint for fast resets.",
  response: [
    { name: "success", type: "boolean", required: true, description: "Whether checkpoint was saved" },
    { name: "height", type: "number", required: true, description: "Saved chain height" },
  ],
  curl: "curl -X POST localhost:7100/api/chain/checkpoint",
};

export const dynamic = "force-dynamic";

export async function POST() {
  try {
    const info = await zephyrRpc(DAEMON_PRIMARY_PORT, "get_info");
    if (info.error || !info.result) {
      return NextResponse.json(
        { success: false, error: info.error || "Could not get chain info" },
        { status: 500 }
      );
    }

    const height = info.result.height as number;
    if (!height) {
      return NextResponse.json(
        { success: false, error: "Could not determine chain height" },
        { status: 500 }
      );
    }

    const saved = await saveCheckpointHeight(height);
    if (!saved) {
      return NextResponse.json(
        { success: false, error: "Failed to save checkpoint" },
        { status: 500 }
      );
    }

    return NextResponse.json({ success: true, height });
  } catch (err) {
    return NextResponse.json(
      { success: false, error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 }
    );
  }
}
