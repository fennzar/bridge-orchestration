import { ANVIL_PORT, ORACLE_PORT, ORDERBOOK_PORT } from "./constants";

/** Convert atomic (1e12) Zephyr value to display number */
export function fromAtomic(value: unknown): number {
  return Number(value ?? 0) / 1e12;
}

/** Convert atomic (1e12) Zephyr value to fixed-decimal string */
export function fromAtomicStr(value: unknown, decimals = 4): string {
  return fromAtomic(value).toFixed(decimals);
}

export async function zephyrRpc(
  port: number,
  method: string,
  params?: Record<string, unknown>
): Promise<{ result?: Record<string, unknown>; error?: string }> {
  try {
    const response = await fetch(`http://127.0.0.1:${port}/json_rpc`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: "0", method, params: params || {} }),
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

export async function walletRpc(
  port: number,
  method: string,
  params?: Record<string, unknown>
): Promise<{ result?: Record<string, unknown>; error?: string }> {
  return zephyrRpc(port, method, params);
}

/** Daemon "other" RPC — endpoints like /start_mining, /stop_mining, /mining_status */
export async function daemonOtherRpc(
  port: number,
  endpoint: string,
  params?: Record<string, unknown>
): Promise<{ result?: Record<string, unknown>; error?: string }> {
  try {
    const response = await fetch(`http://127.0.0.1:${port}/${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(params || {}),
      signal: AbortSignal.timeout(3000),
    });
    if (!response.ok) return { error: `HTTP ${response.status}` };
    const data = await response.json();
    if (data.status && data.status !== "OK") return { error: data.status };
    return { result: data };
  } catch {
    return { error: "Connection refused" };
  }
}

export async function getDaemonInfo(port: number) {
  const { result } = await zephyrRpc(port, "get_info");
  if (!result) return null;

  // Mining status is on a separate /mining_status endpoint (not in get_info)
  let miningActive = false;
  let miningThreads: number | undefined;
  let miningSpeed: number | undefined;
  const { result: mining } = await daemonOtherRpc(port, "mining_status");
  if (mining) {
    miningActive = mining.active === true;
    miningThreads = mining.threads_count as number | undefined;
    miningSpeed = mining.speed as number | undefined;
  }

  return {
    height: result.height as number | undefined,
    synced: (result.status === "OK") as boolean,
    miningActive,
    miningThreads,
    miningSpeed,
    difficulty: result.difficulty as number | undefined,
  };
}

export async function getWalletAddress(port: number): Promise<string | null> {
  const { result } = await walletRpc(port, "get_address");
  return (result?.address as string) || null;
}

export async function getWalletBalance(port: number): Promise<{ unlocked: string; total: string } | null> {
  const { result } = await walletRpc(port, "get_balance");
  if (!result) return null;
  const unlocked = fromAtomicStr(result.unlocked_balance);
  const total = fromAtomicStr(result.balance);
  return { unlocked, total };
}

export async function oracleSet(price: number): Promise<boolean> {
  try {
    const response = await fetch(`http://127.0.0.1:${ORACLE_PORT}/set-price`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spot: Math.round(price * 1e12) }),
      signal: AbortSignal.timeout(2000),
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function getMultiAssetBalance(
  port: number
): Promise<{ ZPH: string; ZSD: string; ZRS: string; ZYS: string; error?: string }> {
  const defaults = { ZPH: "0.0000", ZSD: "0.0000", ZRS: "0.0000", ZYS: "0.0000" };
  const { result, error } = await walletRpc(port, "get_balance", { all_assets: true });
  if (error) return { ...defaults, error };
  if (!result) return { ...defaults, error: "No response" };

  const balances = { ...defaults };

  // Parse per-asset balances array (zephyr-cli style with all_assets: true)
  const balArr = result.balances as Array<{ asset_type: string; unlocked_balance: number }> | undefined;
  if (Array.isArray(balArr)) {
    for (const entry of balArr) {
      const amount = fromAtomicStr(entry.unlocked_balance);
      switch (entry.asset_type) {
        case "ZPH": case "ZEPH": balances.ZPH = amount; break;
        case "ZSD": case "ZEPHUSD": balances.ZSD = amount; break;
        case "ZRS": case "ZEPHRSV": balances.ZRS = amount; break;
        case "ZYS": case "ZYIELD": balances.ZYS = amount; break;
      }
    }
  } else {
    // Fallback: top-level unlocked_balance for ZPH
    balances.ZPH = fromAtomicStr(result.unlocked_balance);
    if (result.unlocked_zsd_balance !== undefined)
      balances.ZSD = fromAtomicStr(result.unlocked_zsd_balance);
    if (result.unlocked_zrs_balance !== undefined)
      balances.ZRS = fromAtomicStr(result.unlocked_zrs_balance);
    if (result.unlocked_zys_balance !== undefined)
      balances.ZYS = fromAtomicStr(result.unlocked_zys_balance);
  }

  return balances;
}

export async function walletTransfer(
  fromPort: number,
  toAddress: string,
  amount: number,
  sourceAsset: string,
  destAsset: string
): Promise<{ success: boolean; txHash?: string; error?: string }> {
  const atomicAmount = Math.round(amount * 1e12);
  const { result, error } = await walletRpc(fromPort, "transfer", {
    destinations: [{ amount: atomicAmount, address: toAddress }],
    source_asset: sourceAsset,
    destination_asset: destAsset,
  });
  if (error) return { success: false, error };
  if (!result) return { success: false, error: "No response" };
  const txHash = (result.tx_hash as string) || (result.tx_hash_list as string[])?.[0];
  return { success: true, txHash };
}

export async function walletRescan(
  port: number,
  hard?: boolean
): Promise<{ success: boolean; error?: string }> {
  const { error } = await walletRpc(port, "rescan_blockchain", hard ? { hard: true } : {});
  if (error) return { success: false, error };
  return { success: true };
}

export async function orderbookGet(): Promise<Record<string, unknown> | null> {
  try {
    const response = await fetch(`http://127.0.0.1:${ORDERBOOK_PORT}/status`, {
      signal: AbortSignal.timeout(2000),
    });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

export async function orderbookSetSpread(bps: number): Promise<boolean> {
  try {
    const response = await fetch(`http://127.0.0.1:${ORDERBOOK_PORT}/set-spread`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ spreadBps: bps }),
      signal: AbortSignal.timeout(2000),
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function oracleGetStatus(): Promise<{
  mode: "manual" | "mirror";
  price: number | null;
  mirrorSpot?: number;
  mirrorLastFetch?: string;
} | null> {
  try {
    const response = await fetch(`http://127.0.0.1:${ORACLE_PORT}/status`, {
      signal: AbortSignal.timeout(2000),
    });
    if (!response.ok) return null;
    const data = await response.json();
    const spot = data.spot ?? data.price;
    const price = spot !== undefined ? fromAtomic(spot) : null;
    const mode = data.mode === "mirror" ? "mirror" as const : "manual" as const;
    const result: {
      mode: "manual" | "mirror";
      price: number | null;
      mirrorSpot?: number;
      mirrorLastFetch?: string;
    } = { mode, price };
    if (data.mirror_spot !== undefined) result.mirrorSpot = fromAtomic(data.mirror_spot);
    if (data.mirror_last_fetch) result.mirrorLastFetch = data.mirror_last_fetch;
    return result;
  } catch {
    return null;
  }
}

export async function oracleSetMode(mode: "manual" | "mirror"): Promise<boolean> {
  try {
    const response = await fetch(`http://127.0.0.1:${ORACLE_PORT}/set-mode`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode }),
      signal: AbortSignal.timeout(2000),
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function anvilMine(blocks?: number): Promise<boolean> {
  try {
    const method = blocks && blocks > 1 ? "anvil_mine" : "evm_mine";
    const params = blocks && blocks > 1 ? [`0x${blocks.toString(16)}`] : [];
    const response = await fetch(`http://127.0.0.1:${ANVIL_PORT}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method, params }),
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) return false;
    const data = await response.json();
    return data.result !== undefined;
  } catch {
    return false;
  }
}

export async function anvilBlockNumber(): Promise<number | null> {
  try {
    const response = await fetch(`http://127.0.0.1:${ANVIL_PORT}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "eth_blockNumber", params: [] }),
      signal: AbortSignal.timeout(2000),
    });
    if (!response.ok) return null;
    const data = await response.json();
    return parseInt(data.result, 16);
  } catch {
    return null;
  }
}
