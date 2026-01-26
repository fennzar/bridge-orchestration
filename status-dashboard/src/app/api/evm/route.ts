import { NextResponse } from "next/server";
import { readFile } from "fs/promises";
import {
  getEvmConfig,
  detectEvmEnv,
  EVM_KEY_ACCOUNTS,
  maskRpcUrl,
} from "@/lib/constants";
import {
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
} from "@/lib/types";

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
    timestamp: new Date().toISOString(),
  };

  return NextResponse.json(resp);
}
