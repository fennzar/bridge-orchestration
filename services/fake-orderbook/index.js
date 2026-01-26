/**
 * Fake Orderbook Service
 *
 * Provides a MEXC-compatible REST and WebSocket API that generates an orderbook
 * around the current fake oracle price. Used for DEVNET testing to enable
 * controllable CEX data for RR mode testing.
 *
 * REST Endpoints:
 *   GET  /api/v3/depth       - MEXC-compatible orderbook depth
 *   GET  /status             - Current price, spread, config
 *   POST /set-spread         - Adjust spread dynamically
 *
 * WebSocket:
 *   WS /                     - Real-time depth updates (MEXC-compatible)
 */

import http from 'http';
import { WebSocketServer } from 'ws';
import { generateOrderbook, setConfig, getConfig } from './orderbook.js';

const PORT = parseInt(process.env.FAKE_ORDERBOOK_PORT || '5556', 10);
const FAKE_ORACLE_URL = process.env.FAKE_ORACLE_URL || 'http://127.0.0.1:5555';
const ORACLE_POLL_INTERVAL_MS = parseInt(process.env.ORACLE_POLL_INTERVAL_MS || '5000', 10);
const WS_BROADCAST_INTERVAL_MS = parseInt(process.env.WS_BROADCAST_INTERVAL_MS || '1000', 10);

// Current oracle price (in USD, not atomic units)
let currentPriceUsd = 15.0;
let lastOracleUpdate = null;
let updateSequence = 0;

/**
 * Fetch current price from fake oracle
 */
async function fetchOraclePrice() {
  try {
    const res = await fetch(`${FAKE_ORACLE_URL}/status`);
    if (!res.ok) {
      console.error(`[oracle] Failed to fetch: ${res.status}`);
      return;
    }
    const data = await res.json();
    // Oracle returns spot in atomic units (1e12 = 1 USD)
    const spotAtomic = data.spot || 0;
    const priceUsd = spotAtomic / 1e12;
    if (priceUsd > 0 && priceUsd !== currentPriceUsd) {
      const oldPrice = currentPriceUsd;
      currentPriceUsd = priceUsd;
      lastOracleUpdate = Date.now();
      console.log(`[oracle] Price updated: $${oldPrice.toFixed(4)} -> $${currentPriceUsd.toFixed(4)}`);
    }
  } catch (err) {
    console.error(`[oracle] Error fetching price: ${err.message}`);
  }
}

/**
 * Format orderbook as MEXC-compatible depth response
 */
function formatMexcDepth(symbol, limit = 20) {
  const orderbook = generateOrderbook(currentPriceUsd, limit);
  updateSequence++;

  return {
    lastUpdateId: updateSequence,
    bids: orderbook.bids.map((level) => [level.price.toFixed(8), level.qty.toFixed(8)]),
    asks: orderbook.asks.map((level) => [level.price.toFixed(8), level.qty.toFixed(8)]),
  };
}

/**
 * HTTP request handler
 */
function handleRequest(req, res) {
  const url = new URL(req.url, `http://localhost:${PORT}`);

  // CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  // GET /api/v3/depth - MEXC-compatible depth endpoint
  if (req.method === 'GET' && url.pathname === '/api/v3/depth') {
    const symbol = url.searchParams.get('symbol') || 'ZEPHUSDT';
    const limit = parseInt(url.searchParams.get('limit') || '20', 10);
    const depth = formatMexcDepth(symbol, Math.min(limit, 100));

    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(depth));
    console.log(`[http] GET /api/v3/depth symbol=${symbol} limit=${limit}`);
    return;
  }

  // GET /status - Current status
  if (req.method === 'GET' && url.pathname === '/status') {
    const config = getConfig();
    const orderbook = generateOrderbook(currentPriceUsd, 1);
    const bestBid = orderbook.bids[0]?.price || 0;
    const bestAsk = orderbook.asks[0]?.price || 0;
    const spread = bestAsk - bestBid;
    const spreadBps = currentPriceUsd > 0 ? (spread / currentPriceUsd) * 10000 : 0;

    res.writeHead(200, { 'Content-Type': 'application/json' });
    res.end(
      JSON.stringify({
        status: 'running',
        oracleUrl: FAKE_ORACLE_URL,
        oraclePriceUsd: currentPriceUsd,
        lastOracleUpdate: lastOracleUpdate ? new Date(lastOracleUpdate).toISOString() : null,
        bestBid,
        bestAsk,
        spread,
        spreadBps: Math.round(spreadBps * 100) / 100,
        config,
        updateSequence,
      })
    );
    return;
  }

  // POST /set-spread - Adjust spread
  if (req.method === 'POST' && url.pathname === '/set-spread') {
    let body = '';
    req.on('data', (chunk) => {
      body += chunk;
    });
    req.on('end', () => {
      try {
        const data = JSON.parse(body);
        const config = getConfig();
        if (data.spreadBps !== undefined) {
          config.spreadBps = parseInt(data.spreadBps, 10);
        }
        if (data.depthLevels !== undefined) {
          config.depthLevels = parseInt(data.depthLevels, 10);
        }
        setConfig(config);
        console.log(`[config] Updated: spreadBps=${config.spreadBps}, depthLevels=${config.depthLevels}`);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'OK', config }));
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Invalid JSON' }));
      }
    });
    return;
  }

  // 404
  res.writeHead(404, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ error: 'Not found' }));
}

// Create HTTP server
const server = http.createServer(handleRequest);

// Create WebSocket server
const wss = new WebSocketServer({ server });

// Track WebSocket clients
const clients = new Set();

wss.on('connection', (ws) => {
  console.log(`[ws] Client connected (total: ${clients.size + 1})`);
  clients.add(ws);

  // Handle subscription messages (MEXC-style)
  ws.on('message', (data) => {
    try {
      const msg = JSON.parse(data.toString());
      if (msg.method === 'SUBSCRIPTION') {
        // Acknowledge subscription
        ws.send(JSON.stringify({ id: msg.id, code: 0, msg: 'ok' }));
        console.log(`[ws] Client subscribed to: ${msg.params?.join(', ')}`);
      } else if (msg.method === 'PING') {
        ws.send(JSON.stringify({ method: 'PONG' }));
      }
    } catch {
      // Ignore parse errors
    }
  });

  ws.on('close', () => {
    clients.delete(ws);
    console.log(`[ws] Client disconnected (total: ${clients.size})`);
  });

  ws.on('error', (err) => {
    console.error(`[ws] Client error: ${err.message}`);
    clients.delete(ws);
  });
});

/**
 * Broadcast depth update to all WebSocket clients
 * Uses a simplified JSON format (not protobuf like real MEXC)
 */
function broadcastDepth() {
  if (clients.size === 0) return;

  const depth = formatMexcDepth('ZEPHUSDT', 20);
  const message = JSON.stringify({
    c: 'spot@public.aggre.depth.v3.api@100ms@ZEPHUSDT',
    d: {
      s: 'ZEPHUSDT',
      t: Date.now(),
      b: depth.bids,
      a: depth.asks,
    },
  });

  for (const client of clients) {
    if (client.readyState === 1) {
      // WebSocket.OPEN
      client.send(message);
    }
  }
}

// Initialize config from environment
setConfig({
  spreadBps: parseInt(process.env.FAKE_ORDERBOOK_SPREAD_BPS || '50', 10),
  depthLevels: parseInt(process.env.FAKE_ORDERBOOK_DEPTH_LEVELS || '20', 10),
});

// Start polling oracle
fetchOraclePrice();
setInterval(fetchOraclePrice, ORACLE_POLL_INTERVAL_MS);

// Start WebSocket broadcast
setInterval(broadcastDepth, WS_BROADCAST_INTERVAL_MS);

// Start server
server.listen(PORT, '0.0.0.0', () => {
  console.log(`Fake orderbook running on port ${PORT}`);
  console.log(`Oracle URL: ${FAKE_ORACLE_URL}`);
  console.log(`Current price: $${currentPriceUsd.toFixed(4)}`);
  console.log(`Endpoints:`);
  console.log(`  GET  /api/v3/depth?symbol=ZEPHUSDT&limit=20  - MEXC-compatible depth`);
  console.log(`  GET  /status                                  - Current status`);
  console.log(`  POST /set-spread {"spreadBps": 50}           - Adjust spread`);
  console.log(`  WS   /                                        - Real-time updates`);
});
