import { spawn, ChildProcess } from "child_process";
import * as path from "path";
import * as readline from "readline";
import { ORCH_DIR } from "@/lib/constants";

// Strip ANSI escape codes for reliable parsing
function stripAnsi(str: string): string {
  // eslint-disable-next-line no-control-regex
  return str.replace(/\x1b\[[0-9;]*m/g, "");
}

// Use global store for process tracking (shared with abort route)
declare global {
  // eslint-disable-next-line no-var
  var testRunnerProcesses: Map<string, { pid: number; kill: () => void }>;
}

if (!global.testRunnerProcesses) {
  global.testRunnerProcesses = new Map();
}

interface RunRequest {
  testIds?: string[];
  level?: "L1" | "L2" | "L3" | "L4" | "L5" | "all";
  sublevel?: string; // e.g. "L5.1", "L5.2" etc.
  category?: string; // e.g. "SEC", "RR" etc.
}

function generateRunId(): string {
  return `run-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

// Build list of scripts to run based on test selection
interface ScriptRun {
  command: string;
  args: string[];
}

function determineScriptsToRun(
  testIds?: string[],
  level?: string,
  sublevel?: string,
  category?: string
): ScriptRun[] {
  const runs: ScriptRun[] = [];
  const runTestsScript = path.join(ORCH_DIR, "scripts/run-tests.py");
  const runL5Script = path.join(ORCH_DIR, "scripts/run-l5-tests.py");

  if (testIds && testIds.length > 0) {
    // Specific tests requested - split by type
    const l1l4Tests = testIds.filter((id) => !id.startsWith("ZB-"));
    const l5Tests = testIds.filter((id) => id.startsWith("ZB-"));

    if (l1l4Tests.length > 0) {
      runs.push({
        command: "python3",
        args: [runTestsScript, ...l1l4Tests],
      });
    }
    if (l5Tests.length > 0) {
      // For specific L5 test IDs, pass them as filter args
      runs.push({
        command: "python3",
        args: [runL5Script, "--execute", "--verbose", ...l5Tests],
      });
    }
  } else if (sublevel) {
    // L5 sublevel selection
    runs.push({
      command: "python3",
      args: [runL5Script, "--execute", "--verbose", "--sublevel", sublevel],
    });
  } else if (category) {
    // L5 category selection
    runs.push({
      command: "python3",
      args: [runL5Script, "--execute", "--verbose", "--category", category],
    });
  } else if (level) {
    if (level === "L5") {
      runs.push({
        command: "python3",
        args: [runL5Script, "--execute", "--verbose"],
      });
    } else if (level === "all") {
      // Run L1-L4 first, then L5
      runs.push({
        command: "python3",
        args: [runTestsScript],
      });
      runs.push({
        command: "python3",
        args: [runL5Script, "--execute", "--verbose"],
      });
    } else {
      // L1, L2, L3, or L4 - the Python runner supports --level
      runs.push({
        command: "python3",
        args: [runTestsScript, "--level", level],
      });
    }
  } else {
    // Default: run all L1-L4
    runs.push({
      command: "python3",
      args: [runTestsScript],
    });
  }

  return runs;
}

export async function POST(request: Request) {
  const body: RunRequest = await request.json();
  const { testIds, level, sublevel, category } = body;

  const runId = generateRunId();
  const encoder = new TextEncoder();

  const stream = new ReadableStream({
    start(controller) {
      // Helper to send SSE events
      const sendEvent = (event: string, data: unknown) => {
        const payload = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
        controller.enqueue(encoder.encode(payload));
      };

      // Determine all scripts to run
      const scriptRuns = determineScriptsToRun(testIds, level, sublevel, category);

      if (scriptRuns.length === 0) {
        sendEvent("error", { runId, message: "No tests to run" });
        controller.close();
        return;
      }

      sendEvent("start", {
        runId,
        testsToRun: testIds && testIds.length > 0 ? testIds : level || sublevel || category || "all",
        timestamp: new Date().toISOString(),
      });

      // Track results across all script runs
      let passCount = 0;
      let failCount = 0;
      let skipCount = 0;
      let currentProc: ChildProcess | null = null;

      // Store process info for abort capability
      global.testRunnerProcesses.set(runId, {
        pid: 0, // Will be updated when process starts
        kill: () => {
          if (currentProc && currentProc.pid) {
            try {
              process.kill(-currentProc.pid, "SIGTERM");
            } catch {
              currentProc.kill("SIGTERM");
            }
          }
        },
      });

      // Parse a line for test results (strip ANSI first)
      const parseLine = (line: string) => {
        // Send raw output (with ANSI for display)
        sendEvent("output", { line });

        // Strip ANSI codes for reliable parsing
        const cleanLine = stripAnsi(line);

        // Detect test results - match test ID (may have colon after it)
        // L1-L4 format: [PASS] TEST-ID: Description
        // L5 format may differ: PASS ZB-SEC-001: Description or similar
        if (cleanLine.includes("[PASS]") || /\bPASS\b/.test(cleanLine)) {
          const match = cleanLine.match(/\[PASS\]\s+([A-Z0-9-]+)/) ||
            cleanLine.match(/PASS\s+(ZB-[A-Z]+-\d{3})/);
          if (match) {
            passCount++;
            sendEvent("result", { testId: match[1], status: "pass" });
          }
        } else if (cleanLine.includes("[FAIL]") || /\bFAIL\b/.test(cleanLine)) {
          const match = cleanLine.match(/\[FAIL\]\s+([A-Z0-9-]+)/) ||
            cleanLine.match(/FAIL\s+(ZB-[A-Z]+-\d{3})/);
          if (match) {
            failCount++;
            sendEvent("result", { testId: match[1], status: "fail" });
          }
        } else if (cleanLine.includes("[SKIP]") || /\bSKIP\b/.test(cleanLine)) {
          const match = cleanLine.match(/\[SKIP\]\s+([A-Z0-9-]+)/) ||
            cleanLine.match(/SKIP\s+(ZB-[A-Z]+-\d{3})/);
          if (match) {
            skipCount++;
            sendEvent("result", { testId: match[1], status: "skip" });
          }
        } else if (cleanLine.includes("[BLOCKED]") || /\bBLOCKED\b/.test(cleanLine)) {
          const match = cleanLine.match(/\[BLOCKED\]\s+([A-Z0-9-]+)/) ||
            cleanLine.match(/BLOCKED\s+(ZB-[A-Z]+-\d{3})/);
          if (match) {
            skipCount++;
            sendEvent("result", { testId: match[1], status: "skip" });
          }
        } else if (cleanLine.includes("[TEST]")) {
          // Test starting
          const match = cleanLine.match(/\[TEST\]\s+([A-Z0-9-]+):/);
          if (match) {
            sendEvent("running", { testId: match[1] });
          }
        }
      };

      // Run scripts sequentially
      let runIndex = 0;

      const runNextScript = () => {
        if (runIndex >= scriptRuns.length) {
          // All scripts completed
          global.testRunnerProcesses.delete(runId);
          sendEvent("complete", {
            runId,
            exitCode: 0,
            pass: passCount,
            fail: failCount,
            skip: skipCount,
            timestamp: new Date().toISOString(),
          });
          controller.close();
          return;
        }

        const scriptRun = scriptRuns[runIndex];
        runIndex++;

        // Spawn the test process using Python
        const proc = spawn(scriptRun.command, scriptRun.args, {
          cwd: ORCH_DIR,
          env: {
            ...process.env,
            FORCE_COLOR: "1",
            TERM: "xterm-256color",
            PYTHONUNBUFFERED: "1",
          },
          detached: true,
        });

        currentProc = proc;

        // Update stored process info
        if (proc.pid) {
          const entry = global.testRunnerProcesses.get(runId);
          if (entry) {
            entry.pid = proc.pid;
          }
        }

        if (!proc.stdout) {
          sendEvent("error", { runId, message: "Failed to capture process output" });
          controller.close();
          return;
        }

        const rl = readline.createInterface({
          input: proc.stdout,
          crlfDelay: Infinity,
        });

        rl.on("line", parseLine);

        // Process stderr
        proc.stderr?.on("data", (data: Buffer) => {
          const lines = data.toString().split("\n");
          for (const line of lines) {
            if (line.trim()) {
              sendEvent("output", { line, stderr: true });
            }
          }
        });

        // Handle process completion - run next script
        proc.on("close", () => {
          currentProc = null;
          runNextScript();
        });

        // Handle process errors
        proc.on("error", (err: Error) => {
          global.testRunnerProcesses.delete(runId);
          sendEvent("error", {
            runId,
            message: err.message,
          });
          controller.close();
        });
      };

      // Start running scripts
      runNextScript();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
