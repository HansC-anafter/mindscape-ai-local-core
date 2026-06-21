"""Memory edge and writeback run contract models."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from .memory_contract_types import (
    MemoryEdgeType,
    MemoryWritebackRunStatus,
    _utc_now,
)


@dataclass
class MemoryEdge:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    from_memory_id: str = ""
    to_memory_id: str = ""
    edge_type: str = MemoryEdgeType.SUPPORTS.value
    weight: Optional[float] = None
    valid_from: datetime = field(default_factory=_utc_now)
    valid_to: Optional[datetime] = None
    evidence_strength: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)

    @staticmethod
    def supersedes(
        from_memory_id: str,
        to_memory_id: str,
        *,
        reason: str = "",
        run_id: Optional[str] = None,
    ) -> "MemoryEdge":
        metadata: Dict[str, Any] = {}
        if reason:
            metadata["reason"] = reason
        if run_id:
            metadata["source_writeback_run_id"] = run_id
        return MemoryEdge(
            from_memory_id=from_memory_id,
            to_memory_id=to_memory_id,
            edge_type=MemoryEdgeType.SUPERSEDES.value,
            evidence_strength=1.0,
            metadata=metadata,
        )


@dataclass
class MemoryWritebackRun:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    run_type: str = ""
    source_scope: str = ""
    source_id: str = ""
    status: str = MemoryWritebackRunStatus.RUNNING.value
    idempotency_key: str = ""
    update_mode_summary: Dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=_utc_now)
    completed_at: Optional[datetime] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    error_detail: Optional[str] = None
    last_stage: str = "created"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    @staticmethod
    def new(
        *,
        run_type: str,
        source_scope: str,
        source_id: str,
        idempotency_key: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "MemoryWritebackRun":
        now = _utc_now()
        return MemoryWritebackRun(
            run_type=run_type,
            source_scope=source_scope,
            source_id=source_id,
            status=MemoryWritebackRunStatus.RUNNING.value,
            idempotency_key=idempotency_key,
            metadata=dict(metadata or {}),
            created_at=now,
            started_at=now,
            updated_at=now,
        )
