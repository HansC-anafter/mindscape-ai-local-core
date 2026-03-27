"""
Canonical memory contract models.

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

from backend.app.models.personal_governance.session_digest import SessionDigest
from backend.app.models.lens_patch import LensPatch
from backend.app.models.meeting_decision import MeetingDecision
from backend.app.models.mindscape import IntentLog
from backend.app.models.reasoning_trace import ReasoningTrace
from backend.app.models.personal_governance.writeback_receipt import WritebackReceipt
from backend.app.models.lens_receipt import LensReceipt
from backend.app.models.workspace import Artifact
from backend.app.models.workspace import Task


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryLayer(str, Enum):
    PROCESS = "process"
    EPISODIC = "episodic"
    INTERFACE = "interface"
    CORE = "core"
    PROCEDURAL = "procedural"


class MemoryKind(str, Enum):
    SESSION_EPISODE = "session_episode"
    DECISION_EPISODE = "decision_episode"
    PATTERN_CANDIDATE = "pattern_candidate"
    CONTEXT_SIGNATURE = "context_signature"
    PREFERENCE = "preference"
    PRINCIPLE = "principle"
    PROCEDURAL_RULE = "procedural_rule"


class MemoryVerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    OBSERVED = "observed"
    VERIFIED = "verified"
    CHALLENGED = "challenged"
    REJECTED = "rejected"


class MemoryLifecycleStatus(str, Enum):
    CANDIDATE = "candidate"
    ACTIVE = "active"
    STALE = "stale"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"


class MemoryUpdateMode(str, Enum):
    APPEND = "append"
    REVISE = "revise"
    SUPERSEDE = "supersede"
    INVALIDATE = "invalidate"
    MERGE = "merge"


class MemoryEdgeType(str, Enum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    CONTINUES = "continues"
    SUPERSEDES = "supersedes"


class MemoryWritebackRunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class MemoryItem:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kind: str = MemoryKind.SESSION_EPISODE.value
    layer: str = MemoryLayer.EPISODIC.value
    scope: str = "global"
    subject_type: str = ""
    subject_id: str = ""
    context_type: str = ""
    context_id: str = ""
    title: str = ""
    claim: str = ""
    summary: str = ""
    salience: float = 0.5
    confidence: float = 0.5
    verification_status: str = MemoryVerificationStatus.OBSERVED.value
    lifecycle_status: str = MemoryLifecycleStatus.CANDIDATE.value
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    observed_at: datetime = field(default_factory=_utc_now)
    last_confirmed_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    update_mode: Optional[str] = MemoryUpdateMode.APPEND.value
    supersedes_memory_id: Optional[str] = None
    created_by_pipeline: str = ""
    created_from_run_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)

    @staticmethod
    def from_session_digest(
        digest: SessionDigest,
        *,
        run_id: str,
        pipeline_name: str = "meeting_close_writeback_v1",
    ) -> "MemoryItem":
        summary = _shorten(digest.summary_md.strip(), 600)
        if not summary:
            summary = _build_meeting_fallback_summary(digest)

        title = f"Meeting episode {digest.source_id}".strip()
        claim = _shorten(digest.summary_md.strip(), 2000) or summary

        action_count = len(digest.actions or [])
        decision_count = len(digest.decisions or [])
        signal_weight = min(1.0, 0.35 + (action_count * 0.05) + (decision_count * 0.08))

        return MemoryItem(
            kind=MemoryKind.SESSION_EPISODE.value,
            layer=MemoryLayer.EPISODIC.value,
            scope="meeting",
            subject_type="meeting_session",
            subject_id=digest.source_id,
            context_type="workspace",
            context_id=(digest.workspace_refs[0] if digest.workspace_refs else ""),
            title=title,
            claim=claim,
            summary=summary,
            salience=signal_weight,
            confidence=0.85,
            verification_status=MemoryVerificationStatus.OBSERVED.value,
            lifecycle_status=MemoryLifecycleStatus.CANDIDATE.value,
            valid_from=digest.source_time_end or digest.created_at,
            observed_at=digest.source_time_end or digest.created_at,
            update_mode=MemoryUpdateMode.APPEND.value,
            created_by_pipeline=pipeline_name,
            created_from_run_id=run_id,
            metadata={
                "source_type": digest.source_type,
                "source_id": digest.source_id,
                "workspace_refs": list(digest.workspace_refs or []),
                "project_refs": list(digest.project_refs or []),
                "participant_count": len(digest.participants or []),
                "action_count": action_count,
                "decision_count": decision_count,
                "digest_id": digest.id,
            },
        )


@dataclass
class MemoryVersion:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    memory_item_id: str = ""
    version_no: int = 1
    update_mode: str = MemoryUpdateMode.APPEND.value
    claim_snapshot: str = ""
    summary_snapshot: Optional[str] = None
    metadata_snapshot: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=_utc_now)
    created_from_run_id: Optional[str] = None

    @staticmethod
    def initial_from_item(item: MemoryItem) -> "MemoryVersion":
        return MemoryVersion(
            memory_item_id=item.id,
            version_no=1,
            update_mode=item.update_mode or MemoryUpdateMode.APPEND.value,
            claim_snapshot=item.claim,
            summary_snapshot=item.summary,
            metadata_snapshot=dict(item.metadata or {}),
            created_from_run_id=item.created_from_run_id,
        )


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


def _shorten(value: str, limit: int) -> str:
    if not value:
        return ""
    value = " ".join(value.split())
    return value[:limit]


def _build_meeting_fallback_summary(digest: SessionDigest) -> str:
    action_count = len(digest.actions or [])
    decision_count = len(digest.decisions or [])
    return (
        f"Closed meeting {digest.source_id} with "
        f"{action_count} action items and {decision_count} decisions."
    )


def _build_reasoning_trace_excerpt(trace: ReasoningTrace) -> str:
    graph = trace.graph
    if graph.answer:
        return _shorten(graph.answer.strip(), 280)

    for preferred_type in ("conclusion", "inference", "evidence", "premise", "risk"):
        for node in graph.nodes:
            if node.type == preferred_type and node.content.strip():
                return _shorten(node.content.strip(), 280)

    return _shorten(f"Reasoning trace {trace.id}", 280)


def _build_writeback_receipt_excerpt(receipt: WritebackReceipt) -> str:
    summary = (
        f"{receipt.target_table} {receipt.writeback_type} "
        f"status={receipt.status} target={receipt.target_id}"
    )
    return _shorten(summary.strip(), 280)


def _build_lens_receipt_excerpt(receipt: LensReceipt) -> str:
    if receipt.diff_summary:
        return _shorten(receipt.diff_summary.strip(), 280)
    if receipt.lens_output:
        return _shorten(receipt.lens_output.strip(), 280)
    if receipt.base_output:
        return _shorten(receipt.base_output.strip(), 280)
    return _shorten(f"Lens receipt {receipt.id}", 280)


def _build_lens_patch_excerpt(patch: LensPatch) -> str:
    status = patch.status.value if hasattr(patch.status, "value") else str(patch.status)
    delta_keys = list((patch.delta or {}).keys())
    if delta_keys:
        preview = ", ".join(delta_keys[:3])
        if len(delta_keys) > 3:
            preview = f"{preview}, +{len(delta_keys) - 3} more"
        return _shorten(
            f"Lens patch {status}. Changed {preview}. Confidence {patch.confidence:.2f}.",
            280,
        )
    return _shorten(
        f"Lens patch {status}. Confidence {patch.confidence:.2f}.",
        280,
    )


def _build_task_execution_excerpt(task: Task) -> str:
    if isinstance(task.result, dict):
        for key in ("summary", "message", "result_summary", "title"):
            value = task.result.get(key)
            if isinstance(value, str) and value.strip():
                return _shorten(value.strip(), 280)
    if task.error:
        return _shorten(task.error.strip(), 280)
    summary = f"{task.pack_id} {task.task_type} status={task.status}"
    return _shorten(summary.strip(), 280)


def _build_execution_trace_excerpt(
    trace_payload: Dict[str, Any],
    *,
    task: Optional[Task] = None,
) -> str:
    output_summary = trace_payload.get("output_summary")
    if isinstance(output_summary, str) and output_summary.strip():
        return _shorten(output_summary.strip(), 280)

    task_description = trace_payload.get("task_description")
    if isinstance(task_description, str) and task_description.strip():
        return _shorten(task_description.strip(), 280)

    agent = trace_payload.get("agent") or trace_payload.get("agent_type")
    if not isinstance(agent, str) or not agent.strip():
        agent = "runtime"
    tool_calls = trace_payload.get("tool_calls")
    files_created = trace_payload.get("files_created")
    files_modified = trace_payload.get("files_modified")
    tool_call_count = len(tool_calls) if isinstance(tool_calls, list) else 0
    file_change_count = 0
    if isinstance(files_created, list):
        file_change_count += len(files_created)
    if isinstance(files_modified, list):
        file_change_count += len(files_modified)
    task_label = ""
    if task is not None:
        task_label = f"{task.pack_id} {task.task_type}".strip()
    summary_parts = [f"{agent} trace"]
    if task_label:
        summary_parts.append(f"for {task_label}")
    summary_parts.append(f"with {tool_call_count} tool calls")
    summary_parts.append(f"and {file_change_count} file changes.")
    return _shorten(" ".join(summary_parts), 280)


def _build_artifact_excerpt(artifact: Artifact) -> str:
    if artifact.summary:
        return _shorten(artifact.summary.strip(), 280)
    if artifact.title:
        return _shorten(artifact.title.strip(), 280)
    summary = f"{artifact.playbook_code} {artifact.artifact_type}"
    return _shorten(summary.strip(), 280)


def _build_stage_result_excerpt(stage_result: Any) -> str:
    preview = getattr(stage_result, "preview", None)
    if isinstance(preview, str) and preview.strip():
        return _shorten(preview.strip(), 280)

    content = getattr(stage_result, "content", None)
    if isinstance(content, dict):
        for key in ("summary", "message", "title", "result_summary"):
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                return _shorten(value.strip(), 280)

    stage_name = getattr(stage_result, "stage_name", "stage")
    result_type = getattr(stage_result, "result_type", "result")
    return _shorten(f"{stage_name} {result_type}", 280)


def _build_intent_log_excerpt(intent_log: IntentLog) -> str:
    final_decision = intent_log.final_decision or {}
    selected_playbook_code = final_decision.get("selected_playbook_code")
    resolution_strategy = final_decision.get("resolution_strategy")
    requires_user_approval = final_decision.get("requires_user_approval")

    summary_parts = []
    if isinstance(selected_playbook_code, str) and selected_playbook_code.strip():
        summary_parts.append(f"Selected {selected_playbook_code.strip()}.")
    if isinstance(resolution_strategy, str) and resolution_strategy.strip():
        summary_parts.append(f"Resolution {resolution_strategy.strip()}.")
    if requires_user_approval is True:
        summary_parts.append("User approval required.")
    if intent_log.user_override:
        summary_parts.append("User override recorded.")
    if summary_parts:
        return _shorten(" ".join(summary_parts), 280)

    raw_input = intent_log.raw_input.strip()
    if raw_input:
        return _shorten(raw_input, 280)
    return _shorten(f"Intent log {intent_log.id}", 280)


def _build_governance_decision_excerpt(decision: Dict[str, Any]) -> str:
    layer = str(decision.get("layer") or "governance").strip()
    approved = decision.get("approved")
    reason = decision.get("reason")
    playbook_code = decision.get("playbook_code")

    summary_parts = [f"{layer.title()} approval={approved}."]
    if isinstance(playbook_code, str) and playbook_code.strip():
        summary_parts.append(f"Playbook {playbook_code.strip()}.")
    if isinstance(reason, str) and reason.strip():
        summary_parts.append(reason.strip())
    return _shorten(" ".join(summary_parts), 280)
