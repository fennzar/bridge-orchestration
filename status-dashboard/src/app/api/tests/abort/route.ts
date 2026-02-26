import { NextResponse } from "next/server";
import type { RouteMeta } from "@/lib/route-meta";

export const meta: RouteMeta = {
  title: "Abort Test Run",
  category: "Testing",
  description: "Abort a running test execution by its run ID.",
  request: [
    { name: "runId", type: "string", required: true, description: "The run ID returned by the test/run SSE start event" },
  ],
  response: [
    { name: "success", type: "boolean", required: true, description: "Whether the run was aborted" },
    { name: "message", type: "string", required: true, description: "Confirmation message" },
  ],
  curl: "curl -X POST localhost:7100/api/tests/abort -H 'Content-Type: application/json' -d '{\"runId\":\"run-123456789-abc1234\"}'",
};

// Store active processes (shared with run route via module-level Map)
// Note: In a real production setup, this would use a more robust IPC mechanism
// For this dashboard, we use a simple in-memory approach

// We need to import the process map from the run route
// However, since Next.js API routes may run in different contexts,
// we'll use a global store

declare global {
  // eslint-disable-next-line no-var
  var testRunnerProcesses: Map<string, { pid: number; kill: () => void }>;
}

if (!global.testRunnerProcesses) {
  global.testRunnerProcesses = new Map();
}

interface AbortRequest {
  runId: string;
}

export async function POST(request: Request) {
  try {
    const body: AbortRequest = await request.json();
    const { runId } = body;

    if (!runId) {
      return NextResponse.json(
        { success: false, error: "runId is required" },
        { status: 400 }
      );
    }

    const processInfo = global.testRunnerProcesses.get(runId);

    if (!processInfo) {
      return NextResponse.json(
        { success: false, error: "No active process found for this runId" },
        { status: 404 }
      );
    }

    try {
      // Kill the process group to ensure child processes are also terminated
      process.kill(-processInfo.pid, "SIGTERM");
    } catch {
      // If process group kill fails, try killing just the process
      try {
        process.kill(processInfo.pid, "SIGTERM");
      } catch {
        // Process may have already exited
      }
    }

    global.testRunnerProcesses.delete(runId);

    return NextResponse.json({
      success: true,
      message: `Test run ${runId} aborted`,
    });
  } catch (error) {
    return NextResponse.json(
      {
        success: false,
        error: error instanceof Error ? error.message : "Unknown error",
      },
      { status: 500 }
    );
  }
}
