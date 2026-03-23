"""SSE event helpers for workspace execution routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict


def _model_dump_json(value):
    """Serialize model-like objects with json-safe output when available."""
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "__dict__"):
        return {
            key: field_value.isoformat() if isinstance(field_value, datetime) else field_value
            for key, field_value in value.__dict__.items()
        }
    return value if isinstance(value, dict) else {}


class ExecutionStreamEvent:
    """Execution stream event model."""

    @staticmethod
    def execution_update(execution) -> Dict[str, Any]:
        """Create execution_update event."""
        exec_dict = _model_dump_json(execution)
        if "task" in exec_dict and isinstance(exec_dict["task"], dict):
            task_dict = exec_dict.pop("task")
            exec_dict.update({f"task_{key}": value for key, value in task_dict.items()})
        return {"type": "execution_update", "execution": exec_dict}

    @staticmethod
    def step_update(step, current_step_index: int) -> Dict[str, Any]:
        """Create step_update event."""
        return {
            "type": "step_update",
            "step": _model_dump_json(step),
            "current_step_index": current_step_index,
        }

    @staticmethod
    def tool_call_update(tool_call: Any) -> Dict[str, Any]:
        """Create tool_call_update event."""
        return {"type": "tool_call_update", "tool_call": _model_dump_json(tool_call)}

    @staticmethod
    def collaboration_update(collaboration: Dict[str, Any]) -> Dict[str, Any]:
        """Create collaboration_update event."""
        return {"type": "collaboration_update", "collaboration": collaboration}

    @staticmethod
    def stage_result(stage_result: Any) -> Dict[str, Any]:
        """Create stage_result event."""
        return {"type": "stage_result", "stage_result": _model_dump_json(stage_result)}

    @staticmethod
    def execution_completed(execution_id: str, final_status: str) -> Dict[str, Any]:
        """Create execution_completed event."""
        return {
            "type": "execution_completed",
            "execution_id": execution_id,
            "final_status": final_status,
        }

    @staticmethod
    def execution_chat(message) -> Dict[str, Any]:
        """Create execution_chat event."""
        return {"type": "execution_chat", "message": _model_dump_json(message)}
