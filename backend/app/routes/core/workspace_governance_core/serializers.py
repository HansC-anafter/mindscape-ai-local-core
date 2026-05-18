from pathlib import Path
from typing import Any, Dict, List, Optional

from .schemas import (
    ArtifactLandingDrilldownSummary,
    EvidenceCoverageSummary,
    ExecutionTraceDrilldownSummary,
    GoalLedgerProjectionSummary,
    MemoryEdgeSummary,
    MemoryEvidenceSummary,
    MemoryVersionSummary,
    PersonalKnowledgeProjectionSummary,
    WorkspaceMemoryItemSummary,
)


def _serialize_workspace_memory_item(item) -> WorkspaceMemoryItemSummary:
    return WorkspaceMemoryItemSummary(
        id=item.id,
        kind=item.kind,
        layer=item.layer,
        title=item.title,
        claim=item.claim,
        summary=item.summary,
        lifecycle_status=item.lifecycle_status,
        verification_status=item.verification_status,
        salience=item.salience,
        confidence=item.confidence,
        subject_type=item.subject_type,
        subject_id=item.subject_id,
        supersedes_memory_id=getattr(item, "supersedes_memory_id", None),
        observed_at=item.observed_at,
        last_confirmed_at=getattr(item, "last_confirmed_at", None),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _serialize_memory_version(version) -> MemoryVersionSummary:
    return MemoryVersionSummary(
        id=version.id,
        version_no=version.version_no,
        update_mode=version.update_mode,
        claim_snapshot=version.claim_snapshot,
        summary_snapshot=version.summary_snapshot,
        metadata_snapshot=dict(getattr(version, "metadata_snapshot", {}) or {}),
        created_at=version.created_at,
        created_from_run_id=getattr(version, "created_from_run_id", None),
    )


def _path_exists(path_value: Any) -> bool:
    if not isinstance(path_value, str) or not path_value.strip():
        return False
    try:
        return Path(path_value).exists()
    except Exception:
        return False


def _build_artifact_landing_drilldown(
    metadata: Dict[str, Any],
) -> Optional[ArtifactLandingDrilldownSummary]:
    artifact_dir = metadata.get("landing_artifact_dir")
    result_json_path = metadata.get("landing_result_json_path")
    summary_md_path = metadata.get("landing_summary_md_path")
    attachments_count = metadata.get("landing_attachments_count")
    attachments = metadata.get("landing_attachments")
    landed_at = metadata.get("landing_landed_at")
    if not any(
        [
            artifact_dir,
            result_json_path,
            summary_md_path,
            attachments_count,
            attachments,
            landed_at,
        ]
    ):
        return None

    normalized_attachments = [
        value.strip()
        for value in attachments or []
        if isinstance(value, str) and value.strip()
    ]
    return ArtifactLandingDrilldownSummary(
        artifact_dir=artifact_dir if isinstance(artifact_dir, str) else None,
        result_json_path=result_json_path
        if isinstance(result_json_path, str)
        else None,
        summary_md_path=summary_md_path if isinstance(summary_md_path, str) else None,
        attachments_count=attachments_count if isinstance(attachments_count, int) else 0,
        attachments=normalized_attachments,
        landed_at=landed_at if isinstance(landed_at, str) else None,
        artifact_dir_exists=_path_exists(artifact_dir),
        result_json_exists=_path_exists(result_json_path),
        summary_md_exists=_path_exists(summary_md_path),
    )


def _build_execution_trace_drilldown(
    metadata: Dict[str, Any],
) -> Optional[ExecutionTraceDrilldownSummary]:
    trace_source = metadata.get("trace_source")
    trace_file_path = metadata.get("trace_file_path")
    sandbox_path = metadata.get("sandbox_path")
    if not any([trace_source, trace_file_path, sandbox_path]):
        return None
    return ExecutionTraceDrilldownSummary(
        trace_source=trace_source if isinstance(trace_source, str) else None,
        trace_file_path=trace_file_path if isinstance(trace_file_path, str) else None,
        trace_file_exists=_path_exists(trace_file_path),
        sandbox_path=sandbox_path if isinstance(sandbox_path, str) else None,
        tool_call_count=metadata.get("tool_call_count")
        if isinstance(metadata.get("tool_call_count"), int)
        else 0,
        file_change_count=metadata.get("file_change_count")
        if isinstance(metadata.get("file_change_count"), int)
        else 0,
        files_created_count=metadata.get("files_created_count")
        if isinstance(metadata.get("files_created_count"), int)
        else 0,
        files_modified_count=metadata.get("files_modified_count")
        if isinstance(metadata.get("files_modified_count"), int)
        else 0,
        success=metadata.get("success")
        if isinstance(metadata.get("success"), bool)
        else None,
        duration_seconds=float(metadata.get("duration_seconds"))
        if isinstance(metadata.get("duration_seconds"), (int, float))
        else None,
        task_description=metadata.get("task_description")
        if isinstance(metadata.get("task_description"), str)
        else None,
        output_summary=metadata.get("output_summary")
        if isinstance(metadata.get("output_summary"), str)
        else None,
    )


def _serialize_memory_evidence(link) -> MemoryEvidenceSummary:
    metadata = dict(getattr(link, "metadata", {}) or {})
    return MemoryEvidenceSummary(
        id=link.id,
        evidence_type=link.evidence_type,
        evidence_id=link.evidence_id,
        link_role=link.link_role,
        excerpt=getattr(link, "excerpt", None),
        confidence=getattr(link, "confidence", None),
        metadata=metadata,
        created_at=link.created_at,
        artifact_landing=_build_artifact_landing_drilldown(metadata)
        if link.evidence_type == "artifact_result"
        else None,
        execution_trace_drilldown=_build_execution_trace_drilldown(metadata)
        if link.evidence_type == "execution_trace"
        else None,
    )


def _serialize_memory_edge(edge) -> MemoryEdgeSummary:
    return MemoryEdgeSummary(
        id=edge.id,
        from_memory_id=edge.from_memory_id,
        to_memory_id=edge.to_memory_id,
        edge_type=edge.edge_type,
        weight=getattr(edge, "weight", None),
        valid_from=edge.valid_from,
        valid_to=getattr(edge, "valid_to", None),
        evidence_strength=getattr(edge, "evidence_strength", None),
        metadata=dict(getattr(edge, "metadata", {}) or {}),
        created_at=edge.created_at,
    )


def _serialize_personal_knowledge_projection(entry) -> PersonalKnowledgeProjectionSummary:
    return PersonalKnowledgeProjectionSummary(
        id=entry.id,
        knowledge_type=entry.knowledge_type,
        content=entry.content,
        status=entry.status,
        confidence=entry.confidence,
        created_at=entry.created_at,
        last_verified_at=getattr(entry, "last_verified_at", None),
    )


def _serialize_goal_projection(entry) -> GoalLedgerProjectionSummary:
    return GoalLedgerProjectionSummary(
        id=entry.id,
        title=entry.title,
        description=entry.description,
        status=entry.status,
        horizon=entry.horizon,
        created_at=entry.created_at,
        confirmed_at=getattr(entry, "confirmed_at", None),
    )


def _evidence_display_name(evidence_type: str) -> str:
    if evidence_type == "session_digest":
        return "Session Digest"
    if evidence_type == "meeting_decision":
        return "Meeting Decision"
    if evidence_type == "reasoning_trace":
        return "Reasoning Trace"
    if evidence_type == "intent_log":
        return "Intent Log"
    if evidence_type == "governance_decision":
        return "Governance Decision"
    if evidence_type == "lens_patch":
        return "Lens Patch"
    if evidence_type == "task_execution":
        return "Task Execution"
    if evidence_type == "execution_trace":
        return "Execution Trace"
    if evidence_type == "stage_result":
        return "Stage Result"
    if evidence_type == "artifact_result":
        return "Artifact Result"
    if evidence_type == "lens_receipt":
        return "Lens Receipt"
    if evidence_type == "writeback_receipt":
        return "Writeback Receipt"
    return evidence_type.replace("_", " ").title()


def _build_evidence_coverage(
    evidence_links: List[MemoryEvidenceSummary],
) -> EvidenceCoverageSummary:
    coverage = {
        "deliberation": 0,
        "execution": 0,
        "governance": 0,
        "support": 0,
        "derived": 0,
    }
    for link in evidence_links:
        if link.evidence_type in {
            "session_digest",
            "meeting_decision",
            "reasoning_trace",
        }:
            coverage["deliberation"] += 1
        if link.evidence_type in {
            "task_execution",
            "execution_trace",
            "stage_result",
            "artifact_result",
            "lens_receipt",
        }:
            coverage["execution"] += 1
        if link.evidence_type in {
            "writeback_receipt",
            "intent_log",
            "governance_decision",
            "lens_patch",
        }:
            coverage["governance"] += 1
        if link.link_role == "supports":
            coverage["support"] += 1
        if link.link_role == "derived_from":
            coverage["derived"] += 1
    return EvidenceCoverageSummary(**coverage)


def _evidence_priority(link: MemoryEvidenceSummary) -> int:
    if link.link_role == "supports" and link.evidence_type == "artifact_result":
        return 0
    if link.link_role == "supports" and link.evidence_type == "stage_result":
        return 1
    if link.link_role == "supports" and link.evidence_type == "task_execution":
        return 2
    if link.link_role == "supports" and link.evidence_type == "execution_trace":
        return 3
    if link.link_role == "supports" and link.evidence_type == "meeting_decision":
        return 4
    if link.link_role == "supports" and link.evidence_type == "governance_decision":
        return 5
    if link.link_role == "supports" and link.evidence_type == "lens_patch":
        return 6
    if link.link_role == "supports" and link.evidence_type == "intent_log":
        return 7
    if link.link_role == "supports" and link.evidence_type == "reasoning_trace":
        return 8
    if link.evidence_type == "session_digest":
        return 9
    if link.evidence_type == "lens_receipt":
        return 10
    if link.evidence_type == "writeback_receipt":
        return 11
    return 12


def _select_primary_evidence(
    evidence_links: List[MemoryEvidenceSummary],
) -> Optional[MemoryEvidenceSummary]:
    if not evidence_links:
        return None
    return sorted(
        evidence_links,
        key=lambda link: (_evidence_priority(link), link.created_at),
        reverse=False,
    )[0]
