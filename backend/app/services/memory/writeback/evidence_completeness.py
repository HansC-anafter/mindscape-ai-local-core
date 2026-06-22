"""Evidence completeness summaries for memory writeback runs."""

from __future__ import annotations

from typing import Any, Mapping


def _count(values: Mapping[str, Any], key: str) -> int:
    try:
        return int(values.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def summarize_writeback_evidence_completeness(values: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize whether a writeback has enough evidence to be trusted."""

    supporting_counts = {
        "reasoning_trace": _count(values, "reasoning_trace_count"),
        "lens_receipt": _count(values, "lens_receipt_count"),
        "meeting_decision": _count(values, "meeting_decision_count"),
        "task_execution": _count(values, "task_execution_count"),
        "artifact_result": _count(values, "artifact_result_count"),
        "phase2": sum(
            _count(values, key)
            for key in (
                "stage_result_evidence_count",
                "execution_trace_evidence_count",
                "intent_log_evidence_count",
                "governance_decision_evidence_count",
                "lens_patch_evidence_count",
            )
        ),
    }
    required = {
        "session_digest": bool(values.get("digest")),
        "memory_item": bool(values.get("item")),
    }
    missing_required = [
        name for name, present in required.items() if not present
    ]
    has_supporting_evidence = any(count > 0 for count in supporting_counts.values())
    status = (
        "verified"
        if not missing_required and has_supporting_evidence
        else "candidate"
    )
    return {
        "status": status,
        "missing_required": missing_required,
        "supporting_evidence": [
            name for name, count in supporting_counts.items() if count > 0
        ],
        "counts": supporting_counts,
    }
