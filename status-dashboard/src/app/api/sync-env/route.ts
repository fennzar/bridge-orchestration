import { NextResponse } from "next/server";
import { exec } from "child_process";
import { promisify } from "util";
import * as path from "path";
import { ORCH_DIR } from "@/lib/constants";
import type { RouteMeta } from "@/lib/route-meta";

export const meta: RouteMeta = {
  title: "Sync Env Files",
  category: "Operations",
  description: "Sync the root .env file to sub-repo .env files (bridge, engine, etc.).",
  response: [
    { name: "success", type: "boolean", required: true, description: "Whether the sync succeeded" },
    { name: "output", type: "string", required: true, description: "Combined stdout/stderr from the sync script" },
  ],
  curl: "curl -X POST localhost:7100/api/sync-env",
};

const execAsync = promisify(exec);

export const dynamic = "force-dynamic";

export async function POST() {
  try {
    const script = path.join(ORCH_DIR, "scripts/sync-env.sh");
    const { stdout, stderr } = await execAsync(script, {
      cwd: ORCH_DIR,
      timeout: 15000,
    });
    return NextResponse.json({
      success: true,
      output: (stdout + stderr).trim(),
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ success: false, error: message }, { status: 500 });
  }
}
