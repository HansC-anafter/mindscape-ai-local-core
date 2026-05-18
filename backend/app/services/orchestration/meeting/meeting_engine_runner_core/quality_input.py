"""Producer quality input normalization for MeetingEngineRunner."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.app.services.orchestration.meeting.meeting_engine_runner_core.artifact_helpers import (
    _append_unique,
    _as_dict,
    _clean_string,
)

def _raw_producer_eval_summaries(value: Any, *, depth: int = 0) -> List[Dict[str, Any]]:
    if depth > 8:
        return []
    found: List[Dict[str, Any]] = []
    if isinstance(value, dict):
        direct = value.get("producer_eval_summary")
        if isinstance(direct, dict):
            found.append(dict(direct))
        elif isinstance(direct, list):
            found.extend(dict(item) for item in direct if isinstance(item, dict))

        if (
            value.get("schema_version") == "producer_eval_summary.v1"
            or (
                "review_state" in value
                and "passed" in value
                and (
                    "producer" in value
                    or "pack_code" in value
                    or "artifact_kind" in value
                )
            )
        ):
            found.append(dict(value))

        for nested in value.values():
            found.extend(_raw_producer_eval_summaries(nested, depth=depth + 1))
    elif isinstance(value, list):
        for item in value:
            found.extend(_raw_producer_eval_summaries(item, depth=depth + 1))
    return found

def _normalize_producer_eval_summary(
    raw: Dict[str, Any],
    *,
    source: str,
    artifact_id: Optional[str] = None,
    artifact_kind: Optional[str] = None,
    execution_id: Optional[str] = None,
) -> Dict[str, Any]:
    summary = dict(raw or {})
    summary.setdefault("schema_version", "producer_eval_summary.v1")
    summary.setdefault("source", source)
    if artifact_id:
        summary.setdefault("artifact_id", artifact_id)
    if artifact_kind:
        summary.setdefault("artifact_kind", artifact_kind)
    if execution_id:
        summary.setdefault("execution_id", execution_id)

    review_state = _clean_string(summary.get("review_state"))
    passed = summary.get("passed")
    if isinstance(passed, bool):
        passed_bool: Optional[bool] = passed
    elif passed is None:
        passed_bool = None
    else:
        passed_bool = bool(passed)
    if not review_state:
        review_state = "passed" if passed_bool is True else "needs_revision"
    summary["review_state"] = review_state
    if passed_bool is not None:
        summary["passed"] = passed_bool
    summary["needs_revision"] = bool(
        summary.get("needs_revision")
        or review_state in {"needs_revision", "needs_reference_analysis", "failed"}
        or passed_bool is False
    )
    summary["rewrite_recommended"] = bool(summary.get("rewrite_recommended"))
    summary["needs_reference_analysis"] = bool(
        summary.get("needs_reference_analysis")
        or review_state == "needs_reference_analysis"
    )
    summary.setdefault("blocking_findings", [])
    summary.setdefault("warnings", [])
    summary.setdefault("recommended_actions", [])
    return summary

def _producer_eval_summaries_from_value(
    value: Any,
    *,
    source: str,
    artifact_id: Optional[str] = None,
    artifact_kind: Optional[str] = None,
    execution_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    seen = set()
    for raw in _raw_producer_eval_summaries(value):
        normalized = _normalize_producer_eval_summary(
            raw,
            source=source,
            artifact_id=artifact_id,
            artifact_kind=artifact_kind,
            execution_id=execution_id,
        )
        key = (
            normalized.get("artifact_id"),
            normalized.get("artifact_kind"),
            normalized.get("review_state"),
            str(normalized.get("score")),
        )
        if key in seen:
            continue
        seen.add(key)
        summaries.append(normalized)
    return summaries

def _producer_review_result(
    summaries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not summaries:
        return {
            "review_state": None,
            "review_reason": None,
            "recommended_actions": [],
        }

    failing = [
        summary
        for summary in summaries
        if summary.get("passed") is False
        or summary.get("needs_revision")
        or summary.get("rewrite_recommended")
        or summary.get("needs_reference_analysis")
        or summary.get("review_state") in {"needs_revision", "needs_reference_analysis", "failed"}
    ]
    if not failing:
        return {
            "review_state": "passed",
            "review_reason": "producer_eval_passed",
            "recommended_actions": [],
        }

    needs_reference_analysis = any(
        summary.get("needs_reference_analysis") for summary in failing
    )
    rewrite_recommended = any(summary.get("rewrite_recommended") for summary in failing)
    actions: List[str] = []
    if needs_reference_analysis:
        _append_unique(actions, "attach_reference_analysis")
        _append_unique(actions, "ask_human_for_reference_cues")
    if rewrite_recommended:
        _append_unique(actions, "rewrite_storyboard_script_with_reference_cues")
    for summary in failing:
        for action in list(summary.get("recommended_actions") or []):
            _append_unique(actions, _clean_string(action))
    _append_unique(actions, "accept_with_risk")
    return {
        "review_state": (
            "needs_reference_analysis"
            if needs_reference_analysis
            else "needs_revision"
        ),
        "review_reason": "producer_eval_requires_review",
        "recommended_actions": actions,
    }

def _strict_quality_gate_rollup(
    producer_eval_summaries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    strict_summaries: List[Dict[str, Any]] = []
    failed_gate_ids: List[str] = []
    for summary in producer_eval_summaries:
        gate_summary = _as_dict(summary.get("quality_gate_summary"))
        if not gate_summary:
            continue
        if not bool(gate_summary.get("strict_acceptance_required")):
            continue
        strict_summaries.append(gate_summary)
        for gate_id in list(gate_summary.get("failed_gate_ids") or []):
            _append_unique(failed_gate_ids, _clean_string(gate_id))

    if not strict_summaries:
        return {
            "strict_acceptance_required": False,
            "strict_gate_failed": False,
            "failed_gate_ids": [],
        }

    content_pass = all(
        bool(summary.get("storyboard_content_high_quality_pass"))
        for summary in strict_summaries
    )
    final_required = any(
        _clean_string(summary.get("gate_stage")) in {"final", "milestone"}
        for summary in strict_summaries
    )
    final_pass = all(
        bool(summary.get("final_storyboard_high_quality_pass"))
        for summary in strict_summaries
    )
    meeting_pass = all(
        bool(summary.get("meeting_final_acceptance_pass"))
        for summary in strict_summaries
    )
    strict_gate_failed = not content_pass or (final_required and not meeting_pass)
    if not failed_gate_ids and strict_gate_failed:
        _append_unique(
            failed_gate_ids,
            (
                "MEETING_FINAL_ACCEPTANCE"
                if final_required and not meeting_pass
                else "STORYBOARD_CONTENT_HIGH_QUALITY"
            ),
        )
    return {
        "strict_acceptance_required": True,
        "strict_gate_failed": strict_gate_failed,
        "failed_gate_ids": failed_gate_ids,
        "storyboard_content_high_quality_pass": content_pass,
        "final_storyboard_high_quality_pass": final_pass,
        "meeting_final_acceptance_pass": meeting_pass,
        "gate_stage": "final" if final_required else "content",
    }
