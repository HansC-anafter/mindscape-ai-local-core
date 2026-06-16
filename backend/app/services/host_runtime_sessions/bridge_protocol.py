"""Host Runtime Session bridge protocol helpers."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


MAX_EVENT_TEXT_CHARS = 10_000
MAX_EVENT_LIST_ITEMS = 40


@dataclass(frozen=True)
class HostRuntimeTurnContext:
    workspace_id: str
    session_id: str
    turn_id: str
    execution_id: str
    runtime_surface: str
    runtime_id: str
    prompt: str
    envelope: dict[str, Any]

    @classmethod
    def from_turn_start(cls, message: dict[str, Any]) -> "HostRuntimeTurnContext":
        envelope = message.get("envelope") if isinstance(message.get("envelope"), dict) else {}
        return cls(
            workspace_id=str(message.get("workspace_id") or envelope.get("workspace_id") or ""),
            session_id=str(message.get("session_id") or envelope.get("session_id") or ""),
            turn_id=str(message.get("turn_id") or envelope.get("turn_id") or ""),
            execution_id=str(envelope.get("execution_id") or ""),
            runtime_surface=str(message.get("runtime_surface") or envelope.get("runtime_surface") or "codex_cli"),
            runtime_id=str(message.get("runtime_id") or envelope.get("runtime_id") or "codex_cli"),
            prompt=str(message.get("prompt") or ""),
            envelope=dict(envelope),
        )


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def monotonic_started_at() -> float:
    return time.monotonic()


def elapsed_seconds(started_at: float) -> float:
    return round(max(0.0, time.monotonic() - started_at), 3)


def clip_event_text(value: Any, *, limit: int = MAX_EVENT_TEXT_CHARS) -> tuple[str, bool]:
    text = str(value or "")
    if len(text) <= limit:
        return text, False
    half = max(1, limit // 2)
    clipped = (
        text[:half]
        + f"\n\n[... clipped {len(text) - (half * 2)} characters for host runtime event budget ...]\n\n"
        + text[-half:]
    )
    return clipped, True


def compact_json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return str(value)


def clipped_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return value[:MAX_EVENT_LIST_ITEMS]


def build_executor_dispatch(
    context: HostRuntimeTurnContext,
    *,
    max_duration: int = 600,
    model: str = "",
) -> dict[str, Any]:
    metadata = context.envelope.get("metadata") if isinstance(context.envelope.get("metadata"), dict) else {}
    context_payload = {
        "conversation_context": compact_json(
            {
                "intent_ref": context.envelope.get("intent_ref") or {},
                "lens_ref": context.envelope.get("lens_ref") or {},
                "policy_ref": context.envelope.get("policy_ref") or {},
                "context_ref": context.envelope.get("context_ref") or {},
                "artifact_ref": context.envelope.get("artifact_ref") or {},
                "governance_trace_ref": context.envelope.get("governance_trace_ref"),
            }
        ),
        "auth_workspace_id": str(metadata.get("auth_workspace_id") or ""),
        "source_workspace_id": str(metadata.get("source_workspace_id") or context.workspace_id),
        "thread_id": str(metadata.get("thread_id") or ""),
        "sandbox_path": str(metadata.get("sandbox_path") or ""),
        "inputs": {
            "host_runtime_session_id": context.session_id,
            "host_runtime_turn_id": context.turn_id,
            "host_runtime_envelope": context.envelope,
            "runtime_surface": context.runtime_surface,
            "runtime_id": context.runtime_id,
        },
    }
    return {
        "execution_id": context.execution_id,
        "workspace_id": context.workspace_id,
        "task": context.prompt,
        "allowed_tools": [],
        "max_duration": int(metadata.get("max_duration") or max_duration),
        "model": str(metadata.get("model") or model or ""),
        "issued_at": utc_iso(),
        "context": context_payload,
    }


def build_bridge_event_message(
    context: HostRuntimeTurnContext,
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    item_id: str | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "type": event_type,
        "payload": payload or {},
    }
    if item_id:
        event["item_id"] = item_id
    return {
        "type": "host_runtime.event",
        "workspace_id": context.workspace_id,
        "session_id": context.session_id,
        "turn_id": context.turn_id,
        "event": event,
    }


def build_completion_event_messages(
    context: HostRuntimeTurnContext,
    result: dict[str, Any],
    *,
    duration_seconds: float,
) -> list[dict[str, Any]]:
    status = str(result.get("status") or "completed")
    output, output_truncated = clip_event_text(result.get("output") or "")
    error, error_truncated = clip_event_text(result.get("error") or "", limit=4000)
    files_modified = clipped_list(result.get("files_modified"))
    files_created = clipped_list(result.get("files_created"))
    attachments = clipped_list(result.get("attachments"))
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}

    common = {
        "status": status,
        "duration_seconds": duration_seconds,
        "files_modified": files_modified,
        "files_created": files_created,
        "attachments": attachments,
        "metadata": metadata,
    }
    events: list[dict[str, Any]] = []

    if status == "completed":
        events.append(
            build_bridge_event_message(
                context,
                "assistant.message.completed",
                {
                    **common,
                    "content": output,
                    "content_truncated": output_truncated,
                },
                item_id=f"assistant_{context.turn_id}",
            )
        )
        if files_modified or files_created:
            events.append(
                build_bridge_event_message(
                    context,
                    "file.changed",
                    {
                        "files_modified": files_modified,
                        "files_created": files_created,
                    },
                    item_id=f"files_{context.turn_id}",
                )
            )
        if attachments:
            events.append(
                build_bridge_event_message(
                    context,
                    "artifact.provenance.recorded",
                    {
                        "artifact_ref": {
                            "kind": "host_runtime_cli_attachments",
                            "attachments": attachments,
                        }
                    },
                    item_id=f"artifact_{context.turn_id}",
                )
            )
        events.append(
            build_bridge_event_message(
                context,
                "turn.completed",
                {
                    **common,
                    "output_preview": output[:1000],
                    "output_truncated": output_truncated,
                },
            )
        )
        return events

    events.append(
        build_bridge_event_message(
            context,
            "turn.failed",
            {
                **common,
                "error": error,
                "error_truncated": error_truncated,
                "output_preview": output[:1000],
                "output_truncated": output_truncated,
            },
        )
    )
    return events
