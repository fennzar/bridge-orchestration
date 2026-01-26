"""Shared types for L1-L4 test modules."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from test_common import ExecutionResult


@dataclass(frozen=True)
class TestDef:
    test_id: str
    title: str
    level: str  # "L1".."L4"
    lane: str
    check: Callable[[dict[str, bool]], ExecutionResult]


def _r(test_id: str, level: str, lane: str, result: str, detail: str, priority: str = "P0") -> ExecutionResult:
    return ExecutionResult(test_id=test_id, result=result, detail=detail, level=level, lane=lane, priority=priority)
