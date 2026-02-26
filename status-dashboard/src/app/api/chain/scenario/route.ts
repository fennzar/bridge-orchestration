import { NextResponse } from "next/server";
import { oracleSet, orderbookSetSpread } from "@/lib/rpc";
import type { RouteMeta } from "@/lib/route-meta";

export const meta: RouteMeta = {
  title: "Set Scenario",
  category: "Chain",
  description:
    "Apply a predefined scenario preset that sets oracle price and orderbook spread. Presets: normal, defensive, crisis, recovery, high-rr, volatility.",
  request: [
    { name: "scenario", type: "string", required: true, description: "Preset name (normal, defensive, crisis, recovery, high-rr, volatility)" },
  ],
  response: [
    { name: "success", type: "boolean", required: true, description: "Whether both price and spread were set" },
    { name: "scenario", type: "string", required: true, description: "Applied preset name" },
    { name: "price", type: "number", required: true, description: "Oracle price set (USD)" },
    { name: "spreadBps", type: "number", required: true, description: "Orderbook spread set (basis points)" },
  ],
  curl: "curl -X POST localhost:7100/api/chain/scenario -H 'Content-Type: application/json' -d '{\"scenario\":\"crisis\"}'",
};

export const dynamic = "force-dynamic";

const SCENARIOS: Record<string, { price: number; spreadBps: number }> = {
  normal:     { price: 15.00, spreadBps: 50 },
  defensive:  { price: 0.80,  spreadBps: 100 },
  crisis:     { price: 0.40,  spreadBps: 300 },
  recovery:   { price: 2.00,  spreadBps: 50 },
  "high-rr":  { price: 25.00, spreadBps: 50 },
  volatility: { price: 5.00,  spreadBps: 150 },
};

interface ScenarioRequest {
  scenario: string;
}

export async function POST(request: Request) {
  let body: ScenarioRequest;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { success: false, error: "Invalid JSON body" },
      { status: 400 }
    );
  }

  const scenario = SCENARIOS[body.scenario];
  if (!scenario) {
    const valid = Object.keys(SCENARIOS).join(", ");
    return NextResponse.json(
      { success: false, error: `Unknown scenario: ${body.scenario}. Valid: ${valid}` },
      { status: 400 }
    );
  }

  const [priceOk, spreadOk] = await Promise.all([
    oracleSet(scenario.price),
    orderbookSetSpread(scenario.spreadBps),
  ]);

  return NextResponse.json({
    success: priceOk && spreadOk,
    scenario: body.scenario,
    price: scenario.price,
    spreadBps: scenario.spreadBps,
  });
}
