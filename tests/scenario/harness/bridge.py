"""Bridge money-path drivers — wrap (deposit→claim→mint) and unwrap (prepare→burn→payout).

Fully programmatic (no browser): wrap = create bridge address, send native ZEPH/ZSD/ZRS/ZYS,
mine to confirmations, poll /claims, then claimWithSignature on the token. Unwrap =
/unwraps/prepare, then burnWithData on the token, then the watcher relays the native payout.
"""
from __future__ import annotations

import time

import test_common as _tc

from harness import chain

API = _tc.BRIDGE_API_URL


# ── wrap side ────────────────────────────────────────────────────────────────
def tokens() -> list[dict]:
    parsed, err = _tc._jget(f"{API}/bridge/tokens", timeout=10.0)
    if err or not parsed:
        return []
    return parsed.get("tokens", [])


def create_address(evm_addr: str) -> tuple[str | None, str | None]:
    """POST /bridge/address → the Zephyr (sub)address to deposit into. Returns (addr, err)."""
    parsed, err = _tc._jpost(f"{API}/bridge/address", {"evmAddress": evm_addr}, timeout=15.0)
    if err or not parsed:
        return None, err or "empty response"
    return parsed.get("zephyrAddress"), None


def claims_for(evm_addr: str, status: str | None = None) -> list[dict]:
    url = f"{API}/claims/{evm_addr}"
    if status:
        url += f"?status={status}"
    parsed, err = _tc._jget(url, timeout=10.0)
    if err or parsed is None:
        return []
    return parsed if isinstance(parsed, list) else parsed.get("claims", [])


def wait_for_claim(evm_addr: str, *, zeph_txid: str | None = None, status: str = "claimable",
                   timeout: float = 120.0, poll: float = 3.0) -> dict | None:
    """Poll /claims until a claim (optionally matching zeph_txid) reaches `status`."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        for c in claims_for(evm_addr):
            if zeph_txid and c.get("zephTxId", "").replace("0x", "") != zeph_txid.replace("0x", ""):
                continue
            if c.get("status") == status:
                return c
        time.sleep(poll)
    return None


def claim_on_evm(token: str, claim: dict, pk: str) -> tuple[str | None, str | None]:
    """claimWithSignature(address to,uint256 amount,bytes32 zephyrTxHash,uint256 deadline,bytes sig)."""
    tx = claim.get("zephTxId", "")
    if not tx.startswith("0x"):
        tx = "0x" + tx
    return chain.cast([
        "send", token,
        "claimWithSignature(address,uint256,bytes32,uint256,bytes)",
        claim["to"], str(claim["amountWei"]), tx, str(claim["deadline"]), claim["signature"],
        "--private-key", pk, "--rpc-url", chain.ANVIL_URL,
    ])


# ── unwrap side ──────────────────────────────────────────────────────────────
def prepare_unwrap(token: str, amount_wei: int, destination: str,
                   headers: dict | None = None) -> tuple[dict | None, int | None, str | None]:
    """POST /unwraps/prepare. Returns (body, http_status, err). Status is captured so
    adversarial scenarios can assert a 4xx rejection."""
    status, body, err = _tc._post(
        f"{API}/unwraps/prepare",
        {"token": token, "amountWei": str(amount_wei), "destination": destination},
        headers=headers, timeout=20.0,
    )
    parsed = None
    if body:
        try:
            import json
            parsed = json.loads(body)
        except Exception:
            parsed = None
    return parsed, status, err


def burn_on_evm(token: str, amount_wei: int, payload_hex: str, nonce_hex: str,
                pk: str) -> tuple[str | None, str | None]:
    """burnWithData(uint256 amount, bytes zephDestination, bytes32 nonce)."""
    return chain.cast([
        "send", token,
        "burnWithData(uint256,bytes,bytes32)",
        str(amount_wei), payload_hex, nonce_hex,
        "--private-key", pk, "--rpc-url", chain.ANVIL_URL,
    ])


def unwraps_for(evm_addr: str) -> list[dict]:
    parsed, err = _tc._jget(f"{API}/unwraps/{evm_addr}", timeout=10.0)
    if err or parsed is None:
        return []
    return parsed if isinstance(parsed, list) else parsed.get("unwraps", [])
