import { ANVIL_PORT, ORACLE_PORT } from "./constants";

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
  const unlocked = (Number(result.unlocked_balance ?? 0) / 1e12).toFixed(4);
  const total = (Number(result.balance ?? 0) / 1e12).toFixed(4);
  return { unlocked, total };
}

export async function oracleGet(): Promise<number | null> {
  try {
    const response = await fetch(`http://127.0.0.1:${ORACLE_PORT}/status`, {
      signal: AbortSignal.timeout(2000),
    });
    if (!response.ok) return null;
    const data = await response.json();
    // Oracle stores price in atomic units (1e12)
    const spot = data.spot ?? data.price;
    if (spot !== undefined) return Number(spot) / 1e12;
    return null;
  } catch {
    return null;
  }
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
      const amount = (Number(entry.unlocked_balance ?? 0) / 1e12).toFixed(4);
      switch (entry.asset_type) {
        case "ZPH": case "ZEPH": balances.ZPH = amount; break;
        case "ZSD": case "ZEPHUSD": balances.ZSD = amount; break;
        case "ZRS": case "ZEPHRSV": balances.ZRS = amount; break;
        case "ZYS": case "ZYIELD": balances.ZYS = amount; break;
      }
    }
  } else {
    // Fallback: top-level unlocked_balance for ZPH
    balances.ZPH = (Number(result.unlocked_balance ?? 0) / 1e12).toFixed(4);
    if (result.unlocked_zsd_balance !== undefined)
      balances.ZSD = (Number(result.unlocked_zsd_balance) / 1e12).toFixed(4);
    if (result.unlocked_zrs_balance !== undefined)
      balances.ZRS = (Number(result.unlocked_zrs_balance) / 1e12).toFixed(4);
    if (result.unlocked_zys_balance !== undefined)
      balances.ZYS = (Number(result.unlocked_zys_balance) / 1e12).toFixed(4);
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
