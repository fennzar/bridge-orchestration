/**
 * Orderbook Generation Module
 *
 * Generates a realistic orderbook around a given price point.
 * Depth levels decay exponentially to simulate realistic liquidity distribution.
 */

// Configuration
let config = {
  spreadBps: 50, // Spread in basis points (50 = 0.5%)
  depthLevels: 20, // Number of price levels on each side
  baseQty: 1000, // Base quantity at best bid/ask
  qtyDecayFactor: 0.85, // Quantity decay per level
  priceStepBps: 10, // Price step between levels in bps
  randomness: 0.15, // Random variation factor (0-1)
};

/**
 * Set configuration
 */
export function setConfig(newConfig) {
  config = { ...config, ...newConfig };
}

/**
 * Get current configuration
 */
export function getConfig() {
  return { ...config };
}

/**
 * Generate a pseudo-random number based on price (deterministic for same price)
 */
function seededRandom(seed) {
  const x = Math.sin(seed) * 10000;
  return x - Math.floor(x);
}

/**
 * Generate orderbook around a price
 * @param {number} midPrice - The mid price in USD
 * @param {number} limit - Maximum number of levels per side
 * @returns {{ bids: Array<{price: number, qty: number}>, asks: Array<{price: number, qty: number}> }}
 */
export function generateOrderbook(midPrice, limit = 20) {
  const effectiveLimit = Math.min(limit, config.depthLevels);
  const halfSpreadPct = config.spreadBps / 10000 / 2;
  const priceStepPct = config.priceStepBps / 10000;

  const bestBid = midPrice * (1 - halfSpreadPct);
  const bestAsk = midPrice * (1 + halfSpreadPct);

  const bids = [];
  const asks = [];

  for (let i = 0; i < effectiveLimit; i++) {
    // Calculate price levels
    const bidPrice = bestBid * (1 - priceStepPct * i);
    const askPrice = bestAsk * (1 + priceStepPct * i);

    // Calculate quantity with decay and randomness
    const baseDecay = Math.pow(config.qtyDecayFactor, i);
    const bidRandom = 1 + (seededRandom(bidPrice * 1000) - 0.5) * config.randomness * 2;
    const askRandom = 1 + (seededRandom(askPrice * 1000) - 0.5) * config.randomness * 2;

    const bidQty = config.baseQty * baseDecay * bidRandom;
    const askQty = config.baseQty * baseDecay * askRandom;

    bids.push({
      price: Math.round(bidPrice * 1e8) / 1e8,
      qty: Math.round(bidQty * 100) / 100,
    });

    asks.push({
      price: Math.round(askPrice * 1e8) / 1e8,
      qty: Math.round(askQty * 100) / 100,
    });
  }

  return { bids, asks };
}

/**
 * Calculate total depth in USD
 */
export function calculateDepthUsd(levels) {
  return levels.reduce((sum, level) => sum + level.price * level.qty, 0);
}
