import { NextResponse } from "next/server";
import {
  WALLET_GOV_PORT,
  WALLET_MINER_PORT,
  WALLET_TEST_PORT,
  WALLET_BRIDGE_PORT,
} from "@/lib/constants";
import { getWalletAddress, walletTransfer } from "@/lib/rpc";

export const dynamic = "force-dynamic";

const WALLET_PORTS: Record<string, number> = {
  gov: WALLET_GOV_PORT,
  miner: WALLET_MINER_PORT,
  test: WALLET_TEST_PORT,
  bridge: WALLET_BRIDGE_PORT,
};

// Valid conversion pairs (from zephyr-cli)
const VALID_CONVERSIONS: [string, string][] = [
  ["ZPH", "ZSD"],
  ["ZSD", "ZPH"],
  ["ZPH", "ZRS"],
  ["ZRS", "ZPH"],
  ["ZSD", "ZYS"],
  ["ZYS", "ZSD"],
];

interface TransferRequest {
  fromWallet: string;
  toWallet: string;
  amount: number;
  sourceAsset: string;
  destAsset: string;
}

export async function POST(request: Request) {
  let body: TransferRequest;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { success: false, error: "Invalid JSON body" },
      { status: 400 }
    );
  }

  const { fromWallet, toWallet, amount, sourceAsset, destAsset } = body;

  if (!fromWallet || !amount || !sourceAsset || !destAsset) {
    return NextResponse.json(
      { success: false, error: "Missing required fields" },
      { status: 400 }
    );
  }

  const fromPort = WALLET_PORTS[fromWallet];
  if (!fromPort) {
    return NextResponse.json(
      { success: false, error: `Unknown wallet: ${fromWallet}` },
      { status: 400 }
    );
  }

  if (amount <= 0) {
    return NextResponse.json(
      { success: false, error: "Amount must be positive" },
      { status: 400 }
    );
  }

  try {
    if (sourceAsset === destAsset) {
      // Same-asset transfer between wallets
      if (!toWallet || toWallet === fromWallet) {
        return NextResponse.json(
          { success: false, error: "Must specify a different destination wallet for transfers" },
          { status: 400 }
        );
      }
      const toPort = WALLET_PORTS[toWallet];
      if (!toPort) {
        return NextResponse.json(
          { success: false, error: `Unknown wallet: ${toWallet}` },
          { status: 400 }
        );
      }

      const toAddress = await getWalletAddress(toPort);
      if (!toAddress) {
        return NextResponse.json(
          { success: false, error: `Could not get address for wallet: ${toWallet}` },
          { status: 500 }
        );
      }

      const result = await walletTransfer(fromPort, toAddress, amount, sourceAsset, destAsset);
      return NextResponse.json(result);
    } else {
      // Asset conversion (self-transfer)
      const isValid = VALID_CONVERSIONS.some(
        ([from, to]) => from === sourceAsset && to === destAsset
      );
      if (!isValid) {
        return NextResponse.json(
          { success: false, error: `Invalid conversion: ${sourceAsset} -> ${destAsset}` },
          { status: 400 }
        );
      }

      const selfAddress = await getWalletAddress(fromPort);
      if (!selfAddress) {
        return NextResponse.json(
          { success: false, error: `Could not get address for wallet: ${fromWallet}` },
          { status: 500 }
        );
      }

      const result = await walletTransfer(fromPort, selfAddress, amount, sourceAsset, destAsset);
      return NextResponse.json(result);
    }
  } catch (err) {
    return NextResponse.json(
      { success: false, error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 }
    );
  }
}
