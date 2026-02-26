import { NextResponse } from "next/server";
import {
  DAEMON_PRIMARY_PORT,
  DAEMON_SECONDARY_PORT,
  WALLET_GOV_PORT,
  WALLET_MINER_PORT,
  WALLET_TEST_PORT,
  WALLET_BRIDGE_PORT,
  WALLET_ENGINE_PORT,
} from "@/lib/constants";
import type { ChainResponse, WalletBalance } from "@/lib/types";
import { readCheckpointHeight } from "@/lib/docker";
import {
  getDaemonInfo,
  getWalletAddress,
  getMultiAssetBalance,
  oracleGetStatus,
  zephyrRpc,
  fromAtomic,
} from "@/lib/rpc";
import type { RouteMeta } from "@/lib/route-meta";

export const meta: RouteMeta = {
  title: "Chain State",
  category: "Chain",
  description:
    "Comprehensive Zephyr chain state including node sync status, mining info, wallet balances, oracle price, reserve protocol data, and checkpoint info.",
  response: [
    { name: "nodes", type: "{ node1: NodeInfo, node2: NodeInfo }", required: true, description: "Sync status of both Zephyr nodes" },
    { name: "mining", type: "{ active, threads?, speed? }", required: true, description: "Mining status on primary node" },
    { name: "checkpoint", type: "{ current, saved }", required: true, description: "Current and saved checkpoint heights" },
    { name: "oracle", type: "{ price, mode, mirrorSpot?, mirrorLastFetch? }", required: true, description: "Oracle price in USD with mode (manual/mirror)" },
    { name: "wallets", type: "WalletBalance[]", required: true, description: "All wallet addresses and multi-asset balances (ZPH, ZSD, ZRS, ZYS)" },
    { name: "reserve", type: "ReserveInfo", description: "Zephyr reserve protocol state (ratios, assets, liabilities)" },
    { name: "timestamp", type: "string", required: true, description: "ISO 8601 timestamp" },
  ],
  curl: "curl localhost:7100/api/chain",
};

export const dynamic = "force-dynamic";

const WALLETS = [
  { name: "gov", port: WALLET_GOV_PORT },
  { name: "miner", port: WALLET_MINER_PORT },
  { name: "test", port: WALLET_TEST_PORT },
  { name: "bridge", port: WALLET_BRIDGE_PORT },
  { name: "engine", port: WALLET_ENGINE_PORT },
] as const;

export async function GET() {
  // Gather node and chain data in parallel
  const [node1Info, node2Info, oracleStatus, reserveResp, savedCheckpoint, ...walletData] =
    await Promise.all([
      getDaemonInfo(DAEMON_PRIMARY_PORT),
      getDaemonInfo(DAEMON_SECONDARY_PORT),
      oracleGetStatus(),
      zephyrRpc(DAEMON_PRIMARY_PORT, "get_reserve_info"),
      readCheckpointHeight(),
      // Wallet data: address + balances for each wallet (5 wallets = 10 promises)
      ...WALLETS.flatMap((w) => [
        getWalletAddress(w.port).catch(() => null),
        getMultiAssetBalance(w.port).catch(() => ({
          ZPH: "0.0000", ZSD: "0.0000", ZRS: "0.0000", ZYS: "0.0000", error: "Connection refused",
        })),
      ]),
    ]);

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
      price: oracleStatus?.price ?? null,
      mode: oracleStatus?.mode ?? "manual",
      mirrorSpot: oracleStatus?.mirrorSpot,
      mirrorLastFetch: oracleStatus?.mirrorLastFetch,
    },
    wallets,
    reserve,
    timestamp: new Date().toISOString(),
  };

  return NextResponse.json(response);
}
