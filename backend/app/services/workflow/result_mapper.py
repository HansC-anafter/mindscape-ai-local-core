"""Result projection helpers for workflow execution."""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from backend.app.services.execution_core.clock import utc_now

logger = logging.getLogger(__name__)


def collect_final_outputs(
    output_defs: Dict[str, Any], step_outputs: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:
    """Collect final playbook outputs from step outputs."""
    final_outputs = {}
    for output_name, output_def in output_defs.items():
        source_path = output_def.source
        parts = source_path.split(".")
        if len(parts) >= 3 and parts[0] == "step":
            step_id = parts[1]
            output_key = ".".join(parts[2:])
            if step_id in step_outputs:
                final_outputs[output_name] = step_outputs[step_id].get(output_key)
    return final_outputs


def map_sub_playbook_result_to_step_outputs(
    output_defs: Dict[str, Any],
    sub_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Map sub-playbook final outputs through the parent step output definition."""
    step_output = {}
    for output_name, source_field in output_defs.items():
        step_output[output_name] = sub_result.get(source_field)
    return step_output


def map_tool_result_to_step_outputs(
    *,
    step_id: str,
    output_defs: Dict[str, Any],
    tool_result: Any,
) -> Dict[str, Any]:
    """Map a tool result object to workflow step outputs."""
    step_output: Dict[str, Any] = {}
    for output_name, tool_field in output_defs.items():
        if isinstance(tool_result, dict):
            if not tool_field:
                value = tool_result
                logger.debug(
                    "Step %s output mapping: output_name=%s, using entire tool_result (len=%s)",
                    step_id,
                    output_name,
                    len(tool_result),
                )
            else:
                value = tool_result
                logger.debug(
                    "Step %s output mapping: output_name=%s, tool_field=%s, tool_result_keys=%s",
                    step_id,
                    output_name,
                    tool_field,
                    list(tool_result.keys()),
                )
                for field_part in str(tool_field).split("."):
                    if isinstance(value, dict):
                        value = value.get(field_part)
                        logger.debug(
                            "Step %s output mapping: field_part=%s, value_type=%s",
                            step_id,
                            field_part,
                            type(value).__name__ if value is not None else "None",
                        )
                    else:
                        value = None
                        break
                    if value is None:
                        break

                if value is None:
                    raise ValueError(
                        f"Step {step_id} required output '{output_name}' "
                        f"(field='{tool_field}') not found in tool result"
                    )

                value_preview = (
                    f"{type(value).__name__}(len={len(value)})"
                    if isinstance(value, (list, dict))
                    else str(value)[:100]
                )
                logger.debug(
                    "Step %s output mapping success: %s=%s",
                    step_id,
                    output_name,
                    value_preview,
                )
            step_output[output_name] = value
        else:
            step_output[output_name] = tool_result
    return step_output


def create_step_event(
    *,
    store: Any,
    execution_id: str,
    workspace_id: str,
    profile_id: Optional[str],
    step_id: str,
    step_name: str,
    step_index: int,
    status: str,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
    error: Optional[str] = None,
) -> None:
    """Create a PLAYBOOK_STEP event for step timeline projection."""
    if not store:
        return

    try:
        from backend.app.models.mindscape import EventActor, EventType, MindEvent

        event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=utc_now(),
            actor=EventActor.SYSTEM,
            channel="workflow_orchestrator",
            profile_id=profile_id or "default-user",
            project_id=None,
            workspace_id=workspace_id,
            event_type=EventType.PLAYBOOK_STEP,
            payload={
                "execution_id": execution_id,
                "step_id": step_id,
                "step_name": step_name,
                "step_index": step_index,
                "status": status,
                "started_at": started_at.isoformat() if started_at else None,
                "completed_at": completed_at.isoformat() if completed_at else None,
                "error": error,
            },
            entity_ids=[execution_id, step_id],
            metadata={},
        )

        store.create_event(event, generate_embedding=False)
        logger.debug(
            "Created PLAYBOOK_STEP event for step %s (index %s)",
            step_id,
            step_index,
        )
    except Exception as exc:
        logger.warning("Failed to create PLAYBOOK_STEP event: %s", exc)
