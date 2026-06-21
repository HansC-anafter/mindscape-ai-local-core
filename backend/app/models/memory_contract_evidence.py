"""Memory evidence link contract model."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

from .lens_patch import LensPatch
from .lens_receipt import LensReceipt
from .meeting_decision import MeetingDecision
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
from .memory_contract_types import _utc_now
from .mindscape import IntentLog
from .personal_governance.session_digest import SessionDigest
from .personal_governance.writeback_receipt import WritebackReceipt
from .reasoning_trace import ReasoningTrace
from .workspace import Artifact, Task


@dataclass
class MemoryEvidenceLink:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    memory_item_id: str = ""
    evidence_type: str = ""
    evidence_id: str = ""
    link_role: str = "supports"
    excerpt: Optional[str] = None
    confidence: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)

    @staticmethod
    def from_session_digest(
        memory_item_id: str,
        digest: SessionDigest,
    ) -> "MemoryEvidenceLink":
        return MemoryEvidenceLink(
            memory_item_id=memory_item_id,
            evidence_type="session_digest",
            evidence_id=digest.id,
            link_role="derived_from",
            excerpt=_shorten(digest.summary_md.strip(), 280),
            confidence=0.9,
            metadata={
                "source_type": digest.source_type,
                "source_id": digest.source_id,
            },
        )

    @staticmethod
    def from_reasoning_trace(
        memory_item_id: str,
        trace: ReasoningTrace,
    ) -> "MemoryEvidenceLink":
        return MemoryEvidenceLink(
            memory_item_id=memory_item_id,
            evidence_type="reasoning_trace",
            evidence_id=trace.id,
            link_role="supports",
            excerpt=_build_reasoning_trace_excerpt(trace),
            confidence=0.78,
            metadata={
                "meeting_session_id": trace.meeting_session_id,
                "execution_id": trace.execution_id,
                "assistant_event_id": trace.assistant_event_id,
                "schema_version": trace.schema_version,
                "sgr_mode": trace.sgr_mode,
                "model": trace.model,
                "node_count": len(trace.graph.nodes),
                "edge_count": len(trace.graph.edges),
            },
        )

    @staticmethod
    def from_meeting_decision(
        memory_item_id: str,
        decision: MeetingDecision,
    ) -> "MemoryEvidenceLink":
        return MemoryEvidenceLink(
            memory_item_id=memory_item_id,
            evidence_type="meeting_decision",
            evidence_id=decision.id,
            link_role="supports",
            excerpt=_shorten(decision.content.strip(), 280),
            confidence=0.82,
            metadata={
                "meeting_session_id": decision.session_id,
                "workspace_id": decision.workspace_id,
                "category": decision.category,
                "status": decision.status,
                "resolved_by_task_id": decision.resolved_by_task_id,
            },
        )

    @staticmethod
    def from_writeback_receipt(
        memory_item_id: str,
        receipt: WritebackReceipt,
    ) -> "MemoryEvidenceLink":
        return MemoryEvidenceLink(
            memory_item_id=memory_item_id,
            evidence_type="writeback_receipt",
            evidence_id=receipt.id,
            link_role="derived_from",
            excerpt=_build_writeback_receipt_excerpt(receipt),
            confidence=0.86 if receipt.status == "completed" else 0.72,
            metadata={
                "meta_session_id": receipt.meta_session_id,
                "source_decision_id": receipt.source_decision_id,
                "target_table": receipt.target_table,
                "target_id": receipt.target_id,
                "writeback_type": receipt.writeback_type,
                "status": receipt.status,
            },
        )

    @staticmethod
    def from_lens_receipt(
        memory_item_id: str,
        receipt: LensReceipt,
    ) -> "MemoryEvidenceLink":
        return MemoryEvidenceLink(
            memory_item_id=memory_item_id,
            evidence_type="lens_receipt",
            evidence_id=receipt.id,
            link_role="supports",
            excerpt=_build_lens_receipt_excerpt(receipt),
            confidence=0.8,
            metadata={
                "execution_id": receipt.execution_id,
                "workspace_id": receipt.workspace_id,
                "effective_lens_hash": receipt.effective_lens_hash,
                "triggered_node_count": len(receipt.triggered_nodes),
            },
        )

    @staticmethod
    def from_lens_patch(
        memory_item_id: str,
        patch: LensPatch,
    ) -> "MemoryEvidenceLink":
        return MemoryEvidenceLink(
            memory_item_id=memory_item_id,
            evidence_type="lens_patch",
            evidence_id=patch.id,
            link_role="supports",
            excerpt=_build_lens_patch_excerpt(patch),
            confidence=patch.confidence or 0.75,
            metadata={
                "lens_id": patch.lens_id,
                "meeting_session_id": patch.meeting_session_id,
                "status": (
                    patch.status.value
                    if hasattr(patch.status, "value")
                    else str(patch.status)
                ),
                "lens_version_before": patch.lens_version_before,
                "lens_version_after": patch.lens_version_after,
                "delta_magnitude": patch.delta_magnitude,
                "evidence_ref_count": len(patch.evidence_refs or []),
            },
        )

    @staticmethod
    def from_task_execution(
        memory_item_id: str,
        task: Task,
    ) -> "MemoryEvidenceLink":
        return MemoryEvidenceLink(
            memory_item_id=memory_item_id,
            evidence_type="task_execution",
            evidence_id=task.execution_id or task.id,
            link_role="supports",
            excerpt=_build_task_execution_excerpt(task),
            confidence=0.79 if str(task.status) == "succeeded" else 0.68,
            metadata={
                "task_id": task.id,
                "execution_id": task.execution_id,
                "status": str(task.status),
                "pack_id": task.pack_id,
                "task_type": task.task_type,
                "completed_at": task.completed_at.isoformat()
                if task.completed_at
                else None,
            },
        )

    @staticmethod
    def from_execution_trace(
        memory_item_id: str,
        trace_payload: Dict[str, Any],
        *,
        task: Optional[Task] = None,
    ) -> "MemoryEvidenceLink":
        tool_calls = trace_payload.get("tool_calls")
        files_created = trace_payload.get("files_created")
        files_modified = trace_payload.get("files_modified")
        return MemoryEvidenceLink(
            memory_item_id=memory_item_id,
            evidence_type="execution_trace",
            evidence_id=str(
                trace_payload.get("execution_id")
                or trace_payload.get("trace_id")
                or (task.execution_id if task else None)
                or (task.id if task else "")
            ),
            link_role="supports",
            excerpt=_build_execution_trace_excerpt(trace_payload, task=task),
            confidence=0.77,
            metadata={
                "task_id": task.id if task else None,
                "execution_id": trace_payload.get("execution_id")
                or (task.execution_id if task else None),
                "trace_id": trace_payload.get("trace_id"),
                "agent": trace_payload.get("agent") or trace_payload.get("agent_type"),
                "tool_call_count": len(tool_calls) if isinstance(tool_calls, list) else 0,
                "files_created_count": len(files_created)
                if isinstance(files_created, list)
                else 0,
                "files_modified_count": len(files_modified)
                if isinstance(files_modified, list)
                else 0,
                "file_change_count": len(trace_payload.get("file_changes"))
                if isinstance(trace_payload.get("file_changes"), list)
                else 0,
                "sandbox_path": trace_payload.get("sandbox_path"),
                "pack_id": task.pack_id if task else None,
                "task_type": task.task_type if task else None,
                "task_description": trace_payload.get("task_description"),
                "output_summary": trace_payload.get("output_summary"),
                "success": trace_payload.get("success"),
                "duration_seconds": trace_payload.get("duration_seconds"),
                "trace_source": trace_payload.get("trace_source"),
                "trace_file_path": trace_payload.get("trace_file_path"),
            },
        )

    @staticmethod
    def from_artifact_result(
        memory_item_id: str,
        artifact: Artifact,
    ) -> "MemoryEvidenceLink":
        artifact_metadata = artifact.metadata or {}
        landing_metadata = (
            artifact_metadata.get("landing")
            if isinstance(artifact_metadata.get("landing"), dict)
            else {}
        )
        return MemoryEvidenceLink(
            memory_item_id=memory_item_id,
            evidence_type="artifact_result",
            evidence_id=artifact.id,
            link_role="supports",
            excerpt=_build_artifact_excerpt(artifact),
            confidence=0.83,
            metadata={
                "artifact_id": artifact.id,
                "execution_id": artifact.execution_id,
                "artifact_type": str(artifact.artifact_type),
                "playbook_code": artifact.playbook_code,
                "storage_ref": artifact.storage_ref,
                "sync_state": artifact.sync_state,
                "landing_artifact_dir": landing_metadata.get("artifact_dir"),
                "landing_result_json_path": landing_metadata.get("result_json_path"),
                "landing_summary_md_path": landing_metadata.get("summary_md_path"),
                "landing_attachments_count": landing_metadata.get(
                    "attachments_count"
                ),
                "landing_attachments": landing_metadata.get("attachments") or [],
                "landing_landed_at": landing_metadata.get("landed_at"),
            },
        )

    @staticmethod
    def from_stage_result(
        memory_item_id: str,
        stage_result: Any,
    ) -> "MemoryEvidenceLink":
        return MemoryEvidenceLink(
            memory_item_id=memory_item_id,
            evidence_type="stage_result",
            evidence_id=stage_result.id,
            link_role="supports",
            excerpt=_build_stage_result_excerpt(stage_result),
            confidence=0.76,
            metadata={
                "execution_id": getattr(stage_result, "execution_id", None),
                "step_id": getattr(stage_result, "step_id", None),
                "stage_name": getattr(stage_result, "stage_name", None),
                "result_type": getattr(stage_result, "result_type", None),
                "requires_review": getattr(stage_result, "requires_review", None),
                "review_status": getattr(stage_result, "review_status", None),
                "artifact_id": getattr(stage_result, "artifact_id", None),
            },
        )

    @staticmethod
    def from_intent_log(
        memory_item_id: str,
        intent_log: IntentLog,
    ) -> "MemoryEvidenceLink":
        final_decision = intent_log.final_decision or {}
        return MemoryEvidenceLink(
            memory_item_id=memory_item_id,
            evidence_type="intent_log",
            evidence_id=intent_log.id,
            link_role="supports",
            excerpt=_build_intent_log_excerpt(intent_log),
            confidence=0.74,
            metadata={
                "workspace_id": intent_log.workspace_id,
                "project_id": intent_log.project_id,
                "channel": intent_log.channel,
                "selected_playbook_code": final_decision.get("selected_playbook_code"),
                "resolution_strategy": final_decision.get("resolution_strategy"),
                "requires_user_approval": final_decision.get(
                    "requires_user_approval"
                ),
                "has_user_override": bool(intent_log.user_override),
            },
        )

    @staticmethod
    def from_governance_decision(
        memory_item_id: str,
        decision: Dict[str, Any],
    ) -> "MemoryEvidenceLink":
        return MemoryEvidenceLink(
            memory_item_id=memory_item_id,
            evidence_type="governance_decision",
            evidence_id=str(decision.get("decision_id", "")),
            link_role="supports",
            excerpt=_build_governance_decision_excerpt(decision),
            confidence=0.81,
            metadata={
                "execution_id": decision.get("execution_id"),
                "layer": decision.get("layer"),
                "approved": decision.get("approved"),
                "reason": decision.get("reason"),
                "playbook_code": decision.get("playbook_code"),
            },
        )
