"""L1-L4 test definitions package (32 tests)."""
from ._types import TestDef
from .l1_infra import TESTS as _L1
from .l2_smoke import TESTS as _L2
from .l3_component import TESTS as _L3
from .l4_e2e import TESTS as _L4

ALL_TESTS: list[TestDef] = _L1 + _L2 + _L3 + _L4

L1_IDS = [t.test_id for t in ALL_TESTS if t.level == "L1"]
L2_IDS = [t.test_id for t in ALL_TESTS if t.level == "L2"]
L3_IDS = [t.test_id for t in ALL_TESTS if t.level == "L3"]
L4_IDS = [t.test_id for t in ALL_TESTS if t.level == "L4"]

TEST_BY_ID: dict[str, TestDef] = {t.test_id: t for t in ALL_TESTS}
