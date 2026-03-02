"""Tiered test definitions package (46 tests)."""
from ._types import TestDef
from .precheck import TESTS as _PRECHECK
from .smoke import TESTS as _SMOKE
from .integration import TESTS as _INTEGRATION
from .seed import TESTS as _SEED

ALL_TESTS: list[TestDef] = _PRECHECK + _SMOKE + _INTEGRATION + _SEED

TIER_MAP: dict[str, list[str]] = {
    "precheck": [t.test_id for t in _PRECHECK],
    "smoke": [t.test_id for t in _SMOKE],
    "integration": [t.test_id for t in _INTEGRATION],
    "seed": [t.test_id for t in _SEED],
}

TEST_BY_ID: dict[str, TestDef] = {t.test_id: t for t in ALL_TESTS}
