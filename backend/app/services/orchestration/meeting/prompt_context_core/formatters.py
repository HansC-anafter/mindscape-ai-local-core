"""Workflow evidence formatter helpers."""

from typing import Any, Dict


def _format_task_execution_line(task: Any) -> str:
    status = getattr(getattr(task, "status", None), "value", None) or str(
        getattr(task, "status", "unknown")
    )
    pack_id = str(getattr(task, "pack_id", "unknown") or "unknown")
    execution_id = str(getattr(task, "execution_id", "") or "")
    result = getattr(task, "result", None)
    summary = _extract_task_summary(task)
    trace_note = ""
    if isinstance(result, dict) and isinstance(result.get("execution_trace"), dict):
        trace_note = " trace=yes"
    execution_label = f" exec={execution_id[:8]}" if execution_id else ""
    summary_label = f" :: {summary}" if summary else ""
    return f"  - [{status}] {pack_id}{execution_label}{trace_note}{summary_label}"


def _extract_task_summary(task: Any) -> str:
    result = getattr(task, "result", None)
    if isinstance(result, dict):
        for key in ("summary", "message", "result_summary", "title", "output"):
            value = result.get(key)
            if isinstance(value, str) and value.strip():
                return _shorten(value.strip(), 160)
        trace_payload = result.get("execution_trace")
        if isinstance(trace_payload, dict):
            for key in ("output_summary", "task_description"):
                value = trace_payload.get(key)
                if isinstance(value, str) and value.strip():
                    return _shorten(value.strip(), 160)
    params = getattr(task, "params", None)
    if isinstance(params, dict):
        for key in ("title", "description", "task", "prompt"):
            value = params.get(key)
            if isinstance(value, str) and value.strip():
                return _shorten(value.strip(), 160)
    return ""


def _format_stage_result_line(stage_result: Any) -> str:
    stage_name = str(getattr(stage_result, "stage_name", "stage") or "stage")
    result_type = str(getattr(stage_result, "result_type", "result") or "result")
    review_status = getattr(stage_result, "review_status", None)
    preview = getattr(stage_result, "preview", None)
    if not preview and isinstance(getattr(stage_result, "content", None), dict):
        for key in ("summary", "message", "title", "result_summary"):
            value = stage_result.content.get(key)
            if isinstance(value, str) and value.strip():
                preview = value.strip()
                break
    review_label = f" review={review_status}" if review_status else ""
    preview_label = f" :: {_shorten(str(preview), 160)}" if preview else ""
    return f"  - {stage_name}/{result_type}{review_label}{preview_label}"


def _format_artifact_line(artifact: Any) -> str:
    artifact_type = getattr(getattr(artifact, "artifact_type", None), "value", None) or str(
        getattr(artifact, "artifact_type", "artifact")
    )
    title = _shorten(str(getattr(artifact, "title", "Artifact") or "Artifact"), 72)
    summary = str(getattr(artifact, "summary", "") or "").strip()
    metadata = getattr(artifact, "metadata", None) or {}
    landing = metadata.get("landing") if isinstance(metadata, dict) else {}
    attachments_count = (
        landing.get("attachments_count")
        if isinstance(landing, dict)
        else None
    )
    attachment_label = (
        f" attachments={attachments_count}"
        if isinstance(attachments_count, int)
        else ""
    )
    summary_label = f" :: {_shorten(summary, 140)}" if summary else ""
    return f"  - {title} [{artifact_type}]{attachment_label}{summary_label}"


def _format_governance_decision_line(decision: Dict[str, Any]) -> str:
    approved = bool(decision.get("approved"))
    layer = str(decision.get("layer") or "governance")
    status = "approved" if approved else "blocked"
    playbook_code = decision.get("playbook_code")
    reason = str(decision.get("reason") or "").strip()
    playbook_label = f" playbook={playbook_code}" if playbook_code else ""
    reason_label = f" :: {_shorten(reason, 140)}" if reason else ""
    return f"  - [{status}] {layer}{playbook_label}{reason_label}"


def _format_intent_log_line(intent_log: Any) -> str:
    final_decision = getattr(intent_log, "final_decision", None) or {}
    route = (
        final_decision.get("playbook_code")
        or final_decision.get("task_domain")
        or final_decision.get("interaction_type")
        or "unspecified"
    )
    override_label = (
        " override=yes"
        if getattr(intent_log, "user_override", None)
        else ""
    )
    raw_input = _shorten(str(getattr(intent_log, "raw_input", "") or "").strip(), 140)
    channel = str(getattr(intent_log, "channel", "unknown") or "unknown")
    return f"  - [{channel}] route={route}{override_label} :: {raw_input}"


def _format_lens_patch_line(patch: Any) -> str:
    status = getattr(getattr(patch, "status", None), "value", None) or str(
        getattr(patch, "status", "unknown")
    )
    confidence = getattr(patch, "confidence", None)
    delta = getattr(patch, "delta", None) or {}
    delta_keys = list(delta.keys())[:3] if isinstance(delta, dict) else []
    delta_label = ", ".join(delta_keys) if delta_keys else "lens delta recorded"
    confidence_label = (
        f" confidence={float(confidence):.2f}"
        if isinstance(confidence, (int, float))
        else ""
    )
    return f"  - [{status}]{confidence_label} :: {_shorten(delta_label, 140)}"


def _shorten(value: str, limit: int) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
