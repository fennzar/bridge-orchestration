import { NextResponse } from "next/server";
import { readFile } from "fs/promises";
import {
  getEvmConfig,
  detectEvmEnv,
  EVM_KEY_ACCOUNTS,
  maskRpcUrl,
} from "@/lib/constants";
import {
  ethCall,
  ethChainId,
  ethBlockNumber,
  ethGetBalance,
  tokenTotalSupply,
  getPoolSlot0,
  getPoolLiquidity,
  computePrice,
  formatWei,
  formatTokenAmount,
} from "@/lib/evm";
import type {
  EvmEnv,
  EvmResponse,
  EvmAccountInfo,
  EvmTokenInfo,
  EvmContractInfo,
  EvmPoolInfo,
  SeedingStatus,
} from "@/lib/types";
import type { RouteMeta } from "@/lib/route-meta";

export const meta: RouteMeta = {
  title: "EVM State",
  category: "Status",
  description:
    "Full EVM state: chain info, key accounts, deployed tokens (with supply), contracts, Uniswap V4 pool prices/liquidity, engine wallet balances, and seeding status.",
  response: [
    { name: "env", type: "string", required: true, description: "EVM environment (devnet, testnet, mainnet)" },
    { name: "chainId", type: "number | null", required: true, description: "Chain ID" },
    { name: "blockNumber", type: "number | null", required: true, description: "Latest block number" },
    { name: "networkName", type: "string", required: true, description: "Human-readable network name" },
    { name: "rpcUrl", type: "string", required: true, description: "RPC URL (masked)" },
    { name: "accounts", type: "EvmAccountInfo[]", required: true, description: "Key accounts with ETH balances" },
    { name: "tokens", type: "EvmTokenInfo[]", required: true, description: "Deployed tokens with total supply" },
    { name: "contracts", type: "EvmContractInfo[]", required: true, description: "Deployed contract addresses" },
    { name: "pools", type: "EvmPoolInfo[]", required: true, description: "Uniswap V4 pool state (price, liquidity)" },
    { name: "engineWallet", type: "{ address, ethBalance, tokenBalances }", description: "Engine wallet EVM balances" },
    { name: "seedingStatus", type: '"not_seeded" | "partial" | "seeded"', required: true, description: "Liquidity seeding status" },
    { name: "timestamp", type: "string", required: true, description: "ISO 8601 timestamp" },
  ],
  curl: "curl localhost:7100/api/evm",
};

export const dynamic = "force-dynamic";

interface AddressesJson {
  deployer?: string;
  contracts?: Record<string, string>;
  tokens?: Record<string, { address: string; decimals: number }>;
  pools?: Record<
    string,
    {
      plan?: {
        key?: { fee?: number; tickSpacing?: number };
        pricing?: { base?: string; quote?: string };
      };
      state?: {
        poolId?: string;
        currency0?: string;
        currency1?: string;
        fee?: number;
        tickSpacing?: number;
      };
    }
  >;
}

const SEL_BALANCE_OF = "0x70a08231";

async function tokenBalanceOf(
  rpcUrl: string,
  tokenAddr: string,
  account: string
): Promise<bigint | null> {
  const padded = account.toLowerCase().replace("0x", "").padStart(64, "0");
  const hex = await ethCall(rpcUrl, tokenAddr, SEL_BALANCE_OF + padded);
  if (!hex || hex === "0x") return null;
  return BigInt(hex);
}

async function loadAddresses(filePath: string): Promise<AddressesJson | null> {
  try {
    const raw = await readFile(filePath, "utf-8");
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const envParam = searchParams.get("env") as EvmEnv | null;
  const env = envParam ?? detectEvmEnv();
  const config = getEvmConfig(env);

  // No RPC URL configured
  if (!config.rpcUrl) {
    const resp: EvmResponse = {
      env,
      chainId: null,
      blockNumber: null,
      networkName: config.networkName,
      rpcUrl: "Not configured",
      accounts: [],
      tokens: [],
      contracts: [],
      pools: [],
      seedingStatus: "not_seeded",
      timestamp: new Date().toISOString(),
      error: `No RPC URL configured for ${config.networkName}. Set the appropriate env var.`,
    };
    return NextResponse.json(resp);
  }

  const rpcUrl = config.rpcUrl;
  const addresses = await loadAddresses(config.addressesFile);

  // Batch 1: Chain info + account balances
  const [chainId, blockNumber, deployerBal, signerBal] = await Promise.all([
    ethChainId(rpcUrl),
    ethBlockNumber(rpcUrl),
    ethGetBalance(rpcUrl, EVM_KEY_ACCOUNTS.deployer.address),
    ethGetBalance(rpcUrl, EVM_KEY_ACCOUNTS.bridgeSigner.address),
  ]);

  // Accounts
  const accounts: EvmAccountInfo[] = [
    {
      label: EVM_KEY_ACCOUNTS.deployer.label,
      address: EVM_KEY_ACCOUNTS.deployer.address,
      ethBalance: deployerBal ? formatWei(deployerBal) : "N/A",
    },
    {
      label: EVM_KEY_ACCOUNTS.bridgeSigner.label,
      address: EVM_KEY_ACCOUNTS.bridgeSigner.address,
      ethBalance: signerBal ? formatWei(signerBal) : "N/A",
    },
  ];

  // Tokens
  const tokens: EvmTokenInfo[] = [];
  if (addresses?.tokens) {
    const tokenEntries = Object.entries(addresses.tokens);
    const supplies = await Promise.all(
      tokenEntries.map(([, t]) => tokenTotalSupply(rpcUrl, t.address).catch(() => null))
    );
    for (let i = 0; i < tokenEntries.length; i++) {
      const [symbol, t] = tokenEntries[i];
      tokens.push({
        symbol,
        address: t.address,
        decimals: t.decimals,
        totalSupply: supplies[i] !== null ? formatTokenAmount(supplies[i]!, t.decimals) : "N/A",
      });
    }
  }

  // Contracts
  const contracts: EvmContractInfo[] = [];
  if (addresses?.contracts) {
    for (const [name, address] of Object.entries(addresses.contracts)) {
      contracts.push({ name, address });
    }
  }

  // Pools
  const pools: EvmPoolInfo[] = [];
  const stateViewAddr = addresses?.contracts?.stateView;
  if (addresses?.pools && stateViewAddr) {
    const poolEntries = Object.entries(addresses.pools);

    // Parallel: getSlot0 + getLiquidity for each pool
    const slot0Results = await Promise.all(
      poolEntries.map(([, p]) =>
        p.state?.poolId
          ? getPoolSlot0(rpcUrl, stateViewAddr, p.state.poolId).catch(() => null)
          : Promise.resolve(null)
      )
    );
    const liquidityResults = await Promise.all(
      poolEntries.map(([, p]) =>
        p.state?.poolId
          ? getPoolLiquidity(rpcUrl, stateViewAddr, p.state.poolId).catch(() => null)
          : Promise.resolve(null)
      )
    );

    for (let i = 0; i < poolEntries.length; i++) {
      const [name, p] = poolEntries[i];
      const slot0 = slot0Results[i];
      const liquidity = liquidityResults[i];
      const state = p.state;
      const pricing = p.plan?.pricing;

      let price: number | null = null;
      let priceLabel = "";
      let tick: number | null = null;
      let lpFee: number | null = null;
      let error: string | undefined;

      if (slot0 && state?.currency0 && state?.currency1 && addresses.tokens) {
        tick = slot0.tick;
        lpFee = slot0.lpFee;

        // Find token decimals for currency0 and currency1
        const c0Addr = state.currency0.toLowerCase();
        const c1Addr = state.currency1.toLowerCase();
        let dec0 = 18;
        let dec1 = 18;
        let sym0 = "token0";
        let sym1 = "token1";

        for (const [sym, t] of Object.entries(addresses.tokens)) {
          if (t.address.toLowerCase() === c0Addr) {
            dec0 = t.decimals;
            sym0 = sym;
          }
          if (t.address.toLowerCase() === c1Addr) {
            dec1 = t.decimals;
            sym1 = sym;
          }
        }

        // sqrtPriceX96 gives currency1-per-currency0 price
        const rawPrice = computePrice(slot0.sqrtPriceX96, dec0, dec1);

        // Determine display direction from pricing config
        if (pricing?.base && pricing?.quote) {
          const baseAddr = addresses.tokens[pricing.base]?.address.toLowerCase();
          if (baseAddr === c0Addr) {
            // price is already base-per-quote direction (currency1/currency0)
            // But we want "1 base = X quote", and rawPrice = currency1/currency0
            // If base = currency0, then rawPrice = quote/base, which is what we want
            price = rawPrice;
            priceLabel = `1 ${pricing.base} = ${rawPrice.toFixed(4)} ${pricing.quote}`;
          } else {
            // base = currency1, so invert
            price = rawPrice > 0 ? 1 / rawPrice : 0;
            priceLabel = `1 ${pricing.base} = ${price.toFixed(4)} ${pricing.quote}`;
          }
        } else {
          price = rawPrice;
          priceLabel = `1 ${sym0} = ${rawPrice.toFixed(4)} ${sym1}`;
        }
      } else if (!slot0 && state?.poolId) {
        error = "Failed to fetch pool data";
      }

      pools.push({
        name,
        poolId: state?.poolId || "",
        currency0: state?.currency0 || "",
        currency1: state?.currency1 || "",
        fee: state?.fee ?? p.plan?.key?.fee ?? 0,
        tickSpacing: state?.tickSpacing ?? p.plan?.key?.tickSpacing ?? 0,
        tick,
        price,
        priceLabel,
        liquidity: liquidity !== null ? liquidity.toString() : null,
        lpFee,
        error,
      });
    }
  }

  // Engine wallet: ETH balance + token balances
  const engineAddr = EVM_KEY_ACCOUNTS.engine.address;
  const engineBal = await ethGetBalance(rpcUrl, engineAddr);

  let engineWallet: EvmResponse["engineWallet"];
  let seedingStatus: SeedingStatus = "not_seeded";

  if (addresses?.tokens) {
    const tokenEntries = Object.entries(addresses.tokens);
    const engineTokenBals = await Promise.all(
      tokenEntries.map(([, t]) =>
        tokenBalanceOf(rpcUrl, t.address, engineAddr).catch(() => null)
      )
    );

    engineWallet = {
      address: engineAddr,
      ethBalance: engineBal ? formatWei(engineBal) : "N/A",
      tokenBalances: tokenEntries.map(([symbol, t], i) => ({
        symbol,
        balance:
          engineTokenBals[i] !== null
            ? formatTokenAmount(engineTokenBals[i]!, t.decimals)
            : "0.00",
        address: t.address,
      })),
    };

    // Determine seeding status
    const hasWrappedTokens = engineTokenBals.some(
      (b, i) => b !== null && Number(b) > 0 && tokenEntries[i][0].startsWith("w")
    );
    const poolsHaveLiquidity =
      pools.length > 0 &&
      pools.every((p) => p.liquidity !== null && p.liquidity !== "0");

    if (poolsHaveLiquidity && hasWrappedTokens) {
      seedingStatus = "seeded";
    } else if (hasWrappedTokens || poolsHaveLiquidity) {
      seedingStatus = "partial";
    }
  } else {
    engineWallet = {
      address: engineAddr,
      ethBalance: engineBal ? formatWei(engineBal) : "N/A",
      tokenBalances: [],
    };
  }

  const resp: EvmResponse = {
    env,
    chainId,
    blockNumber,
    networkName: config.networkName,
    rpcUrl: maskRpcUrl(rpcUrl),
    accounts,
    tokens,
    contracts,
    pools,
    engineWallet,
    seedingStatus,
    timestamp: new Date().toISOString(),
  };

  return NextResponse.json(resp);
}
