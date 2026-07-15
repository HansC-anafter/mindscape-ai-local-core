"""Runtime context helpers for DispatchOrchestrator."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.models.phase_attempt import PhaseAttempt
from backend.app.models.task_ir import PhaseIR, PhaseStatus


def should_skip(
    orchestrator: Any,
    phase_id: str,
    phase_map: Dict[str, PhaseIR],
) -> bool:
    """Check if a phase should be skipped due to failed dependencies."""
    if orchestrator.skip_policy == "continue_on_dep_failure":
        return False

    phase = phase_map.get(phase_id)
    if not phase or not phase.depends_on:
        return False

    for dep_id in phase.depends_on:
        dep = phase_map.get(dep_id)
        if dep and dep.status in (PhaseStatus.FAILED, PhaseStatus.SKIPPED):
            strategy = getattr(phase, "rollback_strategy", None) or "skip"
            if strategy == "retry":
                return False
            return True
    return False


def create_attempt(
    orchestrator: Any,
    phase: PhaseIR,
    task_ir_id: str,
) -> PhaseAttempt:
    """Create and register a new PhaseAttempt for a phase."""
    existing = orchestrator._attempts.get(phase.id)
    attempt_number = (existing.attempt_number + 1) if existing else 1

    attempt = PhaseAttempt(
        task_ir_id=task_ir_id,
        phase_id=phase.id,
        workspace_group_snapshot_id=orchestrator._group_execution.snapshot_id,
        attempt_number=attempt_number,
        target_workspace_id=phase.target_workspace_id,
    )
    orchestrator._attempts[phase.id] = attempt
    return attempt


def meeting_command_transport_context(orchestrator: Any) -> Dict[str, Any]:
    """Extract command-ledger correlation from the active MeetingEngine session."""
    metadata = getattr(orchestrator.session, "metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
    request_contract = metadata.get("request_contract")
    if not isinstance(request_contract, dict):
        request_contract = {}

    aol_metadata: Dict[str, Any] = {}
    for candidate in (
        request_contract.get("addressable_object_layer"),
        (request_contract.get("governance_constraints") or {}).get(
            "addressable_object_layer"
        )
        if isinstance(request_contract.get("governance_constraints"), dict)
        else None,
        metadata.get("addressable_object_layer"),
    ):
        if isinstance(candidate, dict) and candidate:
            aol_metadata = dict(candidate)
            break

    command_id = (
        aol_metadata.get("command_id")
        or request_contract.get("meeting_command_id")
        or request_contract.get("command_id")
        or metadata.get("meeting_command_id")
        or metadata.get("command_id")
    )
    if isinstance(command_id, str):
        command_id = command_id.strip()
    else:
        command_id = ""

    context: Dict[str, Any] = {}
    if command_id:
        context["meeting_command_id"] = command_id
        context["command_id"] = command_id
    if aol_metadata:
        context["addressable_object_layer"] = aol_metadata
    return context


def apply_meeting_command_transport_context(
    orchestrator: Any,
    inputs: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply meeting command transport context to dispatch inputs."""
    context = meeting_command_transport_context(orchestrator)
    command_id = context.get("meeting_command_id")
    if command_id:
        inputs.setdefault("meeting_command_id", command_id)
        inputs.setdefault("command_id", command_id)
    aol_metadata = context.get("addressable_object_layer")
    if isinstance(aol_metadata, dict) and aol_metadata:
        inputs.setdefault("addressable_object_layer", aol_metadata)
    return context


async def load_workspace(orchestrator: Any, workspace_id: str) -> Any:
    """Load and cache workspace data for agent dispatch."""
    if not workspace_id:
        return None
    if workspace_id in orchestrator._workspace_cache:
        return orchestrator._workspace_cache[workspace_id]

    from backend.app.services.stores.postgres.workspaces_store import (
        PostgresWorkspacesStore,
    )

    workspace = await PostgresWorkspacesStore().get_workspace(workspace_id)
    orchestrator._workspace_cache[workspace_id] = workspace
    return workspace


def resolve_agent_runtime(*, engine: str, workspace: Any) -> Optional[str]:
    """Resolve the executor runtime requested by the agent engine string."""
    if isinstance(engine, str) and engine.startswith("agent:"):
        requested_runtime = engine.split(":", 1)[1].strip()
        if requested_runtime and requested_runtime != "auto":
            return requested_runtime

    resolved_runtime = getattr(workspace, "resolved_executor_runtime", None)
    if isinstance(resolved_runtime, str) and resolved_runtime.strip():
        return resolved_runtime.strip()
    return None


def build_agent_task(
    *,
    phase: PhaseIR,
    action_item: Dict[str, Any],
    inputs: Dict[str, Any],
) -> str:
    """Build the text task sent to the workspace agent executor."""
    task = inputs.get("user_request")
    if isinstance(task, str) and task.strip():
        return task.strip()

    for candidate in (
        action_item.get("description"),
        phase.description,
        action_item.get("title"),
        phase.name,
    ):
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return "Complete the requested task."


def build_agent_conversation_context(
    *,
    action_item: Dict[str, Any],
    inputs: Dict[str, Any],
    ir_provenance: Dict[str, Any],
) -> str:
    """Build executor conversation context from inputs and phase metadata."""
    sections: List[str] = []

    base_context = inputs.get("context")
    if isinstance(base_context, str) and base_context.strip():
        sections.append(base_context.strip())

    upstream_context = action_item.get("_upstream_context")
    if isinstance(upstream_context, dict) and upstream_context:
        sections.append(
            "[Upstream Context]\n"
            + json.dumps(upstream_context, ensure_ascii=False, sort_keys=True)
        )

    lens_context = action_item.get("_lens_context")
    if isinstance(lens_context, dict) and lens_context:
        sections.append(
            "[Lens Context]\n"
            + json.dumps(lens_context, ensure_ascii=False, sort_keys=True)
        )

    if ir_provenance:
        sections.append(
            "[IR Provenance]\n"
            + json.dumps(ir_provenance, ensure_ascii=False, sort_keys=True)
        )

    return "\n\n".join(section for section in sections if section)


async def publish_activity(orchestrator: Any, event_type: str, data: dict) -> None:
    """Publish event to workspace activity stream."""
    try:
        from backend.app.services.cache.async_redis import publish_meeting_chunk

        ws_id = getattr(orchestrator.session, "workspace_id", None) or ""
        thread_id = (
            getattr(orchestrator.session, "thread_id", None)
            or getattr(orchestrator.session, "id", None)
            or ""
        )
        if ws_id:
            await publish_meeting_chunk(
                ws_id,
                {
                    "type": event_type,
                    **data,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
                thread_id,
            )
    except Exception:
        pass
