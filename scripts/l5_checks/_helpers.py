"""L5-specific helpers -- imports shared infra from test_common."""
from __future__ import annotations

import json
import socket
import threading
import time as _time
from urllib.request import Request, urlopen

from test_common import (
    PASS, FAIL, BLOCKED,
    L5Result,
    API, ENGINE, WEB, ANVIL, ZNODE, ORACLE, OBOOK,
    GOV_W, TEST_W, MINER_W,
    TK, CTX, ANVIL_URL, NODE2_RPC,
    _get, _post, _jget, _jpost, _rpc, _eth_call, _eth_code, _get_rr,
    _cast,
    set_oracle_price, CleanupContext,
)

# EVM function selectors
SEL_DECIMALS = "0x313ce567"
SEL_TOTAL_SUPPLY = "0x18160ddd"
SEL_HAS_ROLE = "0x91d14854"
SEL_OWNER = "0x8da5cb5b"
SEL_DOMAIN_SEP = "0x3644e515"
SEL_EIP712_DOMAIN = "0x84b0196e"
MINTER_ROLE = "9f2df0fed2c77648de5860a4cc508cd0818c85b8b8a1ab4ceeef8d981c8956a6"
FAKE_EVM = "0x0000000000000000000000000000000000dead01"
FAKE_EVM_2 = "0x0000000000000000000000000000000000dead02"


def _r(row, result: str, detail: str) -> L5Result:
    return L5Result(row.test_id, result, detail, row.lane, row.status, row.priority)


def _needs(row, probes, *keys):
    missing = [k for k in keys if not probes.get(k)]
    if missing:
        return _r(row, BLOCKED, f"Missing: {', '.join(missing)}")
    return None


def _decimals(addr):
    r, e = _eth_call(addr, SEL_DECIMALS)
    if e:
        return None, e
    try:
        return int(r, 16), None
    except (ValueError, TypeError):
        return None, f"Bad decimals: {r}"


def _total_supply(addr):
    r, e = _eth_call(addr, SEL_TOTAL_SUPPLY)
    if e:
        return None, e
    try:
        return int(r, 16), None
    except (ValueError, TypeError):
        return None, f"Bad totalSupply: {r}"


def _has_role(contract, role_hex, account):
    role_pad = role_hex.replace("0x", "").zfill(64)
    acct_pad = account.lower().replace("0x", "").zfill(64)
    r, e = _eth_call(contract, SEL_HAS_ROLE + role_pad + acct_pad)
    if e:
        return None, e
    try:
        return int(r, 16) == 1, None
    except (ValueError, TypeError):
        return None, f"Bad hasRole: {r}"


def _contract_exists(addr):
    code, err = _eth_code(addr)
    if err:
        return None, err
    return code is not None and code != "0x" and len(code) > 2, None
