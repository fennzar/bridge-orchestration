import { NextRequest, NextResponse } from "next/server";
import * as path from "path";
import { ORCH_DIR } from "@/lib/constants";
import { streamScript, sseResponse } from "@/lib/run-script";
import type { RouteMeta } from "@/lib/route-meta";

export const meta: RouteMeta = {
  title: "Reset Environment",
  category: "Operations",
  description:
    "Reset environment layers to post-init state. Streams progress via SSE. Scope: full (all layers), zephyr, evm, or db.",
  sse: true,
  request: [
    { name: "scope", type: "string", description: "Reset scope: full (default), zephyr, evm, db" },
  ],
  curl: [
    "curl -N -X POST localhost:7100/api/reset -H 'Content-Type: application/json' -d '{\"scope\":\"full\"}'",
    "curl -N -X POST localhost:7100/api/reset -H 'Content-Type: application/json' -d '{\"scope\":\"evm\"}'",
  ],
};

export const dynamic = "force-dynamic";

const VALID_SCOPES = ["full", "zephyr", "evm", "db"] as const;
type Scope = (typeof VALID_SCOPES)[number];

const SCOPE_ARGS: Record<Scope, string[]> = {
  full: [],
  zephyr: ["--zephyr-only"],
  evm: ["--evm-only"],
  db: ["--db-only"],
};

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const scope: string = body.scope ?? "full";

  if (!VALID_SCOPES.includes(scope as Scope)) {
    return NextResponse.json(
      { error: `Invalid scope "${scope}". Valid: ${VALID_SCOPES.join(", ")}` },
      { status: 400 },
    );
  }

  const script = path.join(ORCH_DIR, "scripts/dev-reset.sh");
  const args = SCOPE_ARGS[scope as Scope];
  const { stream } = streamScript(script, args);
  return sseResponse(stream);
}
