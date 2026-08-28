"""Lightweight, secret-safe timing and SQL query profiling helpers."""

from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
import re
from time import perf_counter
from typing import Callable, Iterator


Output = Callable[[str], None]


def timing_line(*, stage: str, duration_s: float, source: str = "", **values) -> str:
    """Return one stable machine-readable timing line without payload data."""
    parts = ["[TIMING]"]
    if source:
        parts.append(f"source={source}")
    parts.extend((f"stage={stage}", f"duration_s={duration_s:.3f}"))
    parts.extend(f"{key}={value}" for key, value in values.items())
    return " ".join(parts)


@contextmanager
def timed_stage(output: Output, stage: str, *, source: str = "", **values) -> Iterator[None]:
    """Measure a stage and emit its duration even when the stage fails."""
    started = perf_counter()
    try:
        yield
    finally:
        output(timing_line(
            stage=stage, source=source, duration_s=perf_counter() - started,
            **values,
        ))


def _query_pattern(sql: str) -> str:
    normalized = re.sub(r"\s+", " ", sql.strip()).casefold()
    normalized = re.sub(r"\b\d+\b", "?", normalized)
    return normalized[:180]


@dataclass
class QueryProfile:
    count: int = 0
    duration_s: float = 0.0
    slowest_s: float = 0.0
    patterns: Counter = field(default_factory=Counter)

    @property
    def repeated_patterns(self) -> int:
        return sum(1 for count in self.patterns.values() if count > 1)


_ACTIVE_QUERY_PROFILE: ContextVar[QueryProfile | None] = ContextVar(
    "product_picker_query_profile", default=None,
)


def record_query(sql: str, duration_s: float) -> None:
    """Record query metadata only; SQL parameters and secrets are never logged."""
    profile = _ACTIVE_QUERY_PROFILE.get()
    if profile is None:
        return
    profile.count += 1
    profile.duration_s += duration_s
    profile.slowest_s = max(profile.slowest_s, duration_s)
    profile.patterns[_query_pattern(sql)] += 1


@contextmanager
def query_profile(output: Output, stage: str, *, source: str = "") -> Iterator[QueryProfile]:
    """Profile queries executed by instrumented database adapters in one stage."""
    profile = QueryProfile()
    token = _ACTIVE_QUERY_PROFILE.set(profile)
    started = perf_counter()
    try:
        yield profile
    finally:
        _ACTIVE_QUERY_PROFILE.reset(token)
        output(timing_line(
            stage=stage, source=source, duration_s=perf_counter() - started,
            query_count=profile.count,
            query_duration_s=f"{profile.duration_s:.3f}",
            slowest_query_s=f"{profile.slowest_s:.3f}",
            repeated_patterns=profile.repeated_patterns,
        ))
