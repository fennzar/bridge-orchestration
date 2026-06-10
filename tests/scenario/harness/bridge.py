"""Bridge money-path drivers — wrap (deposit→claim→mint) and unwrap (prepare→burn→payout).

Fully programmatic (no browser): wrap = create bridge address, send native ZEPH/ZSD/ZRS/ZYS,
mine to confirmations, poll /claims, then claimWithSignature on the token. Unwrap =
/unwraps/prepare, then burnWithData on the token, then the watcher relays the native payout.
"""
from __future__ import annotations

import time
import uuid

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


def post_raw(path: str, body: dict, headers: dict | None = None) -> tuple[int | None, str | None, str | None]:
    """Raw POST against an arbitrary bridge-API path → (http_status, body, err).

    For probing whether a route EXISTS (e.g. a voucher re-sign endpoint) in lifecycle/adversarial
    scenarios — a 404/405 means the capability is absent."""
    return _tc._post(f"{API}{path}", body, headers=headers, timeout=10.0)


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


def prepare_and_burn(token: str, amount_wei: int, destination: str,
                     pk: str) -> tuple[dict | None, str | None]:
    """Drive the EVM side of an unwrap: /unwraps/prepare → burnWithData(amount, payload, nonce).

    The caller must already hold `amount_wei` of `token` (mint via pool.mint_wtoken on devnet).
    Returns ({prepare, nonce, burnBlock}, None) — `burnBlock` is the EVM head right after the burn,
    so a finality scenario can measure how many confirmations deep the burn was when relayed.
    """
    # /unwraps/prepare pre-signs a Zephyr payout via the bridge wallet, which can return a transient
    # 5xx while the wallet is busy (e.g. right after a prior unwrap's relay — the daemon-busy
    # gotcha). Retry a few times before giving up so chained unwrap scenarios run, not skip.
    body, st, perr = None, None, None
    for attempt in range(4):
        body, st, perr = prepare_unwrap(token, amount_wei, destination)
        if st == 200 and (body or {}).get("payload"):
            break
        if st is not None and st < 500:
            break  # a real client-side rejection (4xx) — don't retry
        time.sleep(3)
    payload = (body or {}).get("payload")
    if st != 200 or not payload:
        return None, f"prepare failed (http {st}): {perr or (body or {}).get('error')}"
    nonce = "0x" + uuid.uuid4().hex + uuid.uuid4().hex
    _, berr = burn_on_evm(token, amount_wei, payload, nonce, pk)
    if berr:
        return None, f"burn failed: {berr}"
    return {"prepare": body, "nonce": nonce, "burnBlock": chain.block_number()}, None


def wait_for_unwrap(evm_addr: str, *, since_ids: set[str] | None = None,
                    until=None, timeout: float = 90.0, poll: float = 2.0) -> dict | None:
    """Poll /unwraps/{evm_addr} for a NEW record (id not in `since_ids`) satisfying `until`.

    `until(record) -> bool` defaults to "exists". Capture `since_ids` BEFORE the burn so a prior
    unwrap on the same address isn't mistaken for this one. Returns the record or None on timeout.
    """
    since = since_ids or set()
    deadline = time.time() + timeout
    while time.time() < deadline:
        for u in unwraps_for(evm_addr):
            if u.get("id") in since:
                continue
            if until is None or until(u):
                return u
        time.sleep(poll)
    return None
