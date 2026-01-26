import { NextResponse } from "next/server";
import {
  DAEMON_PRIMARY_PORT,
  DAEMON_SECONDARY_PORT,
  WALLET_GOV_PORT,
  WALLET_MINER_PORT,
  WALLET_TEST_PORT,
  WALLET_BRIDGE_PORT,
} from "@/lib/constants";
import type { ChainResponse, WalletBalance } from "@/lib/types";
import { runDC } from "@/lib/docker";
import {
  getDaemonInfo,
  getWalletAddress,
  getMultiAssetBalance,
  oracleGet,
  zephyrRpc,
} from "@/lib/rpc";

export const dynamic = "force-dynamic";

const WALLETS = [
  { name: "gov", port: WALLET_GOV_PORT },
  { name: "miner", port: WALLET_MINER_PORT },
  { name: "test", port: WALLET_TEST_PORT },
  { name: "bridge", port: WALLET_BRIDGE_PORT },
] as const;

export async function GET() {
  // Gather node and chain data in parallel
  const [node1Info, node2Info, oraclePrice, reserveResp, checkpointRaw, ...walletData] =
    await Promise.all([
      getDaemonInfo(DAEMON_PRIMARY_PORT),
      getDaemonInfo(DAEMON_SECONDARY_PORT),
      oracleGet(),
      zephyrRpc(DAEMON_PRIMARY_PORT, "get_reserve_info"),
      runDC("exec -T wallet-gov cat /checkpoint/height"),
      // Wallet data: address + balances for each wallet (3 wallets = 6 promises)
      ...WALLETS.flatMap((w) => [
        getWalletAddress(w.port).catch(() => null),
        getMultiAssetBalance(w.port).catch(() => ({
          ZPH: "0.0000", ZSD: "0.0000", ZRS: "0.0000", ZYS: "0.0000", error: "Connection refused",
        })),
      ]),
    ]);

  // Parse checkpoint
  let savedCheckpoint: number | null = null;
  if (checkpointRaw) {
    const parsed = parseInt(checkpointRaw, 10);
    if (!isNaN(parsed)) savedCheckpoint = parsed;
  }

  // Build wallet balances array
  const wallets: WalletBalance[] = WALLETS.map((w, i) => {
    const address = walletData[i * 2] as string | null;
    const balResult = walletData[i * 2 + 1] as Awaited<ReturnType<typeof getMultiAssetBalance>>;
    return {
      name: w.name,
      port: w.port,
      address: address ?? undefined,
      balances: { ZPH: balResult.ZPH, ZSD: balResult.ZSD, ZRS: balResult.ZRS, ZYS: balResult.ZYS },
      error: balResult.error,
    };
  });

  // Parse reserve info (full protocol state)
  let reserve: ChainResponse["reserve"];
  if (reserveResp.result) {
    const r = reserveResp.result;
    const pr = r.pr as Record<string, number> | undefined;
    const fromAtomic = (v: unknown) => Number(v ?? 0) / 1e12;

    reserve = {
      reserveRatio: String(r.reserve_ratio ?? "0"),
      reserveRatioMa: String(r.reserve_ratio_ma ?? "0"),
      spot: pr ? fromAtomic(pr.spot) : 0,
      movingAverage: pr ? fromAtomic(pr.moving_average) : 0,
      stableRate: pr ? fromAtomic(pr.stable) : 0,
      stableRateMa: pr ? fromAtomic(pr.stable_ma) : 0,
      reserveRate: pr ? fromAtomic(pr.reserve) : 0,
      reserveRateMa: pr ? fromAtomic(pr.reserve_ma) : 0,
      yieldPrice: pr ? fromAtomic(pr.yield_price) : 0,
      numStables: fromAtomic(r.num_stables),
      numReserves: fromAtomic(r.num_reserves),
      numZyield: fromAtomic(r.num_zyield),
      assets: fromAtomic(r.assets),
      assetsMa: fromAtomic(r.assets_ma),
      liabilities: fromAtomic(r.liabilities),
      equity: fromAtomic(r.equity),
      equityMa: fromAtomic(r.equity_ma),
      zephReserve: fromAtomic(r.zeph_reserve),
      zyieldReserve: fromAtomic(r.zyield_reserve),
      height: Number(r.height ?? 0),
      hfVersion: Number(r.hf_version ?? 0),
    };
  }

  const response: ChainResponse = {
    nodes: {
      node1: {
        height: node1Info?.height ?? null,
        synced: node1Info?.synced ?? false,
      },
      node2: {
        height: node2Info?.height ?? null,
        synced: node2Info?.synced ?? false,
      },
    },
    mining: {
      active: node1Info?.miningActive ?? false,
      threads: node1Info?.miningThreads,
      speed: node1Info?.miningSpeed,
    },
    checkpoint: {
      current: node1Info?.height ?? null,
      saved: savedCheckpoint,
    },
    oracle: {
      price: oraclePrice,
    },
    wallets,
    reserve,
    timestamp: new Date().toISOString(),
  };

  return NextResponse.json(response);
}
