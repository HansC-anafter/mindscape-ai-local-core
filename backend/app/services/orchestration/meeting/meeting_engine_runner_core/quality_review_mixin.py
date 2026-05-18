"""Producer quality review mixin for MeetingEngineRunner."""

from __future__ import annotations

from typing import Any, Dict, List

from backend.app.services.orchestration.meeting.meeting_engine_runner_core.quality_policy import (
    _bounded_json,
    _extract_json_object,
    _normalize_meeting_quality_review,
    _producer_quality_gate_fallback,
    _quality_requirements_from_aol_metadata,
)


class MeetingEngineRunnerQualityReviewMixin:
    async def _producer_quality_gate_review(
        self,
        *,
        engine: Any,
        producer_review: Dict[str, Any],
        producer_eval_summaries: List[Dict[str, Any]],
        request_contract_aol: Dict[str, Any],
        task_ir_artifacts: List[Dict[str, Any]],
        user_message: str,
    ) -> Dict[str, Any]:
        quality_requirements = _quality_requirements_from_aol_metadata(
            request_contract_aol
        )
        fallback_gate = _producer_quality_gate_fallback(
            producer_review=producer_review,
            producer_eval_summaries=producer_eval_summaries,
            quality_requirements=quality_requirements,
        )
        if fallback_gate.get("producer_result_missing"):
            return fallback_gate
        if fallback_gate["gate_state"] == "passed":
            return fallback_gate

        generate_text = getattr(engine, "_generate_text", None)
        if not callable(generate_text):
            return _producer_quality_gate_fallback(
                producer_review=producer_review,
                producer_eval_summaries=producer_eval_summaries,
                quality_requirements=quality_requirements,
                reason="meeting_llm_review_unavailable",
            )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are the MeetingEngine producer-quality reviewer. "
                    "Decide whether the produced storyboard can be accepted, "
                    "accepted with explicit risk, requires rewrite, requires "
                    "reference analysis, or requires human review. Return JSON only."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Review this producer evaluator result and choose the next "
                    "orchestration action.\n\n"
                    f"Original user instruction:\n{user_message}\n\n"
                    f"AOL/request contract metadata:\n{_bounded_json(request_contract_aol)}\n\n"
                    f"Producer review rollup:\n{_bounded_json(producer_review)}\n\n"
                    f"Producer eval summaries:\n{_bounded_json(producer_eval_summaries)}\n\n"
                    f"TaskIR artifacts:\n{_bounded_json(task_ir_artifacts, limit=8000)}\n\n"
                    "Return this JSON shape exactly:\n"
                    "{\n"
                    '  "decision": "accept|accept_with_risk|rewrite_required|reference_analysis_required|human_review_required|producer_result_required",\n'
                    '  "rationale": "short reason",\n'
                    '  "recommended_actions": ["action_id"],\n'
                    '  "rewrite_instructions": ["concrete per-scene/content rewrite instruction"],\n'
                    '  "required_reference_questions": ["question if reference evidence is missing"]\n'
                    "}\n"
                    "Do not rewrite the full storyboard here. Produce routing "
                    "instructions for the next pass."
                ),
            },
        ]
        try:
            review_text = await generate_text(
                messages,
                max_tokens=1200,
                capability_profile="precise",
            )
        except TypeError:
            try:
                review_text = await generate_text(messages)
            except Exception as exc:
                return _producer_quality_gate_fallback(
                    producer_review=producer_review,
                    producer_eval_summaries=producer_eval_summaries,
                    quality_requirements=quality_requirements,
                    reason=str(exc),
                )
        except Exception as exc:
            return _producer_quality_gate_fallback(
                producer_review=producer_review,
                producer_eval_summaries=producer_eval_summaries,
                quality_requirements=quality_requirements,
                reason=str(exc),
            )

        parsed = _extract_json_object(review_text)
        if not parsed:
            return _producer_quality_gate_fallback(
                producer_review=producer_review,
                producer_eval_summaries=producer_eval_summaries,
                quality_requirements=quality_requirements,
                reason="meeting_llm_review_non_json",
            )
        return _normalize_meeting_quality_review(
            parsed,
            fallback_gate=fallback_gate,
        )
