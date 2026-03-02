"""Tiered test definitions package.

Tier structure:
  T1  precheck   — Environment readiness (no infra needed)
  T2  infra      — Infrastructure health (post dev-init)
  T3  ops        — Basic operations (post dev-init, mutating)
  T4A bridge     — Bridge health + flows (post dev-setup)
  T4B engine     — Engine strategy tests (external runner)
  T5  e2e        — Full system tests (placeholder)
"""
from ._types import TestDef
from .prereqs import TESTS as _PRECHECK
from .precheck import TESTS as _INFRA
from .ops import TESTS as _OPS
from .bridge_health import TESTS as _BRIDGE_HEALTH
from .bridge_flows import TESTS as _BRIDGE_FLOWS
from .e2e import TESTS as _E2E

ALL_TESTS: list[TestDef] = _PRECHECK + _INFRA + _OPS + _BRIDGE_HEALTH + _BRIDGE_FLOWS + _E2E

TIER_MAP: dict[str, list[str]] = {
    "precheck": [t.test_id for t in _PRECHECK],
    "infra": [t.test_id for t in _INFRA],
    "ops": [t.test_id for t in _OPS],
    "bridge": [t.test_id for t in _BRIDGE_HEALTH + _BRIDGE_FLOWS],
    "e2e": [t.test_id for t in _E2E],
}

TEST_BY_ID: dict[str, TestDef] = {t.test_id: t for t in ALL_TESTS}
