from .base import *


def build_dispatch_payload(
    request: RuntimeExecRequest,
    execution_id: str,
    agent_id: str,
) -> Dict[str, Any]:
    """
    Build a transport-agnostic dispatch payload from a RuntimeExecRequest.

    This is the unified contract shared across all polling-based runtimes.
    """
    # Extract conversation context and thread_id from agent_config
    # These are injected by chat_orchestrator_service when routing to agent
    agent_cfg = request.agent_config or {}
    raw_inputs = agent_cfg.get("inputs")
    inputs = dict(raw_inputs) if isinstance(raw_inputs, dict) else {}
    deliverable_targets = inputs.get("deliverable_targets")
    if not isinstance(deliverable_targets, list):
        deliverable_targets = []
    aol_metadata = {}
    for candidate in (
        agent_cfg.get("addressable_object_layer"),
        inputs.get("addressable_object_layer"),
        (inputs.get("ir_provenance") or {}).get("addressable_object_layer")
        if isinstance(inputs.get("ir_provenance"), dict)
        else None,
    ):
        if isinstance(candidate, dict) and candidate:
            aol_metadata = dict(candidate)
            break
    meeting_command_id = (
        agent_cfg.get("meeting_command_id")
        or agent_cfg.get("command_id")
        or inputs.get("meeting_command_id")
        or inputs.get("command_id")
        or aol_metadata.get("command_id")
    )
    if isinstance(meeting_command_id, str):
        meeting_command_id = meeting_command_id.strip()
    else:
        meeting_command_id = ""

    payload = {
        "execution_id": execution_id,
        "workspace_id": request.workspace_id or "",
        "agent_id": agent_id,
        "task": request.task,
        "allowed_tools": request.allowed_tools,
        "max_duration": request.max_duration_seconds,
        "model": agent_cfg.get("model"),  # per-agent model hint (P1.5)
        "context": {
            "project_id": request.project_id,
            "intent_id": request.intent_id,
            "lens_id": request.lens_id,
            "auth_workspace_id": request.auth_workspace_id or request.workspace_id,
            "source_workspace_id": request.source_workspace_id or request.workspace_id,
            "sandbox_path": request.sandbox_path,
            "conversation_context": agent_cfg.get("conversation_context", ""),
            "thread_id": agent_cfg.get("thread_id", ""),
            "meeting_session_id": agent_cfg.get("meeting_session_id", ""),
            "meeting_command_id": meeting_command_id,
            "uploaded_files": agent_cfg.get("uploaded_files", []),
            "recommended_pack_codes": agent_cfg.get("recommended_pack_codes", []),
            "file_hint": agent_cfg.get("file_hint", ""),
            "control_action": agent_cfg.get("control_action", ""),
            "inputs": inputs,
        },
        "metadata": {
            "inputs": inputs,
        },
        "issued_at": datetime.now(timezone.utc).isoformat(),
    }

    deliverable_path = inputs.get("deliverable_path")
    if isinstance(deliverable_path, str) and deliverable_path.strip():
        cleaned_path = deliverable_path.strip()
        payload["deliverable_path"] = cleaned_path
        payload["metadata"]["deliverable_path"] = cleaned_path

    deliverable_name = inputs.get("deliverable_name")
    if isinstance(deliverable_name, str) and deliverable_name.strip():
        cleaned_name = deliverable_name.strip()
        payload["deliverable_name"] = cleaned_name
        payload["metadata"]["deliverable_name"] = cleaned_name

    if deliverable_targets:
        payload["deliverable_targets"] = deliverable_targets
        payload["metadata"]["deliverable_targets"] = deliverable_targets

    meeting_session_id = agent_cfg.get("meeting_session_id") or inputs.get(
        "meeting_session_id"
    )
    if isinstance(meeting_session_id, str) and meeting_session_id.strip():
        cleaned_session_id = meeting_session_id.strip()
        payload["meeting_session_id"] = cleaned_session_id
        payload["context"]["meeting_session_id"] = cleaned_session_id
        payload["metadata"]["meeting_session_id"] = cleaned_session_id

    if meeting_command_id:
        payload["meeting_command_id"] = meeting_command_id
        payload["context"]["meeting_command_id"] = meeting_command_id
        payload["metadata"]["meeting_command_id"] = meeting_command_id
        payload["metadata"]["command_id"] = meeting_command_id
    if aol_metadata:
        payload["context"]["addressable_object_layer"] = aol_metadata
        payload["metadata"]["addressable_object_layer"] = aol_metadata

    return payload
