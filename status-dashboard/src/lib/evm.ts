// EVM RPC helpers — zero npm dependencies, manual ABI encoding for simple calls

// --- Low-level RPC ---

export async function evmRpc(
  rpcUrl: string,
  method: string,
  params: unknown[] = []
): Promise<{ result?: unknown; error?: string }> {
  try {
    const response = await fetch(rpcUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
      signal: AbortSignal.timeout(3000),
    });
    if (!response.ok) return { error: `HTTP ${response.status}` };
    const data = await response.json();
    if (data.error) return { error: data.error.message || "RPC error" };
    return { result: data.result };
  } catch {
    return { error: "Connection refused" };
  }
}

export async function ethCall(
  rpcUrl: string,
  to: string,
  data: string
): Promise<string | null> {
  const { result, error } = await evmRpc(rpcUrl, "eth_call", [
    { to, data },
    "latest",
  ]);
  if (error || !result) return null;
  return result as string;
}

export async function ethGetBalance(
  rpcUrl: string,
  address: string
): Promise<string | null> {
  const { result, error } = await evmRpc(rpcUrl, "eth_getBalance", [
    address,
    "latest",
  ]);
  if (error || !result) return null;
  return result as string;
}

export async function ethChainId(rpcUrl: string): Promise<number | null> {
  const { result, error } = await evmRpc(rpcUrl, "eth_chainId");
  if (error || !result) return null;
  return parseInt(result as string, 16);
}

export async function ethBlockNumber(rpcUrl: string): Promise<number | null> {
  const { result, error } = await evmRpc(rpcUrl, "eth_blockNumber");
  if (error || !result) return null;
  return parseInt(result as string, 16);
}

// --- ABI encoding (hardcoded selectors) ---

const SEL_TOTAL_SUPPLY = "0x18160ddd";
const SEL_GET_SLOT0 = "0xc815641c"; // getSlot0(bytes32)
const SEL_GET_LIQUIDITY = "0xfa6793d5"; // getLiquidity(bytes32)

function padBytes32(val: string): string {
  return val.toLowerCase().replace("0x", "").padStart(64, "0");
}

// --- Token queries ---

export async function tokenTotalSupply(
  rpcUrl: string,
  tokenAddr: string
): Promise<bigint | null> {
  const hex = await ethCall(rpcUrl, tokenAddr, SEL_TOTAL_SUPPLY);
  if (!hex || hex === "0x") return null;
  return BigInt(hex);
}

// --- StateView pool queries ---

export interface Slot0Data {
  sqrtPriceX96: bigint;
  tick: number;
  protocolFee: number;
  lpFee: number;
}

export async function getPoolSlot0(
  rpcUrl: string,
  stateViewAddr: string,
  poolId: string
): Promise<Slot0Data | null> {
  const data = SEL_GET_SLOT0 + padBytes32(poolId);
  const hex = await ethCall(rpcUrl, stateViewAddr, data);
  if (!hex || hex.length < 2 + 4 * 64) return null;

  const raw = hex.slice(2); // strip 0x
  const sqrtPriceX96 = BigInt("0x" + raw.slice(0, 64));
  // int24 tick — occupies the low 24 bits of a 256-bit word
  const tickRaw = parseInt(raw.slice(64, 128), 16);
  const tick = tickRaw >= 0x800000 ? tickRaw - 0x1000000 : tickRaw;
  const protocolFee = parseInt(raw.slice(128, 192), 16);
  const lpFee = parseInt(raw.slice(192, 256), 16);

  return { sqrtPriceX96, tick, protocolFee, lpFee };
}

export async function getPoolLiquidity(
  rpcUrl: string,
  stateViewAddr: string,
  poolId: string
): Promise<bigint | null> {
  const data = SEL_GET_LIQUIDITY + padBytes32(poolId);
  const hex = await ethCall(rpcUrl, stateViewAddr, data);
  if (!hex || hex === "0x") return null;
  return BigInt(hex);
}

// --- Price math ---

export function computePrice(
  sqrtPriceX96: bigint,
  token0Decimals: number,
  token1Decimals: number
): number {
  // price = (sqrtPriceX96 / 2^96)^2 × 10^(dec0 - dec1)
  // Use BigInt for squaring, then scale down
  const numerator = sqrtPriceX96 * sqrtPriceX96;
  const Q192 = BigInt(1) << BigInt(192);

  // Scale to preserve precision: multiply by 10^18 before dividing
  const SCALE = BigInt(10) ** BigInt(18);
  const scaledPrice = (numerator * SCALE) / Q192;

  // Convert to Number, apply decimal adjustment
  const price = Number(scaledPrice) / 1e18;
  const decimalAdjust = Math.pow(10, token0Decimals - token1Decimals);
  return price * decimalAdjust;
}

// --- Formatting ---

export function formatWei(weiHex: string, displayDecimals = 4): string {
  const wei = BigInt(weiHex);
  const eth = Number(wei) / 1e18;
  return eth.toLocaleString(undefined, {
    minimumFractionDigits: displayDecimals,
    maximumFractionDigits: displayDecimals,
  });
}

export function formatTokenAmount(
  raw: bigint,
  tokenDecimals: number,
  displayDecimals = 2
): string {
  const divisor = 10 ** tokenDecimals;
  const value = Number(raw) / divisor;
  return value.toLocaleString(undefined, {
    minimumFractionDigits: displayDecimals,
    maximumFractionDigits: displayDecimals,
  });
}
