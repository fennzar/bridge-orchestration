import * as path from "path";
import { ORCH_DIR } from "@/lib/constants";
import { streamScript, sseResponse } from "@/lib/run-script";
import type { RouteMeta } from "@/lib/route-meta";

export const meta: RouteMeta = {
  title: "Deploy Contracts",
  category: "Operations",
  description: "Deploy EVM contracts to Anvil. Streams deployment progress via SSE.",
  sse: true,
  curl: "curl -N -X POST localhost:7100/api/deploy",
};

export const dynamic = "force-dynamic";

export async function POST() {
  const script = path.join(ORCH_DIR, "scripts/deploy-contracts.sh");
  const { stream } = streamScript(script, []);
  return sseResponse(stream);
}
