import { spawn } from "child_process";
import * as readline from "readline";
import { ORCH_DIR } from "./constants";

function generateRunId(): string {
  return `run-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

/**
 * Spawn a process and stream its output as SSE events.
 * Events: start, output, complete (with exit code), error
 */
export function streamScript(
  command: string,
  args: string[],
  opts?: { cwd?: string; env?: Record<string, string> }
): { stream: ReadableStream; runId: string } {
  const runId = generateRunId();
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    start(controller) {
      const sendEvent = (event: string, data: unknown) => {
        const payload = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
        controller.enqueue(encoder.encode(payload));
      };

      sendEvent("start", {
        runId,
        command: `${command} ${args.join(" ")}`,
        timestamp: new Date().toISOString(),
      });

      const proc = spawn(command, args, {
        cwd: opts?.cwd ?? ORCH_DIR,
        env: {
          ...process.env,
          ...opts?.env,
          FORCE_COLOR: "1",
          TERM: "xterm-256color",
        },
        stdio: ["ignore", "pipe", "pipe"],
      });

      if (!proc.stdout) {
        sendEvent("error", { runId, message: "Failed to capture process output" });
        controller.close();
        return;
      }

      const rl = readline.createInterface({
        input: proc.stdout,
        crlfDelay: Infinity,
      });

      rl.on("line", (line) => {
        sendEvent("output", { line });
      });

      proc.stderr?.on("data", (data: Buffer) => {
        const lines = data.toString().split("\n");
        for (const line of lines) {
          if (line.trim()) {
            sendEvent("output", { line, stderr: true });
          }
        }
      });

      proc.on("close", (code) => {
        sendEvent("complete", {
          runId,
          exitCode: code ?? 1,
          timestamp: new Date().toISOString(),
        });
        controller.close();
      });

      proc.on("error", (err: Error) => {
        sendEvent("error", { runId, message: err.message });
        controller.close();
      });
    },
  });

  return { stream, runId };
}

/** Return a streaming SSE Response from streamScript output */
export function sseResponse(stream: ReadableStream): Response {
  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
