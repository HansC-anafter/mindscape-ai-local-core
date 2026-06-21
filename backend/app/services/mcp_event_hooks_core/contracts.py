"""Contracts shared by the MCP event hook seams."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, List, Optional


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ReceiptDecision:
    """Structured result from receipt validation."""

    step: str
    should_run: bool
    reason: str
    receipt_trace_id: Optional[str] = None
    receipt_output_hash: Optional[str] = None


@dataclass
class HookResults:
    """Aggregated results from all hooks in a chat_sync cycle."""

    intent_tags: Optional[List[Any]] = None
    layout_plan: Optional[Any] = None
    triggered_hooks: List[str] = field(default_factory=list)
    skipped_hooks: List[str] = field(default_factory=list)
    events_emitted: List[str] = field(default_factory=list)
    receipt_decisions: List[ReceiptDecision] = field(default_factory=list)
