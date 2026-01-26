import { exec } from "child_process";
import { promisify } from "util";
import { DC_CMD } from "./constants";

const execAsync = promisify(exec);

interface ContainerInfo {
  Name: string;
  State: string;
  Status: string;
  Health?: string;
  Publishers?: Array<{ PublishedPort: number; TargetPort: number }>;
}

export async function runDC(args: string): Promise<string> {
  try {
    const { stdout } = await execAsync(`${DC_CMD} ${args}`, { timeout: 15000 });
    return stdout.trim();
  } catch {
    return "";
  }
}

export async function getContainerStatuses(): Promise<Map<string, { state: string; health: string }>> {
  const result = new Map<string, { state: string; health: string }>();
  try {
    const stdout = await runDC("ps --format json -a");
    if (!stdout) return result;

    // docker compose ps --format json outputs one JSON object per line
    const lines = stdout.split("\n").filter((l) => l.trim());
    for (const line of lines) {
      try {
        const data: ContainerInfo = JSON.parse(line);
        const state = data.State?.toLowerCase() || "unknown";
        const health = data.Status || "";
        result.set(data.Name, { state, health });
      } catch {
        // skip unparseable lines
      }
    }
  } catch {
    // compose not running
  }
  return result;
}

export async function getContainerLogs(service: string, tail: number = 20): Promise<string[]> {
  try {
    const stdout = await runDC(`logs --tail=${tail} --no-log-prefix ${service}`);
    return stdout.split("\n").filter((l) => l.trim());
  } catch {
    return [];
  }
}
