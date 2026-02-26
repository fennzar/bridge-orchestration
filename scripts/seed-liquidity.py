#!/usr/bin/env python3
"""Seed liquidity via proper bridge wrap flow.

Replaces ad-hoc ERC-20 minting with:
  1. Fund engine Zephyr wallet from gov (ZPH, ZSD, ZRS, ZYS)
  2. Wrap assets through the bridge (deposit → watcher → claim on EVM)
  3. Mint mock USDs (USDC, USDT) to engine EVM wallet
  4. Add liquidity to Uniswap V4 pools
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Add scripts/ to path so we can import helpers
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from lib.seed_helpers import (
    ANVIL_URL,
    ATOMIC,
    BRIDGE_API_URL,
    BRIDGE_WALLET_PORT,
    ENGINE_WALLET_PORT,
    GOV_WALLET_PORT,
    _cast,
    _json_request,
    bridge_create_account,
    bridge_poll_claims,
    evm_claim,
    evm_token_balance,
    log_err,
    log_ok,
    log_step,
    mine_blocks,
    wait_daemon_ready,
    zephyr_balance,
    zephyr_rpc,
    zephyr_transfer,
)

ORCH_DIR = SCRIPT_DIR.parent

# ── Environment Loading ──────────────────────────────────────────────

def load_env():
    """Load .env from ORCH_DIR, expanding variable references."""
    env_file = ORCH_DIR / ".env"
    if not env_file.exists():
        log_err(f".env not found at {env_file}")
        sys.exit(1)

    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        # Expand ${VAR} and $VAR references against current env
        expanded = os.path.expandvars(value)
        os.environ.setdefault(key, expanded)


def require_env(name: str) -> str:
    val = os.environ.get(name, "")
    if not val:
        log_err(f"Required env var {name} is not set")
        sys.exit(1)
    return val


# ── Configuration ────────────────────────────────────────────────────

# Dynamic seeding config: read from addresses.json "seeding" section
# (written by patch-pool-prices.py from oracle USD prices).
# Falls back to legacy defaults if seeding config not present.

def _load_seeding_config() -> dict:
    """Load seeding config from addresses.json, with legacy fallback."""
    main = ORCH_DIR / "config" / "addresses.json"
    local = ORCH_DIR / "config" / "addresses.local.json"
    for p in (main, local):
        if p.exists():
            data = json.loads(p.read_text())
            seeding = data.get("seeding")
            if seeding:
                return seeding
    # Legacy fallback
    return {
        "funding": {"ZPH": 85000, "ZSD": 85000, "ZRS": 35000, "ZYS": 35000,
                     "USDT": 100000, "USDC": 100000},
        "wrapAmounts": {"ZPH": 80000, "ZSD": 80000, "ZRS": 30000, "ZYS": 30000},
    }

_SEEDING = _load_seeding_config()

SEED_WZEPH = int(os.environ.get("SEED_WZEPH", str(_SEEDING["wrapAmounts"]["ZPH"])))
SEED_WZSD = int(os.environ.get("SEED_WZSD", str(_SEEDING["wrapAmounts"]["ZSD"])))
SEED_WZRS = int(os.environ.get("SEED_WZRS", str(_SEEDING["wrapAmounts"]["ZRS"])))
SEED_WZYS = int(os.environ.get("SEED_WZYS", str(_SEEDING["wrapAmounts"]["ZYS"])))
SEED_USDC = int(os.environ.get("SEED_USDC", str(_SEEDING["funding"].get("USDC", 10000))))
SEED_USDT = int(os.environ.get("SEED_USDT", str(_SEEDING["funding"].get("USDT", 70000))))

# Extra margin sent from gov → engine beyond wrap amounts (covers tx fees)
FUNDING_MARGIN = 5000


# ── Helpers ──────────────────────────────────────────────────────────

def load_addresses() -> dict:
    """Load token contract addresses from config/addresses.json.

    Prefers whichever file is newer (addresses.json is written by deploy,
    addresses.local.json may be a stale user override).
    """
    main = ORCH_DIR / "config" / "addresses.json"
    local = ORCH_DIR / "config" / "addresses.local.json"
    candidates = [p for p in (main, local) if p.exists()]
    if not candidates:
        log_err("No addresses.json found in config/")
        sys.exit(1)
    # Use the most recently modified file
    best = max(candidates, key=lambda p: p.stat().st_mtime)
    return json.loads(best.read_text())


def run_forge(foundry_path: str, script: str, sig: str, rpc_url: str,
              private_key: str, extra_env: dict | None = None):
    """Run a forge script. Returns (success, stderr)."""
    env = os.environ.copy()
    env["RPC_URL"] = rpc_url
    env["DEPLOYER_KEY"] = private_key
    if extra_env:
        env.update(extra_env)

    cmd = [
        os.path.expanduser("~/.foundry/bin/forge"), "script", script,
        "--sig", sig,
        "--rpc-url", rpc_url,
        "--broadcast", "--private-key", private_key, "-vvv",
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=120,
        cwd=foundry_path, env=env,
    )
    if result.returncode != 0:
        return False, result.stderr
    return True, ""


# ── Main Steps ───────────────────────────────────────────────────────

def step_preflight(rpc_url: str, api_url: str):
    """Check Anvil and Bridge API are responding."""
    log_step("Preflight checks...")

    # Anvil
    stdout, err = _cast(["block-number", "--rpc-url", rpc_url])
    if err:
        log_err(f"Anvil not responding at {rpc_url}: {err}")
        sys.exit(1)
    log_ok(f"Anvil at block {stdout}")

    # Bridge API (retry for watchers startup)
    for attempt in range(6):
        try:
            from urllib.request import urlopen
            with urlopen(f"{api_url}/health", timeout=5) as r:
                if r.status == 200:
                    log_ok("Bridge API healthy")
                    return
        except Exception:
            pass
        if attempt < 5:
            time.sleep(3)

    log_err(f"Bridge API not responding at {api_url}/health")
    sys.exit(1)


def step_fund_engine():
    """Fund engine Zephyr wallet with all 4 asset types from gov.

    Sends ZPH, ZSD, ZRS, ZYS directly — no on-chain conversion needed
    because the DEVNET init already minted these on the gov wallet.
    """
    log_step("Funding engine Zephyr wallet from gov...")

    # Wait for daemon to be fully ready (bridge-watchers polling can cause
    # "daemon is busy" shortly after apps start)
    log_step("  Waiting for daemon readiness...")
    if not wait_daemon_ready(timeout=90):
        log_err("Daemon not ready after 90s")
        sys.exit(1)
    log_ok("  Daemon ready")

    # Get engine wallet address
    result, err = zephyr_rpc(ENGINE_WALLET_PORT, "get_address", {"account_index": 0})
    if err or result is None:
        log_err(f"Failed to get engine wallet address: {err}")
        sys.exit(1)
    assert result is not None
    engine_zeph_addr = result["address"]

    # Refresh gov wallet to see latest outputs
    zephyr_rpc(GOV_WALLET_PORT, "refresh")
    time.sleep(2)

    # Use dynamic funding amounts from seeding config if available,
    # otherwise fall back to wrap amount + margin
    funding = _SEEDING.get("funding", {})
    sends = [
        (int(funding.get("ZPH", SEED_WZEPH + FUNDING_MARGIN)), "ZPH"),
        (int(funding.get("ZSD", SEED_WZSD + FUNDING_MARGIN)),  "ZSD"),
        (int(funding.get("ZRS", SEED_WZRS + FUNDING_MARGIN)),  "ZRS"),
        (int(funding.get("ZYS", SEED_WZYS + FUNDING_MARGIN)),  "ZYS"),
    ]

    for amount, asset in sends:
        # Check if engine already has enough of this asset
        existing = zephyr_balance(ENGINE_WALLET_PORT, asset)
        if existing >= amount * 0.9:
            log_ok(f"  Engine already has {existing:.0f} {asset}, skipping")
            continue

        log_step(f"  Sending {amount} {asset} from gov -> engine...")
        tx_hash, err = zephyr_transfer(GOV_WALLET_PORT, engine_zeph_addr, amount, asset)
        if err:
            log_err(f"  Transfer {asset} failed: {err}")
            sys.exit(1)
        log_ok(f"  Sent {amount} {asset}: {tx_hash}")

        # Mine a few blocks between sends (different asset types use
        # independent ring sets, so we just need tx confirmation)
        mine_blocks(3)
        time.sleep(1)

    # Mine blocks for all outputs to mature on engine wallet
    log_step("  Mining 15 blocks for output maturity...")
    mine_blocks(15)

    # Refresh engine wallet to see all new balances
    zephyr_rpc(ENGINE_WALLET_PORT, "refresh")
    time.sleep(2)

    # Verify engine balances
    for asset in ["ZPH", "ZSD", "ZRS", "ZYS"]:
        bal = zephyr_balance(ENGINE_WALLET_PORT, asset)
        log_ok(f"  Engine {asset}: {bal:.2f}")


def step_create_bridge_account(api_url: str, evm_addr: str) -> str:
    """Create bridge wrap account, return Zephyr subaddress."""
    log_step("Creating bridge wrap account...")
    subaddr, err = bridge_create_account(api_url, evm_addr)
    if err or subaddr is None:
        log_err(f"Failed to create bridge account: {err}")
        sys.exit(1)
    assert isinstance(subaddr, str)
    log_ok(f"Bridge subaddress: {subaddr[:20]}...")
    return subaddr


def step_send_to_bridge(bridge_subaddr: str):
    """Send assets from engine wallet to bridge subaddress for wrapping."""
    log_step("Sending assets to bridge for wrapping...")

    # Ensure daemon is ready before transfers
    if not wait_daemon_ready(timeout=60):
        log_err("Daemon not ready for bridge transfers")
        sys.exit(1)

    zephyr_rpc(ENGINE_WALLET_PORT, "refresh")
    time.sleep(1)

    sends = [
        (SEED_WZEPH, "ZPH", "wZEPH"),
        (SEED_WZSD,  "ZSD", "wZSD"),
        (SEED_WZRS,  "ZRS", "wZRS"),
        (SEED_WZYS,  "ZYS", "wZYS"),
    ]

    for amount, asset, label in sends:
        log_step(f"  Sending {amount} {asset} -> bridge ({label})...")
        tx_hash, err = zephyr_transfer(ENGINE_WALLET_PORT, bridge_subaddr, amount, asset)
        if err:
            log_err(f"  Transfer {asset} failed: {err}")
            sys.exit(1)
        log_ok(f"  Sent {amount} {asset}: {tx_hash}")
        # Mine blocks between sends for ring availability
        mine_blocks(3)
        time.sleep(1)


def step_verify_bridge_received():
    """Verify the bridge wallet received native coin deposits."""
    log_step("Verifying bridge wallet received deposits...")

    zephyr_rpc(BRIDGE_WALLET_PORT, "refresh")
    time.sleep(2)

    all_ok = True
    for asset in ["ZPH", "ZSD", "ZRS", "ZYS"]:
        bal = zephyr_balance(BRIDGE_WALLET_PORT, asset)
        if bal > 0:
            log_ok(f"  Bridge wallet {asset}: {bal:.2f}")
        else:
            log_step(f"  Bridge wallet {asset}: 0 (may need more confirmations)")
            all_ok = False

    if not all_ok:
        log_step("  Some deposits not yet visible — watchers will pick them up")


def step_mine_for_confirmations():
    """Mine enough blocks for bridge watchers to detect and process deposits."""
    log_step("Mining blocks for bridge confirmations...")
    # Bridge requires 5 confirmations per deposit. Since deposits land in
    # different blocks (3 blocks mined between each send), mine enough extra
    # to ensure the last deposit also reaches the confirmation threshold.
    mine_blocks(15)
    time.sleep(3)


def step_refresh_and_wait_for_watcher(api_url: str, evm_addr: str):
    """Refresh bridge wallet and wait for the watcher to process all claims.

    After mine_blocks() stops, ensure the daemon is idle and the wallet
    is refreshed so the watcher's get_transfers RPC succeeds. The watcher
    computes confirmations from currentHeight - txHeight (not the wallet's
    stale `confirmations` field), so we just need the wallet to be
    reachable, not necessarily up-to-date.
    """
    log_step("Refreshing bridge wallet and waiting for watcher...")

    # Ensure daemon is idle and wallet can respond
    wait_daemon_ready(timeout=30)
    zephyr_rpc(BRIDGE_WALLET_PORT, "refresh")
    time.sleep(2)

    # Wait for the watcher to process (polls every 5s)
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            resp = _json_request(f"{api_url}/claims/{evm_addr}")
            claims = resp if isinstance(resp, list) else resp.get("claims", [])
            claimable = [c for c in claims if c.get("status") == "claimable"]
            if len(claimable) >= 4:
                log_ok(f"  Watcher caught up: {len(claimable)}/4 claimable")
                return
            by_status: dict[str, int] = {}
            for c in claims:
                s = c.get("status", "unknown")
                by_status[s] = by_status.get(s, 0) + 1
            log_step(f"  {len(claimable)}/4 claimable | {by_status}")
        except Exception:
            pass
        time.sleep(5)

    log_step("  Watcher hasn't caught up yet, proceeding to poll with timeout")


def step_poll_and_claim(api_url: str, evm_addr: str, private_key: str,
                        rpc_url: str):
    """Poll for claimable claims and claim them on EVM."""
    log_step("Polling for claimable claims...")

    # Check if engine already has wrapped tokens (idempotency)
    addrs = load_addresses()
    tokens = addrs.get("tokens", {})
    wzeph_addr = tokens.get("wZEPH", {}).get("address", "")
    if wzeph_addr:
        bal = evm_token_balance(wzeph_addr, evm_addr, rpc_url)
        if bal > 0:
            log_ok(f"Engine already has wZEPH ({bal / ATOMIC:.2f}), skipping claim step")
            return

    claims, err = bridge_poll_claims(api_url, evm_addr, 4, timeout=300)
    if err or not claims:
        log_err(f"Claim polling failed: {err or 'no claims returned'}")
        sys.exit(1)
    assert claims is not None

    log_ok(f"Got {len(claims)} claimable claims")

    # Claim each one
    for i, claim in enumerate(claims):
        token_addr = claim.get("token", "?")
        log_step(f"  Claiming {i+1}/{len(claims)}: {token_addr[:10]}...")
        _, err = evm_claim(claim, private_key, rpc_url)
        if err:
            # May already be claimed
            if "already" in err.lower() or "used" in err.lower():
                log_ok("  Already claimed, skipping")
                continue
            log_err(f"  Claim failed: {err}")
            sys.exit(1)
        log_ok("  Claimed successfully")


def step_mint_mock_usds(deployer_key: str, engine_addr: str,
                        rpc_url: str, addrs: dict):
    """Mint USDC and USDT to engine EVM wallet via deployer."""
    log_step("Minting mock USD tokens to engine EVM wallet...")

    tokens = addrs.get("tokens", {})

    for symbol, amount in [("USDC", SEED_USDC), ("USDT", SEED_USDT)]:
        token_info = tokens.get(symbol, {})
        token_addr = token_info.get("address", "")
        decimals = token_info.get("decimals", 6)
        if not token_addr:
            log_err(f"No address found for {symbol}")
            sys.exit(1)

        # Check existing balance (skip if above 1% of target — not just dust)
        bal = evm_token_balance(token_addr, engine_addr, rpc_url)
        threshold = int(amount * 0.01 * (10 ** decimals))
        if bal > threshold:
            log_ok(f"Engine already has {symbol} ({bal / 10**decimals:.2f}), skipping mint")
            continue

        atomic_amount = str(amount * (10 ** decimals))
        log_step(f"  Minting {amount} {symbol} to {engine_addr}...")
        _, err = _cast([
            "send", token_addr,
            "mint(address,uint256)",
            engine_addr, atomic_amount,
            "--private-key", deployer_key,
            "--rpc-url", rpc_url,
        ])
        if err:
            log_err(f"  Mint {symbol} failed: {err}")
            sys.exit(1)
        log_ok(f"  Minted {amount} {symbol}")


def step_verify_evm_balances(engine_addr: str, rpc_url: str, addrs: dict):
    """Verify engine has wrapped tokens on EVM before adding liquidity."""
    log_step("Verifying EVM token balances...")
    tokens = addrs.get("tokens", {})
    all_ok = True
    for symbol, expected in [("wZEPH", SEED_WZEPH), ("wZSD", SEED_WZSD),
                              ("wZRS", SEED_WZRS), ("wZYS", SEED_WZYS)]:
        token_info = tokens.get(symbol, {})
        token_addr = token_info.get("address", "")
        if not token_addr:
            continue
        bal = evm_token_balance(token_addr, engine_addr, rpc_url)
        bal_human = bal / ATOMIC
        if bal_human < expected * 0.5:
            log_err(f"  {symbol}: {bal_human:.2f} (expected ~{expected}, insufficient)")
            all_ok = False
        else:
            log_ok(f"  {symbol}: {bal_human:.2f}")
    if not all_ok:
        log_err("Insufficient wrapped token balances — claims may have failed")
        log_err("Check bridge-watchers logs and retry with: make seed-engine")
        sys.exit(1)


def step_add_liquidity(foundry_path: str, engine_pk: str, rpc_url: str,
                       addrs: dict, engine_addr: str):
    """Add liquidity to all Uniswap V4 pools from engine wallet."""
    log_step("Adding liquidity to pools...")

    # Idempotency: check if engine already has LP position NFTs
    posm_addr = addrs.get("contracts", {}).get("positionManager", "")
    if posm_addr:
        stdout, err = _cast([
            "call", posm_addr, "balanceOf(address)(uint256)",
            engine_addr, "--rpc-url", rpc_url,
        ])
        if not err and stdout:
            nft_count = int(stdout.strip().split()[0])
            if nft_count > 0:
                log_ok(f"Engine already has {nft_count} LP positions, skipping liquidity")
                return

    tokens = addrs.get("tokens", {})
    markets = ["USDT-USDC", "wZSD-USDT", "wZYS-wZSD", "wZEPH-wZSD", "wZRS-wZEPH"]

    for market in markets:
        # Pre-check: verify engine has both tokens for this market
        token0_sym, token1_sym = market.split("-")
        skip = False
        for sym in (token0_sym, token1_sym):
            token_info = tokens.get(sym, {})
            token_addr = token_info.get("address", "")
            if token_addr:
                bal = evm_token_balance(token_addr, engine_addr, rpc_url)
                if bal == 0:
                    log_err(f"  {market}: engine has 0 {sym} — skipping pool")
                    skip = True
                    break
        if skip:
            continue

        log_step(f"  Adding liquidity: {market}...")

        env = os.environ.copy()
        env["MARKET"] = market
        env["DEPLOYER_KEY"] = engine_pk

        cmd = [
            os.path.expanduser("~/.foundry/bin/forge"), "script",
            "script/uniswap/02_AddLiquidityFromJson.s.sol:AddLiquidityFromJson",
            "--sig", "run()",
            "--rpc-url", rpc_url,
            "--broadcast", "--private-key", engine_pk, "-vvv",
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                cwd=foundry_path, env=env,
            )
            if result.returncode != 0:
                log_err(f"  Liquidity {market} failed: {result.stderr[-500:]}")
                sys.exit(1)
            log_ok(f"  Liquidity added: {market}")
        except subprocess.TimeoutExpired:
            log_err(f"  Liquidity {market} timed out")
            sys.exit(1)


def step_scan_pools(api_url: str):
    """Trigger bridge-api pool scan so bridge-web discovers pools."""
    log_step("Scanning pools via bridge API...")
    admin_token = os.environ.get("ADMIN_TOKEN", "")
    if not admin_token:
        log_err("ADMIN_TOKEN not set, skipping pool scan")
        return

    from urllib.request import Request as _Req, urlopen as _urlopen
    import json as _json

    for attempt in range(3):
        try:
            req = _Req(
                f"{api_url}/admin/uniswap/v4/scan",
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "x-admin-token": admin_token,
                },
                data=b"{}",
            )
            with _urlopen(req, timeout=30) as r:
                resp = _json.loads(r.read())
                pools = resp.get("pools", [])
                log_ok(f"Pool scan complete: {len(pools)} pools discovered")
                return
        except Exception as e:
            if attempt < 2:
                log_step(f"  Scan attempt {attempt + 1} failed ({e}), retrying...")
                time.sleep(5)
            else:
                log_err(f"Pool scan failed after 3 attempts: {e}")


def step_save_snapshot(rpc_url: str, snapshot_dir: str):
    """Save Anvil state snapshot."""
    log_step("Saving Anvil snapshot...")
    os.makedirs(snapshot_dir, exist_ok=True)
    snapshot_file = os.path.join(snapshot_dir, "post-seed.hex")
    stdout, err = _cast(["rpc", "anvil_dumpState", "--rpc-url", rpc_url])
    if err or stdout is None:
        log_err(f"Snapshot failed: {err}")
        return
    assert stdout is not None
    Path(snapshot_file).write_text(stdout)
    log_ok(f"Snapshot saved: {snapshot_file}")


# ── Main ─────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Seed liquidity via bridge wrap flow")
    parser.add_argument("--fund-only", action="store_true",
                        help="Only fund engine Zephyr wallet (gov -> engine), then exit")
    args = parser.parse_args()

    print("===========================================")
    if args.fund_only:
        print("  Fund Engine Wallet (--fund-only)")
    else:
        print("  Seed Liquidity (Bridge Wrap Flow)")
    print("===========================================")
    print()

    # Load environment
    load_env()

    # Re-read configurable amounts after env is loaded (env overrides seeding config)
    global SEED_WZEPH, SEED_WZSD, SEED_WZRS, SEED_WZYS, SEED_USDC, SEED_USDT, _SEEDING
    _SEEDING = _load_seeding_config()
    SEED_WZEPH = int(os.environ.get("SEED_WZEPH", str(_SEEDING["wrapAmounts"]["ZPH"])))
    SEED_WZSD = int(os.environ.get("SEED_WZSD", str(_SEEDING["wrapAmounts"]["ZSD"])))
    SEED_WZRS = int(os.environ.get("SEED_WZRS", str(_SEEDING["wrapAmounts"]["ZRS"])))
    SEED_WZYS = int(os.environ.get("SEED_WZYS", str(_SEEDING["wrapAmounts"]["ZYS"])))
    SEED_USDC = int(os.environ.get("SEED_USDC", str(_SEEDING["funding"].get("USDC", 10000))))
    SEED_USDT = int(os.environ.get("SEED_USDT", str(_SEEDING["funding"].get("USDT", 70000))))

    # Required env vars
    engine_addr = require_env("ENGINE_ADDRESS")
    engine_pk = require_env("ENGINE_PK")
    deployer_key = require_env("DEPLOYER_PRIVATE_KEY")
    foundry_path = require_env("FOUNDRY_REPO_PATH")
    rpc_url = os.environ.get("EVM_RPC_HTTP", ANVIL_URL)
    snapshot_dir = os.environ.get("ANVIL_SNAPSHOT_DIR",
                                  str(ORCH_DIR / "snapshots" / "anvil"))
    api_url = os.environ.get("BRIDGE_API_URL", BRIDGE_API_URL)

    print(f"Engine EVM:  {engine_addr}")
    print(f"RPC:         {rpc_url}")
    print(f"Bridge API:  {api_url}")
    print(f"Amounts:     wZEPH={SEED_WZEPH} wZSD={SEED_WZSD} wZRS={SEED_WZRS} wZYS={SEED_WZYS}")
    print(f"             USDC={SEED_USDC} USDT={SEED_USDT}")
    print()

    try:
        if args.fund_only:
            # --fund-only: just fund engine wallet and exit
            step_fund_engine()
            print()
            print("===========================================")
            log_ok("Engine wallet funded (--fund-only)")
            print("===========================================")
            print()
            return

        # 1. Preflight
        step_preflight(rpc_url, api_url)

        # 2. Load addresses
        addrs = load_addresses()

        # 3. Check if already seeded (EVM wrapped tokens present)
        tokens = addrs.get("tokens", {})
        wzeph_addr = tokens.get("wZEPH", {}).get("address", "")
        has_wrapped = False
        if wzeph_addr:
            bal = evm_token_balance(wzeph_addr, engine_addr, rpc_url)
            if bal > 0:
                log_ok(f"Engine already has wZEPH ({bal / ATOMIC:.2f}), skipping wrap flow")
                has_wrapped = True

        if not has_wrapped:
            # 4. Check for existing claimable claims (partial run recovery)
            from urllib.request import urlopen as _urlopen
            existing_claims = []
            try:
                import urllib.request
                req = urllib.request.Request(f"{api_url}/claims/{engine_addr}")
                with _urlopen(req, timeout=10) as r:
                    import json as _json
                    resp = _json.loads(r.read())
                    claim_list = resp if isinstance(resp, list) else resp.get("claims", [])
                    existing_claims = [c for c in claim_list if c.get("status") == "claimable"]
            except Exception:
                pass

            if existing_claims:
                # Claims exist from a previous run — skip funding/sending, go straight to claiming
                log_ok(f"Found {len(existing_claims)} existing claimable claims, resuming from claim step")
                mine_blocks(5)  # ensure confirmations
            else:
                # Full wrap flow needed
                # 5. Fund engine Zephyr wallet (all 4 assets from gov)
                step_fund_engine()

                # 6. Create bridge account
                bridge_subaddr = step_create_bridge_account(api_url, engine_addr)

                # 7. Send assets to bridge for wrapping
                step_send_to_bridge(bridge_subaddr)

                # 8. Verify bridge wallet received native deposits
                step_verify_bridge_received()

                # 9. Mine for bridge watcher confirmations
                step_mine_for_confirmations()

            # 9.5. Refresh bridge wallet and wait for watcher to process.
            # The wallet's get_transfers returns stale confirmation counts when
            # the daemon is busy mining. We must: stop mining → refresh wallet
            # → give the watcher time to poll with fresh data BEFORE starting
            # any further mining.
            step_refresh_and_wait_for_watcher(api_url, engine_addr)

            # 10. Poll claims + claim wrapped tokens on EVM
            step_poll_and_claim(api_url, engine_addr, engine_pk, rpc_url)

        # 11. Verify EVM balances before liquidity
        step_verify_evm_balances(engine_addr, rpc_url, addrs)

        # 12. Mint mock USDs to engine EVM wallet
        step_mint_mock_usds(deployer_key, engine_addr, rpc_url, addrs)

        # 13. Add liquidity to Uniswap V4 pools
        step_add_liquidity(foundry_path, engine_pk, rpc_url, addrs, engine_addr)

        # 14. Scan pools so bridge-web discovers them
        step_scan_pools(api_url)

        # 15. Save Anvil snapshot
        step_save_snapshot(rpc_url, snapshot_dir)

    except KeyboardInterrupt:
        log_err("Interrupted")
        sys.exit(1)
    except SystemExit:
        raise
    except Exception as e:
        log_err(f"Unexpected error: {e}")
        sys.exit(1)

    print()
    print("===========================================")
    log_ok("Liquidity seeding complete")
    print("===========================================")
    print()


if __name__ == "__main__":
    main()
