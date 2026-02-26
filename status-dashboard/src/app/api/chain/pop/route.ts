import { NextResponse } from "next/server";
import { DAEMON_PRIMARY_PORT, DAEMON_SECONDARY_PORT } from "@/lib/constants";
import { daemonOtherRpc, zephyrRpc } from "@/lib/rpc";
import type { RouteMeta } from "@/lib/route-meta";

export const meta: RouteMeta = {
  title: "Pop Blocks",
  category: "Chain",
  description: "Pop (revert) blocks from both Zephyr nodes. Used for chain resets.",
  request: [
    { name: "blocks", type: "number", required: true, description: "Number of blocks to pop (1-1000)" },
  ],
  response: [
    { name: "success", type: "boolean", required: true, description: "Whether blocks were popped" },
    { name: "blocksPopped", type: "number", required: true, description: "Number of blocks reverted" },
    { name: "newHeight", type: "number | null", required: true, description: "Chain height after pop" },
  ],
  curl: "curl -X POST localhost:7100/api/chain/pop -H 'Content-Type: application/json' -d '{\"blocks\":10}'",
};

export const dynamic = "force-dynamic";

interface PopRequest {
  blocks: number;
}

export async function POST(request: Request) {
  let body: PopRequest;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { success: false, error: "Invalid JSON body" },
      { status: 400 }
    );
  }

  const { blocks } = body;
  if (!blocks || !Number.isInteger(blocks) || blocks < 1 || blocks > 1000) {
    return NextResponse.json(
      { success: false, error: "blocks must be a positive integer (max 1000)" },
      { status: 400 }
    );
  }

  try {
    // pop_blocks is a REST endpoint, not a JSON-RPC method
    const [primary, secondary] = await Promise.all([
      daemonOtherRpc(DAEMON_PRIMARY_PORT, "pop_blocks", { nblocks: blocks }),
      daemonOtherRpc(DAEMON_SECONDARY_PORT, "pop_blocks", { nblocks: blocks }),
    ]);

    if (primary.error) {
      return NextResponse.json(
        { success: false, error: `Primary node: ${primary.error}` },
        { status: 500 }
      );
    }
    if (secondary.error) {
      return NextResponse.json(
        { success: false, error: `Secondary node: ${secondary.error}` },
        { status: 500 }
      );
    }

    const info = await zephyrRpc(DAEMON_PRIMARY_PORT, "get_info");
    const newHeight = (info.result?.height as number) ?? null;

    return NextResponse.json({
      success: true,
      blocksPopped: blocks,
      newHeight,
    });
  } catch (err) {
    return NextResponse.json(
      { success: false, error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 }
    );
  }
}
