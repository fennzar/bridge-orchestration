import { NextResponse } from "next/server";
import { oracleSet } from "@/lib/rpc";

const SCENARIO_PRICES: Record<string, number> = {
  normal: 2.0,
  defensive: 0.5,
  crisis: 0.1,
  recovery: 1.5,
};

type ScenarioName = keyof typeof SCENARIO_PRICES;

interface ScenarioRequest {
  scenario: ScenarioName;
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

  const price = SCENARIO_PRICES[body.scenario];
  if (price === undefined) {
    const valid = Object.keys(SCENARIO_PRICES).join(", ");
    return NextResponse.json(
      { success: false, error: `Unknown scenario: ${body.scenario}. Valid: ${valid}` },
      { status: 400 }
    );
  }

  const success = await oracleSet(price);

  return NextResponse.json({
    success,
    scenario: body.scenario,
    price,
  });
}
