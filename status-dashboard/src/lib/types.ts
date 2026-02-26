// Lifecycle states for the two-layer architecture
export type LifecycleState = "stopped" | "initializing" | "infra-only" | "degraded" | "running";

// Docker container status
export interface ContainerStatus {
  name: string;
  container: string;
  status: "running" | "stopped" | "error";
  port: number;
  type: string;
  health?: string;
  // Per-service metrics (populated for specific types)
  height?: number;
  mining?: { active: boolean; threads?: number; speed?: number };
  address?: string;
  balance?: { unlocked: string; total: string };
  price?: number;
  blockNumber?: number;
}

// Overmind process status
export interface AppStatus {
  name: string;
  status: "running" | "error" | "stopped";
  port?: number;
  group: string;
  logs: string[];
  health?: {
    portListening: boolean | null;
    httpOk: boolean | null;
    errors: string[];
  };
}

// Chain vitals for overview
export interface ChainVitals {
  height: number | null;
  oraclePrice: number | null;
  anvilBlock: number | null;
  checkpoint: number | null;
  miningActive: boolean;
}

// Overview API response
export interface StatusResponse {
  lifecycle: LifecycleState;
  infraSummary: { running: number; total: number };
  appsSummary: { running: number; healthy: number; total: number };
  chain: ChainVitals;
  timestamp: string;
}

// Infrastructure API response
export interface InfraResponse {
  containers: ContainerStatus[];
  timestamp: string;
}

// Apps API response
export interface AppsResponse {
  processes: AppStatus[];
  timestamp: string;
}

// Full reserve/protocol state from get_reserve_info
export interface ReserveInfo {
  reserveRatio: string;
  reserveRatioMa: string;
  spot: number;
  movingAverage: number;
  stableRate: number;
  stableRateMa: number;
  reserveRate: number;
  reserveRateMa: number;
  yieldPrice: number;
  numStables: number;
  numReserves: number;
  numZyield: number;
  assets: number;
  assetsMa: number;
  liabilities: number;
  equity: number;
  equityMa: number;
  zephReserve: number;
  zyieldReserve: number;
  height: number;
  hfVersion: number;
}

// Chain API response
export interface ChainResponse {
  nodes: {
    node1: { height: number | null; synced: boolean };
    node2: { height: number | null; synced: boolean };
  };
  mining: { active: boolean; threads?: number; speed?: number };
  checkpoint: { current: number | null; saved: number | null };
  oracle: {
    price: number | null;
    mode: "manual" | "mirror";
    mirrorSpot?: number;
    mirrorLastFetch?: string;
  };
  wallets: WalletBalance[];
  reserve?: ReserveInfo;
  timestamp: string;
}

export type AssetType = "ZPH" | "ZSD" | "ZRS" | "ZYS";

export interface WalletBalance {
  name: string;
  port: number;
  address?: string;
  balances: {
    ZPH: string;
    ZSD: string;
    ZRS: string;
    ZYS: string;
  };
  error?: string;
}

export interface TransferResponse {
  success: boolean;
  txHash?: string;
  error?: string;
}

// EVM types
export type EvmEnv = "local" | "sepolia" | "mainnet";

export interface EvmAccountInfo {
  label: string;
  address: string;
  ethBalance: string;
}

export interface EvmTokenInfo {
  symbol: string;
  address: string;
  decimals: number;
  totalSupply: string;
}

export interface EvmContractInfo {
  name: string;
  address: string;
}

export interface EvmPoolInfo {
  name: string;
  poolId: string;
  currency0: string;
  currency1: string;
  fee: number;
  tickSpacing: number;
  tick: number | null;
  price: number | null;
  priceLabel: string;
  liquidity: string | null;
  lpFee: number | null;
  error?: string;
}

export interface EvmEngineWallet {
  address: string;
  ethBalance: string;
  tokenBalances: { symbol: string; balance: string; address: string }[];
}

export type SeedingStatus = "seeded" | "partial" | "not_seeded";

export interface EvmResponse {
  env: EvmEnv;
  chainId: number | null;
  blockNumber: number | null;
  networkName: string;
  rpcUrl: string;
  accounts: EvmAccountInfo[];
  tokens: EvmTokenInfo[];
  contracts: EvmContractInfo[];
  pools: EvmPoolInfo[];
  engineWallet?: EvmEngineWallet;
  seedingStatus: SeedingStatus;
  timestamp: string;
  error?: string;
}

// Test info
export interface TestInfo {
  id: string;
  name: string;
  level: "L1" | "L2" | "L3" | "L4" | "L5";
  category: string;
  sublevel?: string;
}
