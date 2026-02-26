import * as net from "net";

const ERROR_PATTERNS = [
  /Process crashed/i,
  /restarting in \d+s/i,
  /FATAL/,
  /password authentication failed/i,
  /EADDRINUSE/,
  /ERR_INVALID_STATE/,
  /ECONNREFUSED.*(?:5432|6380)/,
  /ENOENT: no such file or directory/,
  /Cannot find module/,
];

export async function checkPortListening(
  port: number,
  timeout = 1000,
): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    socket.setTimeout(timeout);
    socket.once("connect", () => {
      socket.destroy();
      resolve(true);
    });
    socket.once("timeout", () => {
      socket.destroy();
      resolve(false);
    });
    socket.once("error", () => {
      socket.destroy();
      resolve(false);
    });
    socket.connect(port, "127.0.0.1");
  });
}

export function extractErrors(logs: string[]): string[] {
  const recent = logs.slice(-20);
  const matched = new Set<string>();
  for (const line of recent) {
    for (const pattern of ERROR_PATTERNS) {
      if (pattern.test(line)) {
        matched.add(line.trim());
        break;
      }
    }
  }
  return Array.from(matched).slice(0, 3);
}

export async function checkHttpHealth(
  port: number,
  path: string,
  timeout = 2000,
): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeout);
    const res = await fetch(`http://127.0.0.1:${port}${path}`, {
      signal: controller.signal,
    });
    clearTimeout(timer);
    return res.ok;
  } catch {
    return false;
  }
}
