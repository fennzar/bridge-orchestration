import { NextResponse } from "next/server";
import { anvilMine } from "@/lib/rpc";
import type { RouteMeta } from "@/lib/route-meta";

export const meta: RouteMeta = {
  title: "Mine EVM Block",
  category: "Status",
  description: "Mine one or more blocks on Anvil (local EVM only).",
  request: [
    { name: "blocks", type: "number", description: "Number of blocks to mine (default: 1)" },
  ],
  response: [
    { name: "success", type: "boolean", required: true, description: "Whether mining succeeded" },
  ],
  curl: "curl -X POST localhost:7100/api/evm/mine -H 'Content-Type: application/json' -d '{\"blocks\":1}'",
};

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  let blocks = 1;
  try {
    const body = await request.json();
    if (typeof body.blocks === "number" && body.blocks > 0) {
      blocks = Math.floor(body.blocks);
    }
  } catch {
    // No body or invalid JSON — mine 1 block
  }

  const success = await anvilMine(blocks);
  return NextResponse.json({ success });
}
