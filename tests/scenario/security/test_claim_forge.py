"""SEC-CLAIM-FORGE — a forged claim voucher reverts on-chain (live cross-check of the EIP-712 gate).

The unit/forge tests prove `claimWithSignature` rejects a bad signature; this is the live
counterpart — submit a fabricated claim (garbage signature) to the deployed wZEPH contract and
assert the transaction REVERTS, so no tokens mint without a real bridge-signer voucher. INV-8/9
(voucher unforgeable & bound). Expected GREEN.

Needs a funded EVM key to pay gas for the (reverting) send — skip if ENGINE_PK is absent. The tx
reverts, so it makes no state change; no reset needed.
"""
from __future__ import annotations

import pytest

from harness import bridge, pool

pytestmark = [pytest.mark.needs_stack, pytest.mark.inv("INV-8")]

FAKE_TXID = "0x" + "ab" * 32
FAR_DEADLINE = 4_102_444_800  # year 2100
GARBAGE_SIG = "0x" + "11" * 65


def test_sec_claim_forge_reverts():
    pk, addr = pool.pusher()
    if not pk or not addr:
        pytest.skip("ENGINE_PK/ENGINE_ADDRESS unavailable — can't pay gas for the forge attempt")
    token = pool.token_address("wZEPH")
    if not token:
        pytest.skip("wZEPH token address not in config")

    forged = {
        "to": addr,
        "amountWei": str(10**18),
        "zephTxId": FAKE_TXID,
        "deadline": str(FAR_DEADLINE),
        "signature": GARBAGE_SIG,
    }
    txhash, err = bridge.claim_on_evm(token, forged, pk)
    assert err is not None and not txhash, (
        f"forged claim did NOT revert (txhash={txhash}) — a fabricated voucher minted tokens! "
        "INV-8/9 broken"
    )
