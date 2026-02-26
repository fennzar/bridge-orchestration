import { NextResponse } from "next/server";
import { WALLET_PORTS } from "@/lib/constants";
import { walletRescan } from "@/lib/rpc";
import type { RouteMeta } from "@/lib/route-meta";

export const meta: RouteMeta = {
  title: "Rescan Wallets",
  category: "Chain",
  description:
    "Trigger a blockchain rescan on one or all Zephyr wallets to refresh balances.",
  request: [
    { name: "wallet", type: "string", required: true, description: "Wallet name (gov, miner, test, bridge, engine) or 'all'" },
  ],
  response: [
    { name: "success", type: "boolean", required: true, description: "Whether all rescans succeeded" },
    { name: "results", type: "{ wallet, success, error? }[]", required: true, description: "Per-wallet rescan results" },
  ],
  curl: "curl -X POST localhost:7100/api/chain/rescan -H 'Content-Type: application/json' -d '{\"wallet\":\"all\"}'",
};

export const dynamic = "force-dynamic";

interface RescanRequest {
  wallet: string;
}

export async function POST(request: Request) {
  let body: RescanRequest;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { success: false, error: "Invalid JSON body" },
      { status: 400 }
    );
  }

  const { wallet } = body;
  if (!wallet) {
    return NextResponse.json(
      { success: false, error: "Missing required field: wallet" },
      { status: 400 }
    );
  }

  const walletsToRescan: [string, number][] = [];

  if (wallet === "all") {
    walletsToRescan.push(...Object.entries(WALLET_PORTS));
  } else {
    const port = WALLET_PORTS[wallet];
    if (!port) {
      const valid = Object.keys(WALLET_PORTS).join(", ");
      return NextResponse.json(
        { success: false, error: `Unknown wallet: ${wallet}. Valid: ${valid}, all` },
        { status: 400 }
      );
    }
    walletsToRescan.push([wallet, port]);
  }

  try {
    const results = await Promise.all(
      walletsToRescan.map(async ([name, port]) => {
        const { success, error } = await walletRescan(port);
        return { wallet: name, success, ...(error ? { error } : {}) };
      })
    );

    const allSuccess = results.every((r) => r.success);
    return NextResponse.json({ success: allSuccess, results });
  } catch (err) {
    return NextResponse.json(
      { success: false, error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 }
    );
  }
}
