import * as path from "path";
import type { EvmEnv } from "./types";

// Docker services (infrastructure layer — Docker Compose)
export const DOCKER_SERVICES = [
  { name: "zephyr-node1", container: "zephyr-node1", port: 47767, type: "daemon" as const },
  { name: "zephyr-node2", container: "zephyr-node2", port: 47867, type: "daemon" as const },
  { name: "wallet-gov", container: "zephyr-wallet-gov", port: 48769, type: "wallet" as const },
  { name: "wallet-miner", container: "zephyr-wallet-miner", port: 48767, type: "wallet" as const },
  { name: "wallet-test", container: "zephyr-wallet-test", port: 48768, type: "wallet" as const },
  { name: "wallet-bridge", container: "zephyr-wallet-bridge", port: 48770, type: "wallet" as const },
  { name: "wallet-engine", container: "zephyr-wallet-engine", port: 48771, type: "wallet" as const },
  { name: "wallet-cex", container: "zephyr-wallet-cex", port: 48772, type: "wallet" as const },
  { name: "fake-oracle", container: "zephyr-fake-oracle", port: 5555, type: "oracle" as const },
  { name: "fake-orderbook", container: "zephyr-fake-orderbook", port: 5556, type: "orderbook" as const },
  { name: "redis", container: "zephyr-redis", port: 6380, type: "infra" as const },
  { name: "postgres", container: "zephyr-postgres", port: 5432, type: "infra" as const },
  { name: "anvil", container: "zephyr-anvil", port: 8545, type: "evm" as const },
  { name: "blockscout", container: "zephyr-blockscout-proxy", port: 4000, type: "explorer" as const, optional: true },
] as const;

export type DockerServiceType = (typeof DOCKER_SERVICES)[number]["type"];

// Overmind processes (app layer — Procfile.dev only)
export const OVERMIND_PROCESSES = [
  { name: "bridge-web", port: 7050, group: "bridge" as const },
  { name: "bridge-api", port: 7051, group: "bridge" as const },
  { name: "bridge-watchers", port: undefined, group: "bridge" as const },
  { name: "engine-web", port: 7000, group: "engine" as const },
  { name: "engine-watchers", port: undefined, group: "engine" as const },
  { name: "dashboard", port: 7100, group: "dashboard" as const },
] as const;

export type AppGroup = "bridge" | "engine" | "dashboard";

// Paths
export const ORCH_DIR = process.env.ORCHESTRATION_PATH || path.resolve(process.cwd(), "..");
export const OVERMIND_SOCKET = process.env.OVERMIND_SOCK || path.join(ORCH_DIR, ".overmind-dev.sock");
export const DC_CMD = `docker compose -p bridge --env-file ${ORCH_DIR}/.env -f ${ORCH_DIR}/docker/compose.base.yml -f ${ORCH_DIR}/docker/compose.dev.yml -f ${ORCH_DIR}/docker/compose.blockscout.yml`;

// RPC ports for direct access
export const DAEMON_PRIMARY_PORT = 47767;
export const DAEMON_SECONDARY_PORT = 47867;
export const WALLET_GOV_PORT = 48769;
export const WALLET_MINER_PORT = 48767;
export const WALLET_TEST_PORT = 48768;
export const WALLET_BRIDGE_PORT = 48770;
export const WALLET_ENGINE_PORT = 48771;
export const WALLET_CEX_PORT = 48772;

export const WALLET_PORTS: Record<string, number> = {
  gov: WALLET_GOV_PORT,
  miner: WALLET_MINER_PORT,
  test: WALLET_TEST_PORT,
  bridge: WALLET_BRIDGE_PORT,
  engine: WALLET_ENGINE_PORT,
  cex: WALLET_CEX_PORT,
};
export const ORACLE_PORT = 5555;
export const ORDERBOOK_PORT = 5556;
export const ANVIL_PORT = 8545;

// --- EVM Configuration ---

export interface EvmConfig {
  rpcUrl: string | null;
  chainId: number;
  networkName: string;
  addressesFile: string;
}

export function detectEvmEnv(): EvmEnv {
  const env = process.env.BRIDGE_ENV?.toLowerCase();
  if (env === "sepolia") return "sepolia";
  if (env === "mainnet") return "mainnet";
  return "local";
}

export function getEvmConfig(env?: EvmEnv): EvmConfig {
  const resolved = env ?? detectEvmEnv();
  switch (resolved) {
    case "sepolia":
      return {
        rpcUrl: process.env.EVM_RPC_HTTP_SEPOLIA || null,
        chainId: 11155111,
        networkName: "Sepolia",
        addressesFile: path.join(ORCH_DIR, "config/addresses.sepolia.json"),
      };
    case "mainnet":
      return {
        rpcUrl: process.env.EVM_RPC_HTTP_MAINNET || null,
        chainId: 1,
        networkName: "Ethereum Mainnet",
        addressesFile: path.join(ORCH_DIR, "config/addresses.mainnet.json"),
      };
    default:
      return {
        rpcUrl: process.env.EVM_RPC_HTTP || "http://127.0.0.1:8545",
        chainId: 31337,
        networkName: "Anvil (Local)",
        addressesFile: path.join(ORCH_DIR, "config/addresses.local.json"),
      };
  }
}

export const EVM_KEY_ACCOUNTS = {
  deployer: {
    label: "Deployer",
    address: process.env.DEPLOYER_ADDRESS ?? "",
  },
  bridgeSigner: {
    label: "Bridge Signer",
    address: process.env.BRIDGE_SIGNER_ADDRESS ?? "",
  },
  engine: {
    label: "Engine",
    address: process.env.ENGINE_ADDRESS ?? "",
  },
};

export function maskRpcUrl(url: string): string {
  try {
    const u = new URL(url);
    // Local URLs don't need masking
    if (u.hostname === "127.0.0.1" || u.hostname === "localhost") return url;
    // Mask path after first segment (API keys often in path)
    const segments = u.pathname.split("/").filter(Boolean);
    if (segments.length > 1) {
      u.pathname = "/" + segments[0] + "/***";
    }
    // Mask query params
    if (u.search) u.search = "?***";
    return u.toString();
  } catch {
    return "***";
  }
}
