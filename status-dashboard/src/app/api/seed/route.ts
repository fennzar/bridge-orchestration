import * as path from "path";
import { ORCH_DIR } from "@/lib/constants";
import { streamScript, sseResponse } from "@/lib/run-script";
import type { RouteMeta } from "@/lib/route-meta";

export const meta: RouteMeta = {
  title: "Seed Liquidity",
  category: "Operations",
  description:
    "Seed liquidity through the full bridge wrap flow: fund engine wallet, convert assets, bridge wrap, claim tokens, add pool liquidity. Streams progress via SSE.",
  sse: true,
  curl: "curl -N -X POST localhost:7100/api/seed",
};

export const dynamic = "force-dynamic";

export async function POST() {
  const script = path.join(ORCH_DIR, "scripts/seed-liquidity.py");
  const { stream } = streamScript("python3", [script], { env: { PYTHONUNBUFFERED: "1" } });
  return sseResponse(stream);
}
