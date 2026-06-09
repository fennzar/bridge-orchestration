"""OPS-* — stack/protocol sanity gates. All GREEN: if any reds, the deeper scenarios are
untrustworthy, so these double as a self-test of the harness (chain/control/engine/pool) against a
live `make dev` stack. They mutate nothing irreversibly (oracle restored via clean_market).
"""
from __future__ import annotations

import pytest

from harness import chain, control, engine, pool

pytestmark = [pytest.mark.needs_stack]

TOKENS = ("wZEPH", "wZSD", "wZRS", "wZYS")


def test_ops_chain_health():
    """Daemon and Anvil are both live and advancing."""
    h = chain.daemon_height()
    assert h and h > 0, f"daemon height not positive: {h}"
    bn = chain.block_number()
    assert bn and bn > 0, f"anvil block number not positive: {bn}"


def test_ops_contracts_deployed():
    """The four wrapped tokens + the SwapRouter have bytecode at their configured addresses."""
    for sym in TOKENS:
        addr = pool.token_address(sym)
        assert addr, f"{sym} address missing from config"
        code, err = chain.cast(["code", addr, "--rpc-url", chain.ANVIL_URL])
        assert not err and code and len(code) > 2, f"{sym} ({addr}) has no bytecode: {err or code}"


def test_ops_oracle_control(clean_market):
    """Setting the fake oracle price takes effect (the master knob the MKT suite depends on)."""
    assert control.set_price(1.50), "set_oracle_price returned False"
    spot = control.oracle_spot_usd()
    assert spot is not None and abs(spot - 1.50) < 0.05, f"oracle spot {spot} != ~1.50"


def test_ops_rr_compute_agrees():
    """Daemon reserve ratio is sane and the engine reports it consistently (×100 percent)."""
    rr, err = chain.reserve_ratio()
    assert not err and rr and rr > 0, f"daemon RR not positive: {rr} ({err})"
    ev, eerr = engine.evaluate()
    assert not eerr and ev, f"engine evaluate errored: {eerr}"
    reported = engine.reserve_ratio(ev)
    assert reported is not None, "engine reported no reserveRatio"
    assert reported == pytest.approx(rr * 100, rel=0.05), (
        f"engine RR {reported}% disagrees with daemon {rr * 100:.1f}%"
    )


def test_ops_wallet_balances():
    """The gov wallet holds ZPH (it funds seeding + conversions in the scenarios)."""
    bals = chain.balances(chain.GOV_WALLET_PORT)
    assert bals, "gov wallet returned no balances (all_assets probe failed)"
    zph = bals.get("ZPH", 0.0)
    assert zph > 0, f"gov wallet holds no ZPH: {bals}"
