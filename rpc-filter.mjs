/**
 * EVM RPC Method Filter Proxy
 *
 * Sits between nginx and Anvil to allowlist safe JSON-RPC methods.
 * Blocks dangerous methods like eth_sendTransaction (which Anvil auto-signs
 * with dev accounts) and all anvil_*/debug_* admin methods.
 *
 * eth_sendRawTransaction IS allowed — it requires a real wallet signature,
 * so MetaMask users can still send transactions normally.
 *
 * Background: Exposing Anvil's RPC port publicly allows arbitrary code
 * execution via eth_sendTransaction → contract deploy → vm.ffi() cheatcode.
 * This proxy prevents that attack vector.
 *
 * Usage: node rpc-filter.mjs
 * Listens: 127.0.0.1:8546
 * Upstream: 127.0.0.1:8545 (Anvil)
 */
import { createServer } from "http";

const ANVIL = "http://127.0.0.1:8545";
const PORT = parseInt(process.env.RPC_FILTER_PORT || "8546", 10);

const ALLOWED = new Set([
  // Chain / network
  "eth_chainId", "eth_syncing", "net_listening", "net_version",
  "web3_clientVersion", "web3_sha3",

  // Block & transaction reads
  "eth_blockNumber", "eth_getBlockByHash", "eth_getBlockByNumber",
  "eth_getBlockTransactionCountByHash", "eth_getBlockTransactionCountByNumber",
  "eth_getTransactionByHash", "eth_getTransactionCount",
  "eth_getTransactionReceipt",

  // Account & contract reads
  "eth_accounts", "eth_getBalance", "eth_getCode", "eth_getStorageAt",
  "eth_call", "eth_estimateGas",

  // Gas
  "eth_gasPrice", "eth_feeHistory", "eth_maxPriorityFeePerGas",

  // Logs & filters
  "eth_getLogs", "eth_getFilterChanges", "eth_getFilterLogs",
  "eth_newBlockFilter", "eth_newFilter", "eth_uninstallFilter",
  "eth_subscribe", "eth_unsubscribe",

  // Wallet-signed transactions (safe — requires real private key)
  "eth_sendRawTransaction",
]);

createServer(async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (req.method === "OPTIONS") { res.writeHead(204); return res.end(); }
  if (req.method !== "POST") { res.writeHead(405); return res.end(); }

  const chunks = [];
  for await (const c of req) chunks.push(c);
  const body = Buffer.concat(chunks).toString();

  let parsed;
  try { parsed = JSON.parse(body); } catch {
    res.writeHead(400, { "Content-Type": "application/json" });
    return res.end(JSON.stringify({ error: "invalid json" }));
  }

  const requests = Array.isArray(parsed) ? parsed : [parsed];
  for (const r of requests) {
    if (!ALLOWED.has(r.method)) {
      res.writeHead(403, { "Content-Type": "application/json" });
      return res.end(JSON.stringify({
        jsonrpc: "2.0", id: r.id,
        error: { code: -32601, message: "method not allowed: " + r.method },
      }));
    }
  }

  try {
    const upstream = await fetch(ANVIL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    res.writeHead(upstream.status, { "Content-Type": "application/json" });
    res.end(await upstream.text());
  } catch {
    res.writeHead(502, { "Content-Type": "application/json" });
    res.end(JSON.stringify({
      jsonrpc: "2.0", id: requests[0]?.id,
      error: { code: -32000, message: "upstream unavailable" },
    }));
  }
}).listen(PORT, "127.0.0.1", () => console.log(`RPC filter proxy on :${PORT}`));
