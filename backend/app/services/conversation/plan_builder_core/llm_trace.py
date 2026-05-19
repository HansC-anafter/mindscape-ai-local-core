"""Trace helpers for LLM plan generation."""

from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.trace import get_trace_recorder, TraceNodeType, TraceStatus

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def start_plan_generation_trace(
    *,
    workspace_id: str,
    profile_id: str,
    message: str,
    model_name: str,
    available_packs: List[str],
    capability_profile: Optional[str],
) -> Tuple[Optional[str], Optional[str]]:
    """Start a best-effort trace node for LLM plan generation."""
    try:
        trace_recorder = get_trace_recorder()
        trace_id = trace_recorder.create_trace(
            workspace_id=workspace_id,
            execution_id=f"plan_{profile_id}_{int(utc_now().timestamp())}",
            user_id=profile_id,
        )
        trace_node_id = trace_recorder.start_node(
            trace_id=trace_id,
            node_type=TraceNodeType.LLM,
            name="llm:plan_generation",
            input_data={
                "message": message[:200],
                "model_name": model_name,
                "available_packs_count": len(available_packs),
            },
            metadata={
                "model_name": model_name,
                "capability_profile": capability_profile,
            },
        )
        return trace_id, trace_node_id
    except Exception as exc:
        logger.warning("Failed to start trace node for LLM plan generation: %s", exc)
        return None, None


def end_plan_generation_trace_success(
    *,
    trace_id: Optional[str],
    trace_node_id: Optional[str],
    llm_start_time: datetime,
    context_with_history: str,
    result: Dict[str, Any],
) -> None:
    """End the trace node after a successful extraction call."""
    if not trace_node_id or not trace_id:
        return

    try:
        trace_recorder = get_trace_recorder()
        llm_end_time = utc_now()
        latency_ms = int((llm_end_time - llm_start_time).total_seconds() * 1000)
        input_tokens = int(len(context_with_history.split()) * 1.3)
        output_tokens = int(len(str(result).split()) * 1.3)
        total_tokens = input_tokens + output_tokens

        trace_recorder.end_node(
            trace_id=trace_id,
            node_id=trace_node_id,
            status=TraceStatus.SUCCESS,
            output_data={
                "tasks_count": len(result.get("extracted_data", {}).get("tasks", [])),
            },
            cost_tokens=total_tokens,
            latency_ms=latency_ms,
        )
    except Exception as exc:
        logger.warning("Failed to end trace node for LLM plan generation: %s", exc)


def end_plan_generation_trace_failure(
    *,
    trace_id: Optional[str],
    trace_node_id: Optional[str],
    llm_start_time: datetime,
    error: Exception,
) -> None:
    """End the trace node after a failed extraction call."""
    if not trace_node_id or not trace_id:
        return

    try:
        trace_recorder = get_trace_recorder()
        llm_end_time = utc_now()
        latency_ms = int((llm_end_time - llm_start_time).total_seconds() * 1000)
        trace_recorder.end_node(
            trace_id=trace_id,
            node_id=trace_node_id,
            status=TraceStatus.FAILED,
            error_message=str(error)[:500],
            error_stack=traceback.format_exc(),
            latency_ms=latency_ms,
        )
    except Exception as exc:
        logger.warning(
            "Failed to end trace node for failed LLM plan generation: %s",
            exc,
        )
