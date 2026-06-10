"""Chain access — Zephyr daemon/wallet RPC + Anvil/EVM, wrapping test_common.

True chain tip comes from the daemon (`get_info`), NOT the wallet (its height is stale).
EVM snapshot/revert gives cheap per-test isolation.
"""
from __future__ import annotations

from typing import Any

import test_common as _tc

# Re-export the canonical endpoints/constants so scenarios don't reach into test_common.
ATOMIC = _tc.ATOMIC
NODE1_RPC = _tc.NODE1_RPC
ANVIL_URL = _tc.ANVIL_URL
GOV_W = _tc.GOV_W
MINER_W = _tc.MINER_W
TEST_W = _tc.TEST_W
BRIDGE_W = _tc.BRIDGE_W
TK = _tc.TK
CTX = _tc.CTX
GOV_WALLET_PORT = _tc.GOV_WALLET_PORT
TEST_WALLET_PORT = _tc.TEST_WALLET_PORT
BRIDGE_WALLET_PORT = _tc.BRIDGE_WALLET_PORT


# ── Zephyr daemon ──────────────────────────────────────────────────────────
def daemon(method: str, params: Any = None) -> tuple[Any, str | None]:
    """JSON-RPC against Zephyr node1 (the source of truth for chain tip + reserves)."""
    return _tc._rpc(NODE1_RPC, method, params)


def daemon_height() -> int | None:
    info, err = daemon("get_info")
    if err or not info:
        return None
    try:
        return int(info.get("height", 0))
    except (TypeError, ValueError):
        return None


def reserve_info() -> tuple[dict | None, str | None]:
    """get_reserve_info — reserve_ratio, num_reserves, num_stables, spot/MA price report."""
    return daemon("get_reserve_info")


def reserve_ratio() -> tuple[float | None, str | None]:
    """Current spot reserve ratio as a float (e.g. 7.01 = 701%, i.e. 4.0 == 400%)."""
    return _tc._get_rr()


def reserve_ratio_ma() -> tuple[float | None, str | None]:
    """Moving-average reserve ratio (`reserve_ratio_ma`) — same units as spot. Protocol gates
    test BOTH spot and MA (see harness chain.reserve_ratio); the engine reads this into
    `reserveRatioMovingAverage` (reserve.ts)."""
    info, err = reserve_info()
    if err or not info:
        return None, err or "no reserve_info"
    raw = info.get("reserve_ratio_ma")
    try:
        return float(raw), None  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None, f"bad reserve_ratio_ma: {raw!r}"


def circulating() -> dict[str, float]:
    """Circulating supply the protocol gates care about: ZSD (`num_stables`) and ZRS
    (`num_reserves`), in whole units. Used for the MINT_RESERVE bootstrap exception
    (circulating ZSD < 100) and reserve-empty checks."""
    info, err = reserve_info()
    out: dict[str, float] = {}
    if err or not info:
        return out
    for key, label in (("num_stables", "ZSD"), ("num_reserves", "ZRS")):
        try:
            out[label] = int(info.get(key, 0)) / ATOMIC
        except (TypeError, ValueError):
            continue
    return out


# ── Zephyr wallets ───────────────────────────────────────────────────────────
def wallet(port: int, method: str, params: Any = None) -> tuple[Any, str | None]:
    url = f"http://127.0.0.1:{port}/json_rpc"
    return _tc._rpc(url, method, params)


def balances(port: int) -> dict[str, float]:
    """All-asset unlocked balances (in whole units) for a wallet. Requires all_assets:true."""
    res, err = wallet(port, "get_balance", {"account_index": 0, "all_assets": True})
    out: dict[str, float] = {}
    if err or not res:
        return out
    for b in res.get("balances", []):
        try:
            out[b["asset_type"]] = int(b.get("unlocked_balance", 0)) / ATOMIC
        except (TypeError, ValueError, KeyError):
            continue
    return out


def wallet_address(port: int) -> str | None:
    """The primary Zephyr address of a wallet — a valid unwrap payout destination."""
    res, err = wallet(port, "get_address", {"account_index": 0})
    if err or not res:
        return None
    return res.get("address")


def transfer(port: int, dest: str, amount_atomic: int, source_asset: str,
             destination_asset: str | None = None) -> tuple[Any, str | None]:
    """Wallet `transfer` — also used for native conversions (both source_asset AND
    destination_asset required; never `asset_type`)."""
    params = {
        "destinations": [{"address": dest, "amount": amount_atomic}],
        "account_index": 0,
        "source_asset": source_asset,
        "destination_asset": destination_asset or source_asset,
        "priority": 0,
    }
    return wallet(port, "transfer", params)


# ── Anvil / EVM ──────────────────────────────────────────────────────────────
def _anvil(method: str, params: list | None = None) -> tuple[Any, str | None]:
    parsed, err = _tc._jpost(
        ANVIL_URL, {"jsonrpc": "2.0", "method": method, "params": params or [], "id": 1}
    )
    if err:
        return None, err
    if not parsed:
        return None, "empty response"
    if "error" in parsed:
        return None, str(parsed["error"])
    return parsed.get("result"), None


def block_number() -> int | None:
    res, err = _anvil("eth_blockNumber")
    try:
        return int(res, 16) if res else None
    except (TypeError, ValueError):
        return None


def evm_snapshot() -> str | None:
    res, _ = _anvil("evm_snapshot")
    return res


def evm_revert(snap_id: str) -> bool:
    res, _ = _anvil("evm_revert", [snap_id])
    return res is True


def mine_evm(blocks: int = 1) -> None:
    _anvil("anvil_mine", [hex(blocks)])


def eth_call(to: str, data: str) -> tuple[str | None, str | None]:
    return _tc._eth_call(to, data)


def cast(args: list[str]) -> tuple[str | None, str | None]:
    return _tc._cast(args)
