import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from backend.app.core.trace import TraceNodeType, TraceStatus


@dataclass
class IntentTraceHandle:
    trace_id: Optional[str] = None
    node_id: Optional[str] = None


def utc_now() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def start_intent_trace(
    *,
    recorder_factory: Callable[[], Any],
    profile_id: str,
    workspace_id: Optional[str],
    user_message: str,
    model_name: Optional[str],
    emphasis: str,
    available_tools_count: int,
    logger: Any,
) -> IntentTraceHandle:
    """Start the existing trace node for the intent LLM call."""
    try:
        trace_recorder = recorder_factory()
        trace_id = trace_recorder.create_trace(
            workspace_id=workspace_id or "",
            execution_id=f"intent_{profile_id}_{int(utc_now().timestamp())}",
            user_id=profile_id,
        )
        node_id = trace_recorder.start_node(
            trace_id=trace_id,
            node_type=TraceNodeType.LLM,
            name=f"llm:intent_analysis:{emphasis}",
            input_data={
                "user_message": user_message[:200],
                "model_name": model_name,
                "emphasis": emphasis,
                "available_tools_count": available_tools_count,
            },
            metadata={
                "workspace_id": workspace_id or "",
                "model_name": model_name,
                "emphasis": emphasis,
            },
        )
        return IntentTraceHandle(trace_id=trace_id, node_id=node_id)
    except Exception as exc:
        logger.warning("Failed to start trace node for LLM intent analysis: %s", exc)
        return IntentTraceHandle()


def finish_intent_trace_success(
    *,
    handle: IntentTraceHandle,
    recorder_factory: Callable[[], Any],
    prompt: str,
    response: Any,
    result: Any,
    latency_ms: int,
    logger: Any,
) -> None:
    """End the existing intent trace node after a successful LLM call."""
    if not handle.trace_id or not handle.node_id:
        return

    try:
        trace_recorder = recorder_factory()
        input_tokens = len(prompt.split()) * 1.3
        output_tokens = len(str(response).split()) * 1.3
        trace_recorder.end_node(
            trace_id=handle.trace_id,
            node_id=handle.node_id,
            status=TraceStatus.SUCCESS,
            output_data={
                "relevant_tools_count": len(result.relevant_tools) if result else 0,
                "confidence": result.confidence if result else 0.0,
            },
            cost_tokens=int(input_tokens + output_tokens),
            latency_ms=latency_ms,
        )
    except Exception as exc:
        logger.warning("Failed to end trace node for LLM intent analysis: %s", exc)


def finish_intent_trace_failure(
    *,
    handle: IntentTraceHandle,
    recorder_factory: Callable[[], Any],
    error: Exception,
    latency_ms: int,
    logger: Any,
) -> None:
    """End the existing intent trace node after a failed LLM call."""
    if not handle.trace_id or not handle.node_id:
        return

    try:
        trace_recorder = recorder_factory()
        trace_recorder.end_node(
            trace_id=handle.trace_id,
            node_id=handle.node_id,
            status=TraceStatus.FAILED,
            error_message=str(error)[:500],
            error_stack=traceback.format_exc(),
            latency_ms=latency_ms,
        )
    except Exception as exc:
        logger.warning(
            "Failed to end trace node for failed LLM intent analysis: %s",
            exc,
        )
