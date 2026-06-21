"""Memory evidence excerpt builders."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .lens_patch import LensPatch
from .lens_receipt import LensReceipt
from .mindscape import IntentLog
from .personal_governance.writeback_receipt import WritebackReceipt
from .reasoning_trace import ReasoningTrace
from .workspace import Artifact, Task


def _shorten(value: str, limit: int) -> str:
    if not value:
        return ""
    value = " ".join(value.split())
    return value[:limit]


def _build_reasoning_trace_excerpt(trace: ReasoningTrace) -> str:
    graph = trace.graph
    if graph.answer:
        return _shorten(graph.answer.strip(), 280)

    for preferred_type in ("conclusion", "inference", "evidence", "premise", "risk"):
        for node in graph.nodes:
            if node.type == preferred_type and node.content.strip():
                return _shorten(node.content.strip(), 280)

    return _shorten(f"Reasoning trace {trace.id}", 280)


def _build_writeback_receipt_excerpt(receipt: WritebackReceipt) -> str:
    summary = (
        f"{receipt.target_table} {receipt.writeback_type} "
        f"status={receipt.status} target={receipt.target_id}"
    )
    return _shorten(summary.strip(), 280)


def _build_lens_receipt_excerpt(receipt: LensReceipt) -> str:
    if receipt.diff_summary:
        return _shorten(receipt.diff_summary.strip(), 280)
    if receipt.lens_output:
        return _shorten(receipt.lens_output.strip(), 280)
    if receipt.base_output:
        return _shorten(receipt.base_output.strip(), 280)
    return _shorten(f"Lens receipt {receipt.id}", 280)


def _build_lens_patch_excerpt(patch: LensPatch) -> str:
    status = patch.status.value if hasattr(patch.status, "value") else str(patch.status)
    delta_keys = list((patch.delta or {}).keys())
    if delta_keys:
        preview = ", ".join(delta_keys[:3])
        if len(delta_keys) > 3:
            preview = f"{preview}, +{len(delta_keys) - 3} more"
        return _shorten(
            f"Lens patch {status}. Changed {preview}. Confidence {patch.confidence:.2f}.",
            280,
        )
    return _shorten(
        f"Lens patch {status}. Confidence {patch.confidence:.2f}.",
        280,
    )


def _build_task_execution_excerpt(task: Task) -> str:
    if isinstance(task.result, dict):
        for key in ("summary", "message", "result_summary", "title"):
            value = task.result.get(key)
            if isinstance(value, str) and value.strip():
                return _shorten(value.strip(), 280)
    if task.error:
        return _shorten(task.error.strip(), 280)
    summary = f"{task.pack_id} {task.task_type} status={task.status}"
    return _shorten(summary.strip(), 280)


def _build_execution_trace_excerpt(
    trace_payload: Dict[str, Any],
    *,
    task: Optional[Task] = None,
) -> str:
    output_summary = trace_payload.get("output_summary")
    if isinstance(output_summary, str) and output_summary.strip():
        return _shorten(output_summary.strip(), 280)

    task_description = trace_payload.get("task_description")
    if isinstance(task_description, str) and task_description.strip():
        return _shorten(task_description.strip(), 280)

    agent = trace_payload.get("agent") or trace_payload.get("agent_type")
    if not isinstance(agent, str) or not agent.strip():
        agent = "runtime"
    tool_calls = trace_payload.get("tool_calls")
    files_created = trace_payload.get("files_created")
    files_modified = trace_payload.get("files_modified")
    tool_call_count = len(tool_calls) if isinstance(tool_calls, list) else 0
    file_change_count = 0
    if isinstance(files_created, list):
        file_change_count += len(files_created)
    if isinstance(files_modified, list):
        file_change_count += len(files_modified)
    task_label = ""
    if task is not None:
        task_label = f"{task.pack_id} {task.task_type}".strip()
    summary_parts = [f"{agent} trace"]
    if task_label:
        summary_parts.append(f"for {task_label}")
    summary_parts.append(f"with {tool_call_count} tool calls")
    summary_parts.append(f"and {file_change_count} file changes.")
    return _shorten(" ".join(summary_parts), 280)


def _build_artifact_excerpt(artifact: Artifact) -> str:
    if artifact.summary:
        return _shorten(artifact.summary.strip(), 280)
    if artifact.title:
        return _shorten(artifact.title.strip(), 280)
    summary = f"{artifact.playbook_code} {artifact.artifact_type}"
    return _shorten(summary.strip(), 280)


def _build_stage_result_excerpt(stage_result: Any) -> str:
    preview = getattr(stage_result, "preview", None)
    if isinstance(preview, str) and preview.strip():
        return _shorten(preview.strip(), 280)

    content = getattr(stage_result, "content", None)
    if isinstance(content, dict):
        for key in ("summary", "message", "title", "result_summary"):
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                return _shorten(value.strip(), 280)

    stage_name = getattr(stage_result, "stage_name", "stage")
    result_type = getattr(stage_result, "result_type", "result")
    return _shorten(f"{stage_name} {result_type}", 280)


def _build_intent_log_excerpt(intent_log: IntentLog) -> str:
    final_decision = intent_log.final_decision or {}
    selected_playbook_code = final_decision.get("selected_playbook_code")
    resolution_strategy = final_decision.get("resolution_strategy")
    requires_user_approval = final_decision.get("requires_user_approval")

    summary_parts = []
    if isinstance(selected_playbook_code, str) and selected_playbook_code.strip():
        summary_parts.append(f"Selected {selected_playbook_code.strip()}.")
    if isinstance(resolution_strategy, str) and resolution_strategy.strip():
        summary_parts.append(f"Resolution {resolution_strategy.strip()}.")
    if requires_user_approval is True:
        summary_parts.append("User approval required.")
    if intent_log.user_override:
        summary_parts.append("User override recorded.")
    if summary_parts:
        return _shorten(" ".join(summary_parts), 280)

    raw_input = intent_log.raw_input.strip()
    if raw_input:
        return _shorten(raw_input, 280)
    return _shorten(f"Intent log {intent_log.id}", 280)


def _build_governance_decision_excerpt(decision: Dict[str, Any]) -> str:
    layer = str(decision.get("layer") or "governance").strip()
    approved = decision.get("approved")
    reason = decision.get("reason")
    playbook_code = decision.get("playbook_code")

    summary_parts = [f"{layer.title()} approval={approved}."]
    if isinstance(playbook_code, str) and playbook_code.strip():
        summary_parts.append(f"Playbook {playbook_code.strip()}.")
    if isinstance(reason, str) and reason.strip():
        summary_parts.append(reason.strip())
    return _shorten(" ".join(summary_parts), 280)
