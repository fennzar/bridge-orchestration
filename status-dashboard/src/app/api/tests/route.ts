import { NextResponse } from "next/server";
import { exec } from "child_process";
import { promisify } from "util";
import * as path from "path";
import type { TestInfo } from "@/lib/types";
import { ORCH_DIR } from "@/lib/constants";

const execAsync = promisify(exec);

export const dynamic = "force-dynamic";

// L1-L4 test descriptions
const TEST_DESCRIPTIONS: Record<string, { name: string; category: string }> = {
  // L1: Infrastructure
  "INFRA-01": { name: "Docker Services", category: "Infrastructure" },
  "INFRA-02": { name: "DEVNET Services", category: "Infrastructure" },
  "INFRA-03": { name: "Wallet RPCs", category: "Infrastructure" },
  "INFRA-04": { name: "Application Services", category: "Infrastructure" },
  // L2: Smoke Tests
  "SMOKE-01": { name: "Zephyr Chain Health", category: "Smoke Tests" },
  "SMOKE-02": { name: "Wallet Balances", category: "Smoke Tests" },
  "SMOKE-03": { name: "Oracle Price", category: "Smoke Tests" },
  "SMOKE-04": { name: "EVM Contracts", category: "Smoke Tests" },
  "SMOKE-05": { name: "Bridge API Health", category: "Smoke Tests" },
  "SMOKE-06": { name: "Mining Active", category: "Smoke Tests" },
  // L3: Engine Component Tests
  "ENGINE-01": { name: "State Builder", category: "Engine" },
  "ENGINE-02": { name: "Engine Status", category: "Engine" },
  "ENGINE-03": { name: "Arbitrage Analysis", category: "Engine" },
  "ENGINE-04": { name: "Balances Endpoint", category: "Engine" },
  "ENGINE-05": { name: "Runtime Info", category: "Engine" },
  "ENGINE-06": { name: "Zephyr Network State", category: "Engine" },
  // L3: Bridge Component Tests
  "BRIDGE-01": { name: "Bridge API Status", category: "Bridge" },
  "BRIDGE-02": { name: "Claims Endpoint", category: "Bridge" },
  "BRIDGE-03": { name: "Unwraps Endpoint", category: "Bridge" },
  // L3: Zephyr Tests
  "ZEPHYR-01": { name: "Gov Wallet Balances", category: "Zephyr" },
  "ZEPHYR-02": { name: "Reserve Info", category: "Zephyr" },
  // L3: EVM Tests
  "EVM-01": { name: "Deployed Contracts", category: "EVM" },
  // L3: Oracle Tests
  "ORACLE-01": { name: "Oracle Price Control", category: "Oracle" },
  // L3: Orderbook Tests
  "ORDERBOOK-01": { name: "Orderbook Price Tracking", category: "Orderbook" },
  // L4: Full Stack E2E Tests
  "L4-01": { name: "Transfer Flow Test", category: "E2E" },
  "L4-02": { name: "RR Mode Transitions", category: "E2E" },
  "L4-03": { name: "Engine State Updates", category: "E2E" },
  "L4-04": { name: "Arbitrage Spread Detection", category: "E2E" },
  "L4-05": { name: "Paper Account", category: "E2E" },
  "L4-06": { name: "Quoter System", category: "E2E" },
  "L4-07": { name: "MEXC Market Data", category: "E2E" },
  "L4-08": { name: "LP Positions", category: "E2E" },
};

// Map test IDs to their levels
const TEST_LEVELS: Record<string, "L1" | "L2" | "L3" | "L4"> = {
  "INFRA-01": "L1",
  "INFRA-02": "L1",
  "INFRA-03": "L1",
  "INFRA-04": "L1",
  "SMOKE-01": "L2",
  "SMOKE-02": "L2",
  "SMOKE-03": "L2",
  "SMOKE-04": "L2",
  "SMOKE-05": "L2",
  "SMOKE-06": "L2",
  "ENGINE-01": "L3",
  "ENGINE-02": "L3",
  "ENGINE-03": "L3",
  "ENGINE-04": "L3",
  "ENGINE-05": "L3",
  "ENGINE-06": "L3",
  "BRIDGE-01": "L3",
  "BRIDGE-02": "L3",
  "BRIDGE-03": "L3",
  "ZEPHYR-01": "L3",
  "ZEPHYR-02": "L3",
  "EVM-01": "L3",
  "ORACLE-01": "L3",
  "ORDERBOOK-01": "L3",
  "L4-01": "L4",
  "L4-02": "L4",
  "L4-03": "L4",
  "L4-04": "L4",
  "L4-05": "L4",
  "L4-06": "L4",
  "L4-07": "L4",
  "L4-08": "L4",
};

// L5 sublevel definitions
const L5_SUBLEVELS: Record<string, { name: string; categories: string[] }> = {
  "L5.1": { name: "Security & Contracts", categories: ["SEC", "SC"] },
  "L5.2": { name: "Runtime & Consistency", categories: ["CONS", "RR", "CONC"] },
  "L5.3": { name: "Infra & Watchers", categories: ["WATCH", "CONF", "REC"] },
  "L5.4": { name: "Asset & DEX", categories: ["ASSET", "DEX"] },
  "L5.5": { name: "Privacy & Load", categories: ["PRIV", "LOAD", "TIME"] },
  "L5.6": { name: "Frontend", categories: ["FE"] },
};

// Map category prefixes to sublevel
function getSublevel(testId: string): string | undefined {
  // L5 test IDs are like ZB-SEC-001, ZB-RR-003, etc.
  const match = testId.match(/^ZB-([A-Z]+)-\d+$/);
  if (!match) return undefined;
  const cat = match[1];
  for (const [sublevel, info] of Object.entries(L5_SUBLEVELS)) {
    if (info.categories.includes(cat)) return sublevel;
  }
  return undefined;
}

async function discoverL5Tests(): Promise<TestInfo[]> {
  const tests: TestInfo[] = [];

  try {
    // Use the Python L5 runner to get the catalog
    const scriptPath = path.join(ORCH_DIR, "scripts/run-l5-tests.py");
    const { stdout } = await execAsync(
      `python3 "${scriptPath}" --list 2>/dev/null`,
      { timeout: 10000, cwd: ORCH_DIR }
    );

    if (!stdout.trim()) return tests;

    // Parse --list output: each line typically has "ZB-XXX-NNN: Title"
    for (const line of stdout.split("\n")) {
      const match = line.match(/^\s*(ZB-[A-Z]+-\d{3})\s*[:\-]\s*(.+)$/);
      if (match) {
        const id = match[1];
        const name = match[2].trim();
        const catMatch = id.match(/^ZB-([A-Z]+)-/);
        const category = catMatch ? catMatch[1] : "L5";
        const sublevel = getSublevel(id);

        tests.push({
          id,
          name,
          level: "L5",
          category,
          sublevel,
        });
      }
    }
  } catch {
    // --list may not be supported; fall back to --catalog or similar
    try {
      const scriptPath = path.join(ORCH_DIR, "scripts/run-l5-tests.py");
      const { stdout } = await execAsync(
        `python3 "${scriptPath}" --summary 2>/dev/null | head -200`,
        { timeout: 10000, cwd: ORCH_DIR }
      );

      // Parse summary output for test IDs
      for (const line of stdout.split("\n")) {
        const idMatch = line.match(/(ZB-[A-Z]+-\d{3})/g);
        if (idMatch) {
          for (const id of idMatch) {
            // Skip if already added
            if (tests.find((t) => t.id === id)) continue;
            const catMatch = id.match(/^ZB-([A-Z]+)-/);
            const category = catMatch ? catMatch[1] : "L5";
            const sublevel = getSublevel(id);

            tests.push({
              id,
              name: `${category} Edge Test`,
              level: "L5",
              category,
              sublevel,
            });
          }
        }
      }
    } catch {
      // Add placeholder sublevel entries if discovery fails entirely
      for (const [sublevel, info] of Object.entries(L5_SUBLEVELS)) {
        tests.push({
          id: sublevel,
          name: info.name,
          level: "L5",
          category: info.categories.join("+"),
          sublevel,
        });
      }
    }
  }

  return tests;
}

async function buildTestList(): Promise<TestInfo[]> {
  const tests: TestInfo[] = [];

  // Add L1-L4 tests from static definitions
  for (const [id, level] of Object.entries(TEST_LEVELS)) {
    const desc = TEST_DESCRIPTIONS[id];
    if (desc) {
      tests.push({
        id,
        name: desc.name,
        level,
        category: desc.category,
      });
    }
  }

  // Discover L5 tests
  const l5Tests = await discoverL5Tests();
  tests.push(...l5Tests);

  // Sort: by level then by id
  const levelOrder: Record<string, number> = { L1: 1, L2: 2, L3: 3, L4: 4, L5: 5 };
  tests.sort((a, b) => {
    const levelDiff = (levelOrder[a.level] ?? 99) - (levelOrder[b.level] ?? 99);
    if (levelDiff !== 0) return levelDiff;
    return a.id.localeCompare(b.id);
  });

  return tests;
}

export async function GET() {
  const tests = await buildTestList();

  const summary = {
    L1: tests.filter((t) => t.level === "L1").length,
    L2: tests.filter((t) => t.level === "L2").length,
    L3: tests.filter((t) => t.level === "L3").length,
    L4: tests.filter((t) => t.level === "L4").length,
    L5: tests.filter((t) => t.level === "L5").length,
    total: tests.length,
  };

  return NextResponse.json({ tests, summary });
}
