import { NextResponse } from "next/server";
import { orderbookGet, orderbookSetSpread } from "@/lib/rpc";
import type { RouteMeta } from "@/lib/route-meta";

export const meta: RouteMeta = {
  title: "Orderbook Control",
  category: "Operations",
  description: "Get fake orderbook state or set the bid/ask spread (DEVNET only).",
  request: [
    { name: "spreadBps", type: "number", required: true, description: "Spread in basis points (e.g. 50 = 0.5%)" },
  ],
  response: [
    { name: "success", type: "boolean", required: true, description: "Whether the operation succeeded" },
    { name: "spreadBps", type: "number", description: "Confirmed spread in basis points (POST)" },
    { name: "oraclePriceUsd", type: "number", description: "Current oracle price in USD (GET)" },
    { name: "bestBid", type: "number", description: "Current best bid price (GET)" },
    { name: "bestAsk", type: "number", description: "Current best ask price (GET)" },
    { name: "spread", type: "number", description: "Absolute spread (GET)" },
  ],
  curl: [
    "curl localhost:7100/api/orderbook",
    "curl -X POST localhost:7100/api/orderbook -H 'Content-Type: application/json' -d '{\"spreadBps\":50}'",
  ],
};

export const dynamic = "force-dynamic";

export async function GET() {
  const data = await orderbookGet();
  if (!data) {
    return NextResponse.json(
      { success: false, error: "Orderbook unavailable" },
      { status: 502 }
    );
  }
  return NextResponse.json({ success: true, ...data });
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { spreadBps } = body;

    if (typeof spreadBps !== "number" || spreadBps <= 0) {
      return NextResponse.json(
        { success: false, error: "spreadBps must be a positive number" },
        { status: 400 }
      );
    }

    const ok = await orderbookSetSpread(spreadBps);
    if (!ok) {
      return NextResponse.json(
        { success: false, error: "Failed to set spread" },
        { status: 502 }
      );
    }
    return NextResponse.json({ success: true, spreadBps });
  } catch {
    return NextResponse.json(
      { success: false, error: "Invalid request body" },
      { status: 400 }
    );
  }
}
