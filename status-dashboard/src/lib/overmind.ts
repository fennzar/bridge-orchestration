import { exec } from "child_process";
import { promisify } from "util";
import * as os from "os";
import * as fs from "fs/promises";
import * as path from "path";
import { ORCH_DIR, OVERMIND_SOCKET } from "./constants";

const execAsync = promisify(exec);

// Cache the tmux socket path with a short TTL so we revalidate between polling cycles
let tmuxSocketCache: { path: string; ts: number } | null = null;
const CACHE_TTL = 5000; // 5 seconds

async function findTmuxSocket(): Promise<string | null> {
  if (tmuxSocketCache && Date.now() - tmuxSocketCache.ts < CACHE_TTL) {
    return tmuxSocketCache.path;
  }

  try {
    const uid = os.userInfo().uid;
    const tmuxDir = `/tmp/tmux-${uid}`;
    const files = await fs.readdir(tmuxDir);
    const matching = files.filter((f) => f.startsWith("overmind-bridge-orchestration-"));
    if (matching.length === 0) return null;

    // Stat each socket and sort by mtime descending (newest first)
    const withStats = await Promise.all(
      matching.map(async (f) => {
        const fullPath = path.join(tmuxDir, f);
        const stat = await fs.stat(fullPath);
        return { path: fullPath, mtime: stat.mtimeMs };
      })
    );
    withStats.sort((a, b) => b.mtime - a.mtime);

    // Try sockets newest-first, validate each is alive
    for (const candidate of withStats) {
      try {
        await execAsync(`tmux -S "${candidate.path}" list-sessions 2>/dev/null`, {
          timeout: 2000,
        });
        tmuxSocketCache = { path: candidate.path, ts: Date.now() };
        return candidate.path;
      } catch {
        // Dead socket, try the next one
      }
    }
  } catch {
    // directory doesn't exist
  }

  tmuxSocketCache = null;
  return null;
}

export async function getOvmStatus(): Promise<Map<string, "running" | "stopped">> {
  const result = new Map<string, "running" | "stopped">();
  try {
    const { stdout } = await execAsync(
      `overmind status -s ${OVERMIND_SOCKET} 2>/dev/null || echo ""`,
      { timeout: 5000 }
    );
    if (!stdout.trim()) return result;

    for (const line of stdout.split("\n")) {
      const match = line.match(/^(\S+)\s+\d+\s+(\w+)/);
      if (match) {
        result.set(match[1], match[2] === "running" ? "running" : "stopped");
      }
    }
  } catch {
    // overmind not running
  }
  return result;
}

export async function isOvermindRunning(): Promise<boolean> {
  try {
    await fs.access(OVERMIND_SOCKET);
    const statuses = await getOvmStatus();
    return statuses.size > 0;
  } catch {
    return false;
  }
}

export async function getProcessLogs(name: string, lines: number = 50): Promise<string[]> {
  try {
    const socketPath = await findTmuxSocket();
    if (!socketPath) return [];

    const { stdout } = await execAsync(
      `tmux -S "${socketPath}" capture-pane -p -t bridge-orchestration:${name} -S -${lines} 2>/dev/null || echo ""`,
      { timeout: 5000 }
    );
    return stdout
      .split("\n")
      .filter((line) => line.trim() !== "")
      .slice(-lines);
  } catch {
    return [];
  }
}

export async function restartProcess(name: string): Promise<boolean> {
  try {
    await execAsync(`overmind restart ${name} -s ${OVERMIND_SOCKET}`, {
      cwd: ORCH_DIR,
      timeout: 10000,
    });
    return true;
  } catch {
    return false;
  }
}
