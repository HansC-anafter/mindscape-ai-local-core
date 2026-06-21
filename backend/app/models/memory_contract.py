"""
Canonical memory contract public facade.

These dataclasses back the first governed-memory rollout slice:
`memory_items`, `memory_versions`, `memory_evidence_links`,
and `memory_writeback_runs`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

from .lens_patch import LensPatch
from .lens_receipt import LensReceipt
from .meeting_decision import MeetingDecision
from .memory_contract_edges import MemoryEdge, MemoryWritebackRun
from .memory_contract_evidence import MemoryEvidenceLink
from .memory_contract_excerpts import (
    _build_artifact_excerpt,
    _build_execution_trace_excerpt,
    _build_governance_decision_excerpt,
    _build_intent_log_excerpt,
    _build_lens_patch_excerpt,
    _build_lens_receipt_excerpt,
    _build_reasoning_trace_excerpt,
    _build_stage_result_excerpt,
    _build_task_execution_excerpt,
    _build_writeback_receipt_excerpt,
    _shorten,
)
from .memory_contract_items import (
    MemoryItem,
    MemoryVersion,
    _build_meeting_fallback_summary,
)
from .memory_contract_types import (
    MemoryEdgeType,
    MemoryKind,
    MemoryLayer,
    MemoryLifecycleStatus,
    MemoryUpdateMode,
    MemoryVerificationStatus,
    MemoryWritebackRunStatus,
    _utc_now,
)
from .mindscape import IntentLog
from .personal_governance.session_digest import SessionDigest
from .personal_governance.writeback_receipt import WritebackReceipt
from .reasoning_trace import ReasoningTrace
from .workspace import Artifact, Task
