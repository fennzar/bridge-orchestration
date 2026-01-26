import { NextResponse } from "next/server";
import { DAEMON_PRIMARY_PORT, WALLET_MINER_PORT } from "@/lib/constants";
import { getWalletAddress, daemonOtherRpc } from "@/lib/rpc";

interface MiningRequest {
  action: "start" | "stop";
  threads?: number;
}

export async function POST(request: Request) {
  let body: MiningRequest;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { success: false, error: "Invalid JSON body" },
      { status: 400 }
    );
  }

  if (body.action !== "start" && body.action !== "stop") {
    return NextResponse.json(
      { success: false, error: 'action must be "start" or "stop"' },
      { status: 400 }
    );
  }

  if (body.action === "start") {
    const minerAddress = await getWalletAddress(WALLET_MINER_PORT);
    if (!minerAddress) {
      return NextResponse.json(
        { success: false, error: "Could not get miner wallet address" },
        { status: 500 }
      );
    }

    const threads = body.threads ?? 1;
    const { result, error } = await daemonOtherRpc(DAEMON_PRIMARY_PORT, "start_mining", {
      miner_address: minerAddress,
      threads_count: threads,
      do_background_mining: false,
      ignore_battery: true,
    });

    if (error) {
      return NextResponse.json({ success: false, error }, { status: 500 });
    }
    return NextResponse.json({ success: true, result });
  }

  // stop
  const { result, error } = await daemonOtherRpc(DAEMON_PRIMARY_PORT, "stop_mining");
  if (error) {
    return NextResponse.json({ success: false, error }, { status: 500 });
  }
  return NextResponse.json({ success: true, result });
}
