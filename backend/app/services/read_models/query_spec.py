"""Runtime query request and page objects for read models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ReadModelQuerySpec:
    read_model_id: str
    filters: dict[str, Any]
    sort_id: str
    limit: int
    cursor: str | None = None
    include_counts: bool = True


@dataclass(frozen=True)
class ReadModelPage:
    items: list[dict[str, Any]]
    next_cursor: str | None
    counts: dict[str, Any] = field(default_factory=dict)
    count_version: int | None = None
