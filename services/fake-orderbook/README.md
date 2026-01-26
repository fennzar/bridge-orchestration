# Fake Orderbook Service

MEXC-compatible orderbook service for DEVNET testing. Generates realistic orderbook data that tracks the fake oracle price, enabling controllable CEX data for RR mode testing.

## Overview

This service provides:
- **REST API**: MEXC-compatible `/api/v3/depth` endpoint
- **WebSocket**: Real-time depth updates
- **Dynamic Configuration**: Adjustable spread and depth

## Usage

Started automatically when running `make dev-init`.

**Recommended workflow:**
```bash
# First time: Full init (starts fake-orderbook automatically)
make dev-init

# Between tests: Light reset (~30 sec, preserves fake-orderbook)
make dev-reset
```

### Manual Start

```bash
cd services/fake-orderbook
npm install
FAKE_ORACLE_URL=http://127.0.0.1:5555 npm start
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FAKE_ORDERBOOK_PORT` | 5556 | HTTP/WebSocket port |
| `FAKE_ORACLE_URL` | http://127.0.0.1:5555 | Fake oracle URL |
| `FAKE_ORDERBOOK_SPREAD_BPS` | 50 | Spread in basis points |
| `FAKE_ORDERBOOK_DEPTH_LEVELS` | 20 | Number of levels per side |
| `ORACLE_POLL_INTERVAL_MS` | 5000 | Oracle polling interval |
| `WS_BROADCAST_INTERVAL_MS` | 1000 | WebSocket broadcast interval |

## API Endpoints

### GET /api/v3/depth

MEXC-compatible orderbook depth.

**Query Parameters:**
- `symbol` (default: ZEPHUSDT): Trading pair
- `limit` (default: 20, max: 100): Number of levels

**Response:**
```json
{
  "lastUpdateId": 123,
  "bids": [["14.95000000", "1000.00"], ...],
  "asks": [["15.05000000", "1000.00"], ...]
}
```

### GET /status

Current service status.

**Response:**
```json
{
  "status": "running",
  "oracleUrl": "http://127.0.0.1:5555",
  "oraclePriceUsd": 15.0,
  "lastOracleUpdate": "2024-01-15T10:30:00.000Z",
  "bestBid": 14.9625,
  "bestAsk": 15.0375,
  "spread": 0.075,
  "spreadBps": 50,
  "config": { "spreadBps": 50, "depthLevels": 20 },
  "updateSequence": 123
}
```

### POST /set-spread

Adjust spread dynamically.

**Request Body:**
```json
{
  "spreadBps": 100,
  "depthLevels": 30
}
```

## WebSocket

Connect to `ws://127.0.0.1:5556/` for real-time updates.

### Subscription

Send MEXC-style subscription:
```json
{
  "method": "SUBSCRIPTION",
  "params": ["spot@public.aggre.depth.v3.api@100ms@ZEPHUSDT"],
  "id": 1
}
```

### Depth Updates

Receives depth updates every second:
```json
{
  "c": "spot@public.aggre.depth.v3.api@100ms@ZEPHUSDT",
  "d": {
    "s": "ZEPHUSDT",
    "t": 1705312200000,
    "b": [["14.95000000", "1000.00"], ...],
    "a": [["15.05000000", "1000.00"], ...]
  }
}
```

## Testing with curl

```bash
# Check status
curl http://127.0.0.1:5556/status

# Get orderbook
curl "http://127.0.0.1:5556/api/v3/depth?symbol=ZEPHUSDT&limit=5"

# Adjust spread
curl -X POST http://127.0.0.1:5556/set-spread \
  -H "Content-Type: application/json" \
  -d '{"spreadBps": 100}'
```

## Integration with Engine

The zephyr-bridge-engine uses this service when `FAKE_ORDERBOOK_ENABLED=true`:

```bash
FAKE_ORDERBOOK_ENABLED=true FAKE_ORDERBOOK_PORT=5556 pnpm dev:watchers
```

The engine's MEXC client automatically routes requests to this service instead of the real MEXC API.
