from typing import Any, Dict, Literal, Optional

from .schemas import WorkflowEvidenceHealthSessionSummary


def _classify_workflow_evidence_diagnostics(
    diagnostics: Dict[str, Any],
) -> Literal["balanced", "tight", "sparse", "underused", "narrow", "empty"]:
    selected = diagnostics.get("selected_line_count")
    candidates = diagnostics.get("total_candidate_count")
    dropped = diagnostics.get("total_dropped_count")
    rendered_sections = diagnostics.get("rendered_section_count")
    utilization = diagnostics.get("budget_utilization_ratio")

    selected_count = selected if isinstance(selected, int) else 0
    candidate_count = candidates if isinstance(candidates, int) else 0
    dropped_count = dropped if isinstance(dropped, int) else 0
    rendered_section_count = (
        rendered_sections if isinstance(rendered_sections, int) else 0
    )
    utilization_ratio = (
        float(utilization) if isinstance(utilization, (int, float)) else 0.0
    )

    if selected_count == 0 and candidate_count == 0:
        return "empty"
    if dropped_count > 0 and utilization_ratio >= 0.85:
        return "tight"
    if selected_count > 0 and utilization_ratio < 0.4:
        return "underused"
    if selected_count == 0 and candidate_count > 0:
        return "sparse"
    if rendered_section_count <= 1:
        return "narrow"
    return "balanced"


def _serialize_workflow_evidence_health_session(session) -> Optional[WorkflowEvidenceHealthSessionSummary]:
    metadata = dict(getattr(session, "metadata", {}) or {})
    diagnostics = metadata.get("workflow_evidence_diagnostics")
    if not isinstance(diagnostics, dict):
        return None

    def _int_value(key: str) -> int:
        value = diagnostics.get(key)
        return value if isinstance(value, int) else 0

    def _float_value(key: str) -> float:
        value = diagnostics.get(key)
        return float(value) if isinstance(value, (int, float)) else 0.0

    return WorkflowEvidenceHealthSessionSummary(
        session_id=session.id,
        project_id=getattr(session, "project_id", None),
        thread_id=getattr(session, "thread_id", None),
        meeting_type=getattr(session, "meeting_type", "general") or "general",
        started_at=session.started_at,
        ended_at=getattr(session, "ended_at", None),
        profile=str(diagnostics.get("profile") or "general"),
        scope=str(diagnostics.get("scope") or "none"),
        total_candidate_count=_int_value("total_candidate_count"),
        selected_line_count=_int_value("selected_line_count"),
        total_line_budget=_int_value("total_line_budget"),
        total_dropped_count=_int_value("total_dropped_count"),
        rendered_section_count=_int_value("rendered_section_count"),
        budget_utilization_ratio=_float_value("budget_utilization_ratio"),
        classification=_classify_workflow_evidence_diagnostics(diagnostics),
    )
