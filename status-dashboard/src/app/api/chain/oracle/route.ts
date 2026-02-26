import { NextResponse } from "next/server";
import { oracleSet, oracleGetStatus, oracleSetMode } from "@/lib/rpc";
import type { RouteMeta } from "@/lib/route-meta";

export const meta: RouteMeta = {
  title: "Oracle Price & Mode",
  category: "Chain",
  description: "Get or set the fake oracle price and mode (DEVNET only).",
  request: [
    { name: "price", type: "number", description: "New price in USD (e.g. 15.00)" },
    { name: "action", type: "string", description: "Action to perform: 'set-mode'" },
    { name: "mode", type: "string", description: "Oracle mode: 'manual' or 'mirror' (with action: 'set-mode')" },
  ],
  response: [
    { name: "price", type: "number | null", description: "Current oracle price in USD (GET)" },
    { name: "mode", type: "string", description: "Current oracle mode: 'manual' or 'mirror' (GET)" },
    { name: "mirrorSpot", type: "number", description: "Mainnet spot price when in mirror mode (GET)" },
    { name: "mirrorLastFetch", type: "string", description: "Last mirror fetch timestamp (GET)" },
    { name: "success", type: "boolean", description: "Whether the action succeeded (POST)" },
  ],
  curl: [
    "curl localhost:7100/api/chain/oracle",
    "curl -X POST localhost:7100/api/chain/oracle -H 'Content-Type: application/json' -d '{\"price\":15.00}'",
    "curl -X POST localhost:7100/api/chain/oracle -H 'Content-Type: application/json' -d '{\"action\":\"set-mode\",\"mode\":\"mirror\"}'",
  ],
};

export const dynamic = "force-dynamic";

export async function GET() {
  const status = await oracleGetStatus();
  if (!status) {
    return NextResponse.json({ price: null, mode: "manual" });
  }
  return NextResponse.json({
    price: status.price,
    mode: status.mode,
    mirrorSpot: status.mirrorSpot,
    mirrorLastFetch: status.mirrorLastFetch,
  });
}

export async function POST(request: Request) {
  let body: { price?: number; action?: string; mode?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { success: false, error: "Invalid JSON body" },
      { status: 400 }
    );
  }

  // Handle mode switching
  if (body.action === "set-mode") {
    if (body.mode !== "manual" && body.mode !== "mirror") {
      return NextResponse.json(
        { success: false, error: "mode must be 'manual' or 'mirror'" },
        { status: 400 }
      );
    }
    const success = await oracleSetMode(body.mode);
    return NextResponse.json({ success });
  }

  // Handle price setting (existing behavior)
  const price = typeof body.price === "string" ? parseFloat(body.price) : body.price;
  if (typeof price !== "number" || isNaN(price) || price <= 0) {
    return NextResponse.json(
      { success: false, error: "price must be a positive number" },
      { status: 400 }
    );
  }

  const success = await oracleSet(price);
  return NextResponse.json({ success });
}
