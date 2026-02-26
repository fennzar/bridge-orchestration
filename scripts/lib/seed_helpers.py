"""Reusable helpers for bridge liquidity seeding and tests.

Wraps lower-level HTTP/RPC primitives from test_common with
seed-specific workflows. Stdlib-only (no third-party deps).
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from urllib.request import Request, urlopen

# ── Constants ─────────────────────────────────────────────────────────

ATOMIC = 1_000_000_000_000  # 1e12

NODE1_RPC = "http://127.0.0.1:47767"
NODE2_RPC = "http://127.0.0.1:47867"
GOV_WALLET_PORT = 48769
ENGINE_WALLET_PORT = 48771
BRIDGE_WALLET_PORT = 48770
MINER_WALLET_PORT = 48767
BRIDGE_API_URL = "http://127.0.0.1:7051"
ANVIL_URL = "http://127.0.0.1:8545"

# ── Logging ───────────────────────────────────────────────────────────

_BLUE = "\033[0;34m"
_GREEN = "\033[0;32m"
_RED = "\033[0;31m"
_NC = "\033[0m"

if not sys.stdout.isatty():
    _BLUE = _GREEN = _RED = _NC = ""


def log_step(msg: str) -> None:
    print(f"{_BLUE}[STEP]{_NC} {msg}", flush=True)


def log_ok(msg: str) -> None:
    print(f"{_GREEN}[OK]{_NC}   {msg}", flush=True)


def log_err(msg: str) -> None:
    print(f"{_RED}[ERR]{_NC}  {msg}", flush=True)


# ── HTTP / RPC ────────────────────────────────────────────────────────

def _json_request(url: str, payload: dict | None = None,
                  method: str = "GET", timeout: float = 15.0):
    """Send an HTTP request, return parsed JSON or raise."""
    hdrs = {"Content-Type": "application/json"}
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(url, method=method if data is None else "POST",
                  headers=hdrs, data=data)
    with urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def zephyr_rpc(port: int, method: str, params: dict | None = None):
    """Zephyr wallet JSON-RPC call. Returns (result, error)."""
    url = f"http://127.0.0.1:{port}/json_rpc"
    payload: dict = {"jsonrpc": "2.0", "id": "0", "method": method}
    if params:
        payload["params"] = params
    try:
        resp = _json_request(url, payload)
        if "error" in resp:
            return None, str(resp["error"])
        return resp.get("result"), None
    except Exception as e:
        return None, str(e)


def daemon_rpc(method: str, params: dict | None = None, node_url: str = NODE1_RPC):
    """Zephyr daemon JSON-RPC call. Returns (result, error)."""
    url = f"{node_url}/json_rpc"
    payload: dict = {"jsonrpc": "2.0", "id": "0", "method": method}
    if params:
        payload["params"] = params
    try:
        resp = _json_request(url, payload)
        if "error" in resp:
            return None, str(resp["error"])
        return resp.get("result"), None
    except Exception as e:
        return None, str(e)


def wait_daemon_ready(timeout: float = 120.0) -> bool:
    """Wait until the Zephyr daemon is not busy syncing and wallets can respond.

    Stops any active mining first (mining causes persistent "daemon is busy"),
    then polls daemon get_info for busy_syncing=false and verifies a wallet
    RPC actually succeeds.
    """
    # Stop mining if active — mining causes constant "daemon is busy" for wallets
    try:
        req = Request(f"{NODE1_RPC}/stop_mining",
                      headers={"Content-Type": "application/json"},
                      data=b"{}")
        urlopen(req, timeout=5)
    except Exception:
        pass

    deadline = time.time() + timeout
    while time.time() < deadline:
        # Check daemon sync status
        info, err = daemon_rpc("get_info")
        if err:
            time.sleep(3)
            continue
        if info and info.get("busy_syncing", False):
            time.sleep(3)
            continue
        # Daemon says it's not syncing — verify wallet can actually respond
        result, err = zephyr_rpc(GOV_WALLET_PORT, "get_balance",
                                  {"account_index": 0})
        if err and "daemon is busy" in str(err):
            time.sleep(3)
            continue
        if result is not None:
            return True
        time.sleep(3)
    return False


def zephyr_balance(port: int, asset: str) -> float:
    """Get wallet balance for specific asset type, returns float."""
    result, err = zephyr_rpc(port, "refresh")
    if err:
        return 0.0
    time.sleep(0.5)
    result, err = zephyr_rpc(port, "get_balance",
                              {"account_index": 0, "all_assets": True})
    if err or result is None:
        return 0.0
    assert result is not None  # narrowed above
    # Response uses balances array: [{asset_type, balance, ...}, ...]
    for entry in result.get("balances", []):
        if entry.get("asset_type") == asset:
            return int(entry.get("balance", 0)) / ATOMIC
    return 0.0


def zephyr_transfer(src_port: int, dest_addr: str, amount: float, asset: str):
    """Send assets from wallet to destination address. Returns (tx_hash, error).

    Retries on 'daemon is busy' errors (common after mining restart).
    """
    atomic_amount = int(amount * ATOMIC)
    params = {
        "destinations": [{"amount": atomic_amount, "address": dest_addr}],
        "source_asset": asset,
        "destination_asset": asset,
        "priority": 0,
        "ring_size": 2,
        "get_tx_key": True,
    }
    max_retries = 12
    for attempt in range(max_retries):
        result, err = zephyr_rpc(src_port, "transfer", params)
        if err and "daemon is busy" in str(err):
            if attempt < max_retries - 1:
                log_step(f"    Daemon busy, retry {attempt + 1}/{max_retries}...")
                time.sleep(5)
                continue
        if err or result is None:
            return None, err or "No response"
        assert result is not None  # narrowed above
        return result.get("tx_hash"), None
    return None, "daemon is busy (exhausted retries)"


def zephyr_convert(port: int, amount: float, from_asset: str, to_asset: str):
    """Convert assets (e.g., ZPH->ZSD). Sends to self. Returns (tx_hash, error)."""
    # Get own address
    addr_result, err = zephyr_rpc(port, "get_address", {"account_index": 0})
    if err or addr_result is None:
        return None, f"get_address failed: {err}"
    assert addr_result is not None  # narrowed above
    own_addr = addr_result["address"]

    atomic_amount = int(amount * ATOMIC)
    params = {
        "destinations": [{"amount": atomic_amount, "address": own_addr}],
        "source_asset": from_asset,
        "destination_asset": to_asset,
        "priority": 0,
        "ring_size": 2,
        "get_tx_key": True,
    }
    result, err = zephyr_rpc(port, "transfer", params)
    if err or result is None:
        return None, err or "No response"
    assert result is not None  # narrowed above
    return result.get("tx_hash"), None


# ── Bridge API ────────────────────────────────────────────────────────

def bridge_create_account(api_url: str, evm_addr: str):
    """POST to bridge API to create wrap account. Returns (zephyr_subaddress, error)."""
    try:
        resp = _json_request(
            f"{api_url}/bridge/address",
            {"evmAddress": evm_addr},
        )
        return resp.get("zephyrAddress") or resp.get("zephyrSubaddress") or resp.get("address"), None
    except Exception as e:
        return None, str(e)


def bridge_poll_claims(api_url: str, evm_addr: str,
                       expected_count: int, timeout: float = 120.0):
    """Poll claims endpoint until expected_count claims reach 'claimable' status.

    Caller should ensure mining is running (start_continuous_mining) so
    the bridge watcher can advance confirmation counts.
    """
    deadline = time.time() + timeout
    poll_count = 0
    while time.time() < deadline:
        try:
            resp = _json_request(f"{api_url}/claims/{evm_addr}")
            claims = resp if isinstance(resp, list) else resp.get("claims", [])
            claimable = [c for c in claims if c.get("status") == "claimable"]
            if len(claimable) >= expected_count:
                return claimable, None
            # Detailed status every 6th poll (~30s)
            poll_count += 1
            if poll_count % 6 == 1:
                by_status: dict[str, int] = {}
                for c in claims:
                    s = c.get("status", "unknown")
                    by_status[s] = by_status.get(s, 0) + 1
                log_step(f"  Claims: {len(claims)} total, {len(claimable)}/{expected_count} claimable | {by_status}")
            else:
                log_step(f"  Claims: {len(claimable)}/{expected_count} claimable, waiting...")
        except Exception:
            pass
        time.sleep(5)
    # Final diagnostic on timeout
    try:
        resp = _json_request(f"{api_url}/claims/{evm_addr}")
        claims = resp if isinstance(resp, list) else resp.get("claims", [])
        log_err(f"  Timeout detail: {len(claims)} claims total")
        for c in claims:
            conf = c.get("zephConfirmations", {})
            log_err(f"    status={c.get('status')} token={str(c.get('token',''))[:12]} conf={conf}")
    except Exception:
        pass
    return None, f"Timeout after {timeout}s waiting for {expected_count} claimable claims"


# ── EVM Helpers ───────────────────────────────────────────────────────

def _cast(args: list[str], timeout: float = 30.0):
    """Run foundry `cast` CLI. Returns (stdout, error)."""
    try:
        result = subprocess.run(
            ["cast"] + args,
            capture_output=True, text=True, timeout=timeout,
        )
        if result.returncode != 0:
            return None, result.stderr.strip() or f"exit code {result.returncode}"
        return result.stdout.strip(), None
    except FileNotFoundError:
        return None, "cast not found (install foundry)"
    except subprocess.TimeoutExpired:
        return None, f"cast timed out after {timeout}s"
    except Exception as e:
        return None, str(e)


def evm_claim(claim_data: dict, private_key: str, rpc_url: str):
    """Call claimWithSignature on the token contract. Returns (tx_hash, error).

    Accepts the bridge API claim format:
      token, to, amountWei, zephTxId, deadline, signature
    """
    token_addr = claim_data["token"]
    to = claim_data["to"]
    amount = str(claim_data["amountWei"])
    # zephTxId needs 0x prefix for bytes32
    zeph_tx_id = claim_data["zephTxId"]
    zephyr_tx_hash = zeph_tx_id if zeph_tx_id.startswith("0x") else f"0x{zeph_tx_id}"
    deadline = str(claim_data["deadline"])
    signature = claim_data["signature"]

    stdout, err = _cast([
        "send", token_addr,
        "claimWithSignature(address,uint256,bytes32,uint256,bytes)",
        to, amount, zephyr_tx_hash, deadline, signature,
        "--private-key", private_key,
        "--rpc-url", rpc_url,
    ])
    if err:
        return None, err
    return stdout, None


def evm_token_balance(token_addr: str, account: str, rpc_url: str) -> int:
    """ERC-20 balanceOf via cast call. Returns balance in wei."""
    stdout, err = _cast([
        "call", token_addr,
        "balanceOf(address)(uint256)",
        account,
        "--rpc-url", rpc_url,
    ])
    if err or stdout is None:
        return 0
    assert stdout is not None  # narrowed above
    try:
        return int(stdout.strip().split()[0])
    except (ValueError, IndexError):
        return 0


# ── Mining Helpers ────────────────────────────────────────────────────

def mine_blocks(count: int = 5):
    """Trigger mining via daemon RPC (start_mining, wait, stop_mining)."""
    # Get miner address
    result, err = zephyr_rpc(MINER_WALLET_PORT, "get_address", {"account_index": 0})
    if err or result is None:
        log_err(f"Failed to get miner address: {err}")
        return
    assert result is not None  # narrowed above

    miner_addr = result["address"]

    # Get current height
    info, _ = daemon_rpc("get_info")
    start_height = int(info.get("height", 0)) if info else 0

    # Start mining
    try:
        hdrs = {"Content-Type": "application/json"}
        data = json.dumps({
            "do_background_mining": False,
            "ignore_battery": True,
            "miner_address": miner_addr,
            "threads_count": 2,
        }).encode()
        req = Request(f"{NODE1_RPC}/start_mining", headers=hdrs, data=data)
        urlopen(req, timeout=10)
    except Exception as e:
        log_err(f"start_mining failed: {e}")
        return

    # Wait for blocks
    target = start_height + count
    deadline = time.time() + 120
    while time.time() < deadline:
        info, _ = daemon_rpc("get_info")
        if info and int(info.get("height", 0)) >= target:
            break
        time.sleep(1)

    # Stop mining
    try:
        req = Request(f"{NODE1_RPC}/stop_mining",
                      headers={"Content-Type": "application/json"},
                      data=b"{}")
        urlopen(req, timeout=10)
    except Exception:
        pass


def start_continuous_mining():
    """Start mining without stopping — for use during bridge watcher polling."""
    result, err = zephyr_rpc(MINER_WALLET_PORT, "get_address", {"account_index": 0})
    if err or result is None:
        return
    assert result is not None
    try:
        hdrs = {"Content-Type": "application/json"}
        data = json.dumps({
            "do_background_mining": False,
            "ignore_battery": True,
            "miner_address": result["address"],
            "threads_count": 2,
        }).encode()
        req = Request(f"{NODE1_RPC}/start_mining", headers=hdrs, data=data)
        urlopen(req, timeout=10)
    except Exception:
        pass


def stop_continuous_mining():
    """Stop mining."""
    try:
        req = Request(f"{NODE1_RPC}/stop_mining",
                      headers={"Content-Type": "application/json"},
                      data=b"{}")
        urlopen(req, timeout=10)
    except Exception:
        pass


def wait_blocks(target_height: int, timeout: float = 60.0):
    """Poll daemon get_info until height reaches target."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        info, _ = daemon_rpc("get_info")
        if info and int(info.get("height", 0)) >= target_height:
            return True
        time.sleep(1)
    return False
