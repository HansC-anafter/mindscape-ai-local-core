"""Workflow evidence scoring helpers."""

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from backend.app.services.orchestration.meeting.prompt_context_core.formatters import (
    _extract_task_summary,
)


def _sort_by_score(items: List[Any], score_fn: Callable[[Any], float]) -> List[Any]:
    return sorted(items, key=score_fn, reverse=True)


def _score_task_execution(task: Any, meeting_profile: str) -> float:
    score = _recency_score(
        getattr(task, "completed_at", None) or getattr(task, "created_at", None)
    )
    status = getattr(getattr(task, "status", None), "value", None) or str(
        getattr(task, "status", "")
    )
    if status == "succeeded":
        score += 5.0
    elif status == "running":
        score += 2.0
    if _extract_task_summary(task):
        score += 2.0
    result = getattr(task, "result", None) or {}
    if isinstance(result, dict) and isinstance(result.get("execution_trace"), dict):
        score += 1.5
    params = getattr(task, "params", None) or {}
    if isinstance(params, dict) and any(params.get(key) for key in ("title", "description", "task")):
        score += 0.5
    if meeting_profile == "decision":
        score += 1.0 if status == "succeeded" else 0.0
    if meeting_profile == "reflection":
        score += 1.0 if isinstance(result, dict) and result.get("execution_trace") else 0.0
    return score


def _score_stage_result(stage_result: Any, meeting_profile: str) -> float:
    score = _recency_score(getattr(stage_result, "created_at", None))
    if getattr(stage_result, "requires_review", False):
        score += 4.0
    review_status = str(getattr(stage_result, "review_status", "") or "")
    if review_status in {"pending", "needs_review"}:
        score += 3.0
    if getattr(stage_result, "preview", None):
        score += 1.5
    if getattr(stage_result, "artifact_id", None):
        score += 1.0
    if meeting_profile == "review":
        score += 3.0
    return score


def _score_artifact(artifact: Any, meeting_profile: str) -> float:
    score = _recency_score(
        getattr(artifact, "updated_at", None) or getattr(artifact, "created_at", None)
    )
    if getattr(artifact, "summary", None):
        score += 1.5
    metadata = getattr(artifact, "metadata", None) or {}
    landing = metadata.get("landing") if isinstance(metadata, dict) else {}
    attachments_count = landing.get("attachments_count") if isinstance(landing, dict) else 0
    if isinstance(attachments_count, int) and attachments_count > 0:
        score += min(float(attachments_count), 3.0)
    artifact_type = getattr(getattr(artifact, "artifact_type", None), "value", None) or str(
        getattr(artifact, "artifact_type", "")
    )
    if artifact_type in {"draft", "docx", "post", "code"}:
        score += 1.0
    if meeting_profile == "review":
        score += 1.0
    return score


def _score_governance_decision(decision: Dict[str, Any], meeting_profile: str) -> float:
    score = _recency_score(_coerce_datetime(decision.get("timestamp")))
    approved = bool(decision.get("approved"))
    score += 3.0 if not approved else 1.5
    if decision.get("reason"):
        score += 2.0
    layer = str(decision.get("layer") or "")
    if layer in {"policy", "approval", "risk"}:
        score += 2.0
    if decision.get("playbook_code"):
        score += 1.0
    if meeting_profile in {"review", "decision"}:
        score += 2.0
    return score


def _score_intent_log(intent_log: Any, meeting_profile: str) -> float:
    score = _recency_score(getattr(intent_log, "timestamp", None))
    final_decision = getattr(intent_log, "final_decision", None) or {}
    if final_decision.get("playbook_code") or final_decision.get("selected_playbook_code"):
        score += 2.0
    if final_decision.get("requires_user_approval"):
        score += 3.0
    if getattr(intent_log, "user_override", None):
        score += 4.0
    pipeline_steps = getattr(intent_log, "pipeline_steps", None) or {}
    if isinstance(pipeline_steps, dict) and pipeline_steps:
        score += 1.0
    if meeting_profile == "decision":
        score += 2.0
    return score


def _recency_score(value: Any) -> float:
    dt = _coerce_datetime(value)
    if dt is None:
        return 0.0
    age_hours = max((datetime.now(dt.tzinfo) - dt).total_seconds() / 3600.0, 0.0)
    return max(0.0, 6.0 - min(age_hours, 6.0))


def _coerce_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None
