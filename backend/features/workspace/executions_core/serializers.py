"""Serialization helpers for workspace execution routes."""

from __future__ import annotations

from datetime import datetime

from backend.app.models.workspace import ExecutionSession


def _to_isoformat(value):
    """Convert datetimes to ISO strings and pass through other values."""
    return value.isoformat() if isinstance(value, datetime) else value


def serialize_tool_call(tool_call):
    """Serialize a tool-call record to a JSON-compatible dictionary."""
    if hasattr(tool_call, "model_dump"):
        return tool_call.model_dump()
    if hasattr(tool_call, "__dict__"):
        return {
            key: _to_isoformat(value)
            for key, value in tool_call.__dict__.items()
        }
    try:
        return dict(tool_call)
    except (TypeError, ValueError):
        return vars(tool_call) if hasattr(tool_call, "__dict__") else {}


def serialize_stage_result(stage_result):
    """Serialize a stage-result record to a JSON-compatible dictionary."""
    if hasattr(stage_result, "model_dump"):
        return stage_result.model_dump()
    if hasattr(stage_result, "__dict__"):
        return {
            key: _to_isoformat(value)
            for key, value in stage_result.__dict__.items()
        }
    try:
        return dict(stage_result)
    except (TypeError, ValueError):
        return vars(stage_result) if hasattr(stage_result, "__dict__") else {}


def serialize_execution_session(task, execution_factory=ExecutionSession.from_task):
    """Build the execution session payload returned by list/get routes."""
    execution = execution_factory(task)
    execution_dict = (
        execution.model_dump()
        if hasattr(execution, "model_dump")
        else execution
    )
    if isinstance(execution_dict, dict):
        execution_dict["status"] = task.status.value
        execution_dict["created_at"] = (
            task.created_at.isoformat() if task.created_at else None
        )
        execution_dict["started_at"] = (
            task.started_at.isoformat() if task.started_at else None
        )
        execution_dict["completed_at"] = (
            task.completed_at.isoformat() if task.completed_at else None
        )
        execution_dict["storyline_tags"] = task.storyline_tags or []
        execution_dict["execution_context"] = task.execution_context or {}
    return execution_dict


def serialize_execution_chat_message(message):
    """Serialize an execution-chat message view model."""
    if hasattr(message, "model_dump"):
        return message.model_dump(mode="json")
    return message if isinstance(message, dict) else {}
