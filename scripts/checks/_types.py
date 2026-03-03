"""Shared types for the tiered test framework."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from test_common import ExecutionResult


@dataclass(frozen=True)
class TestDef:
    test_id: str
    title: str
    level: str          # grouping within a tier (e.g. "infra", "smoke", "bridge", "seed")
    tier: str            # "precheck", "infra", "ops", "bridge", "e2e"
    lane: str
    check: Callable[[dict[str, bool]], ExecutionResult]
    depends_on: tuple[str, ...] = ()  # test IDs that must PASS first


def _r(test_id: str, level: str, lane: str, result: str, detail: str, priority: str = "P0") -> ExecutionResult:
    return ExecutionResult(test_id=test_id, result=result, detail=detail, level=level, lane=lane, priority=priority)
