"""Producer quality gate policy helpers for MeetingEngineRunner."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from backend.app.services.orchestration.meeting.meeting_engine_runner_core.artifact_helpers import (
    _append_unique,
    _as_dict,
    _clean_string,
)
from backend.app.services.orchestration.meeting.meeting_engine_runner_core.quality_input import (
    _strict_quality_gate_rollup,
)

def _bounded_json(value: Any, *, limit: int = 12000) -> str:
    try:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        rendered = str(value)
    if len(rendered) <= limit:
        return rendered
    return rendered[:limit] + "...<truncated>"

def _extract_json_object(text: Any) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        parsed = json.loads(raw[start : end + 1])
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}

def _truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return default

def _quality_requirements_from_aol_metadata(
    request_contract_aol: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    metadata = _as_dict(request_contract_aol)
    return _as_dict(metadata.get("quality_requirements"))

def _rewrite_until_quality_passed(quality_requirements: Dict[str, Any]) -> bool:
    content_quality = _as_dict(quality_requirements.get("content_quality"))
    return _truthy(quality_requirements.get("rewrite_until_quality_passed")) or _truthy(
        content_quality.get("rewrite_until_quality_passed")
    )

def _producer_eval_required_by_quality_requirements(
    quality_requirements: Dict[str, Any],
) -> bool:
    content_quality = _as_dict(quality_requirements.get("content_quality"))
    target = _as_dict(quality_requirements.get("target"))
    deliverable_kind = (_clean_string(target.get("deliverable_kind")) or "").lower()
    strict_keys = (
        "strict_acceptance_required",
        "storyboard_content_high_quality_required",
        "final_storyboard_high_quality_required",
        "meeting_final_acceptance_required",
        "scene_judge_required",
    )
    if any(_truthy(quality_requirements.get(key)) for key in strict_keys):
        return True
    if any(_truthy(content_quality.get(key)) for key in strict_keys):
        return True
    if "storyboard" not in deliverable_kind:
        return False
    return _truthy(content_quality.get("require_reference_grounding")) or (
        (_clean_string(content_quality.get("minimum_scene_specificity")) or "").lower()
        == "high"
    )

def _producer_rewrite_dispatch_request(
    *,
    producer_eval_summaries: List[Dict[str, Any]],
    quality_requirements: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    request: Dict[str, Any] = {}
    for summary in producer_eval_summaries:
        candidate = _as_dict(
            summary.get("rewrite_dispatch_request")
            or summary.get("producer_rewrite_dispatch_request")
        )
        if _clean_string(candidate.get("playbook_code")):
            request = candidate
            break
    if not request:
        return None

    producer_eval_artifact_ids = [
        _clean_string(summary.get("artifact_id"))
        for summary in producer_eval_summaries
        if _clean_string(summary.get("artifact_id"))
    ]
    source_playbook_codes = [
        _clean_string(summary.get("playbook_code"))
        for summary in producer_eval_summaries
        if _clean_string(summary.get("playbook_code"))
    ]
    auto_allowed = _rewrite_until_quality_passed(quality_requirements)
    input_params = _as_dict(request.get("input_params"))
    input_params.update(
        {
            "quality_requirements": quality_requirements,
            "producer_eval_artifact_ids": producer_eval_artifact_ids,
            "source_playbook_codes": source_playbook_codes,
            "rewrite_handoff": {
                "value_from": "producer_quality_gate.rewrite_handoff"
            },
        }
    )
    return {
        **request,
        "schema_version": request.get("schema_version")
        or "producer_quality_rewrite_dispatch_request.v1",
        "dispatch_mode": (
            "auto_launch_allowed"
            if auto_allowed
            else "explicit_quality_requirement_required"
        ),
        "required_inputs": list(
            request.get("required_inputs")
            or [
                "storyboard",
                "reference_cue_map",
                "content_quality_eval",
                "quality_requirements",
                "rewrite_handoff",
            ]
        ),
        "input_params": input_params,
    }

def _producer_quality_gate_fallback(
    *,
    producer_review: Dict[str, Any],
    producer_eval_summaries: List[Dict[str, Any]],
    quality_requirements: Optional[Dict[str, Any]] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    strict_rollup = _strict_quality_gate_rollup(producer_eval_summaries)
    review_state = producer_review.get("review_state")
    recommended_actions = list(producer_review.get("recommended_actions") or [])
    quality_requirements_payload = _as_dict(quality_requirements)
    producer_result_required = _producer_eval_required_by_quality_requirements(
        quality_requirements_payload
    )
    producer_result_missing = producer_result_required and not producer_eval_summaries
    failed_gate_ids = list(strict_rollup.get("failed_gate_ids") or [])
    if producer_result_missing:
        review_state = review_state or "producer_result_missing"
        _append_unique(failed_gate_ids, "PRODUCER_RESULT_REQUIRED")
        _append_unique(
            recommended_actions,
            "resolve_producer_result:storyboard_quality_eval",
        )
    needs_revision = review_state in {
        "needs_revision",
        "needs_reference_analysis",
        "failed",
        "producer_result_missing",
    } or bool(strict_rollup.get("strict_gate_failed")) or producer_result_missing
    if strict_rollup.get("strict_gate_failed") or producer_result_missing:
        review_state = review_state or "needs_revision"
        for gate_id in failed_gate_ids:
            _append_unique(recommended_actions, f"resolve_quality_gate:{gate_id}")
    gate_state = (
        "needs_reference_analysis"
        if review_state == "needs_reference_analysis"
        else "blocked_for_revision"
        if needs_revision
        else "passed"
    )
    dispatch_request = (
        _producer_rewrite_dispatch_request(
            producer_eval_summaries=producer_eval_summaries,
            quality_requirements=quality_requirements_payload,
        )
        if needs_revision
        else None
    )
    return {
        "schema_version": "meeting_producer_quality_gate.v1",
        "gate_state": gate_state,
        "review_state": review_state,
        "review_reason": producer_review.get("review_reason"),
        "llm_review_status": "fallback" if needs_revision else "not_required",
        "llm_review_error": reason,
        "decision": (
            "reference_analysis_required"
            if review_state == "needs_reference_analysis"
            else "producer_result_required"
            if producer_result_missing
            else "rewrite_required"
            if needs_revision
            else "accept"
        ),
        "completion_status": "needs_revision" if needs_revision else "accepted",
        "recommended_actions": recommended_actions,
        "strict_acceptance_required": bool(
            strict_rollup.get("strict_acceptance_required") or producer_result_required
        ),
        "strict_gate_failed": bool(
            strict_rollup.get("strict_gate_failed") or producer_result_missing
        ),
        "producer_result_required": producer_result_required,
        "producer_result_missing": producer_result_missing,
        "failed_gate_ids": failed_gate_ids,
        "storyboard_content_high_quality_pass": strict_rollup.get(
            "storyboard_content_high_quality_pass"
        ),
        "final_storyboard_high_quality_pass": strict_rollup.get(
            "final_storyboard_high_quality_pass"
        ),
        "meeting_final_acceptance_pass": strict_rollup.get(
            "meeting_final_acceptance_pass"
        ),
        "rewrite_handoff": (
            {
                "kind": "producer_quality_rewrite_handoff",
                "source": "meeting_engine_runner",
                "target_review_state": review_state,
                "producer_eval_artifact_ids": [
                    summary.get("artifact_id")
                    for summary in producer_eval_summaries
                    if summary.get("artifact_id")
                ],
                "producer_eval_summaries": producer_eval_summaries,
                "required_actions": recommended_actions,
                "dispatch_request": dispatch_request,
            }
            if needs_revision
            else None
        ),
    }

def _normalize_meeting_quality_review(
    raw_review: Dict[str, Any],
    *,
    fallback_gate: Dict[str, Any],
) -> Dict[str, Any]:
    review = dict(raw_review or {})
    decision = _clean_string(review.get("decision")) or fallback_gate["decision"]
    if decision not in {
        "accept",
        "accept_with_risk",
        "rewrite_required",
        "reference_analysis_required",
        "human_review_required",
        "producer_result_required",
    }:
        decision = fallback_gate["decision"]
    if fallback_gate.get("strict_gate_failed") and decision in {
        "accept",
        "accept_with_risk",
    }:
        decision = fallback_gate["decision"]

    actions = list(fallback_gate.get("recommended_actions") or [])
    for action in list(review.get("recommended_actions") or []):
        _append_unique(actions, _clean_string(action))

    gate_state = fallback_gate["gate_state"]
    if decision in {
        "rewrite_required",
        "human_review_required",
        "producer_result_required",
    }:
        gate_state = "blocked_for_revision"
    elif decision == "reference_analysis_required":
        gate_state = "needs_reference_analysis"
    elif decision == "accept_with_risk":
        gate_state = "accept_with_risk"
    elif decision == "accept":
        gate_state = "passed"

    rewrite_handoff = fallback_gate.get("rewrite_handoff")
    if isinstance(rewrite_handoff, dict):
        rewrite_handoff = {
            **rewrite_handoff,
            "meeting_review": {
                "decision": decision,
                "rationale": _clean_string(review.get("rationale")),
                "rewrite_instructions": review.get("rewrite_instructions") or [],
                "required_reference_questions": review.get(
                    "required_reference_questions"
                )
                or [],
            },
            "required_actions": actions,
        }

    return {
        **fallback_gate,
        "gate_state": gate_state,
        "llm_review_status": "completed",
        "llm_review_error": None,
        "decision": decision,
        "completion_status": (
            "accepted"
            if decision == "accept"
            else "accepted_with_risk"
            if decision == "accept_with_risk"
            else "needs_revision"
        ),
        "recommended_actions": actions,
        "rationale": _clean_string(review.get("rationale")),
        "rewrite_instructions": review.get("rewrite_instructions") or [],
        "required_reference_questions": review.get("required_reference_questions") or [],
        "rewrite_handoff": rewrite_handoff,
    }
