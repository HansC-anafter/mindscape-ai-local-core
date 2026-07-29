"""Stable existing-lane durable delayed-task facade for capability packs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.knowledge_projection.retrievable.canonical_json import (
    canonical_sha256,
)
from backend.app.services.stores.tasks_store import TasksStore


class DurableTimerAppender(Protocol):
    def record_timer(self, conn, **kwargs) -> dict[str, Any]: ...


class InstalledToolSelector(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_code: str = Field(
        pattern=r"^[a-z0-9_]+$",
        max_length=128,
    )
    tool_code: str = Field(
        pattern=r"^[a-z0-9_.-]+$",
        max_length=256,
    )

    @property
    def qualified_tool_name(self) -> str:
        return f"{self.capability_code}.{self.tool_code}"


class DurableScheduledTaskCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    workflow_id: str = Field(min_length=1, max_length=256)
    expected_sequence: int = Field(ge=0)
    timer_id: str = Field(min_length=1, max_length=256)
    deadline: datetime
    workspace_id: str = Field(min_length=1, max_length=128)
    selector: InstalledToolSelector
    payload: dict[str, Any]
    payload_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    actor: dict[str, Any]
    idempotency_key: str = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def validate_deadline_and_digest(self):
        if self.deadline.tzinfo is None:
            raise ValueError("durable_scheduled_task_deadline_timezone_required")
        if canonical_sha256(self.payload) != self.payload_digest:
            raise ValueError("durable_scheduled_task_payload_digest_mismatch")
        if not str(self.actor.get("actor_id") or "").strip():
            raise ValueError("durable_scheduled_task_actor_required")
        return self


class DurableScheduledTaskReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: str
    workflow_id: str
    timer_id: str
    task_id: str
    deadline: datetime
    qualified_tool_name: str
    payload_digest: str
    task_created: bool
    timer_sequence: int
    receipt_sha256: str = ""

    @model_validator(mode="after")
    def add_receipt_hash(self):
        if self.receipt_sha256:
            return self
        object.__setattr__(
            self,
            "receipt_sha256",
            canonical_sha256(
                self.model_dump(
                    mode="json",
                    exclude={"receipt_sha256"},
                )
            ),
        )
        return self


class DurableScheduledTaskFacade:
    """Atomically append one timer and one future task on existing lanes."""

    def __init__(
        self,
        *,
        durable_timer: DurableTimerAppender,
        tasks_store: TasksStore | None = None,
        tool_registry: Any | None = None,
    ) -> None:
        self._durable_timer = durable_timer
        self._tasks_store = tasks_store or TasksStore()
        if tool_registry is None:
            from backend.app.services.capability_registry import get_registry

            tool_registry = get_registry()
        self._tool_registry = tool_registry

    def schedule_next(
        self,
        command: DurableScheduledTaskCommand,
    ) -> DurableScheduledTaskReceipt:
        tool_name = command.selector.qualified_tool_name
        if self._tool_registry.get_tool(tool_name) is None:
            raise ValueError(
                "durable_scheduled_task_installed_tool_required"
            )
        task_id = "scheduled_" + canonical_sha256(
            {
                "workflow_id": command.workflow_id,
                "timer_id": command.timer_id,
                "tool_name": tool_name,
                "payload_digest": command.payload_digest,
            }
        )[:48]
        deadline = command.deadline.astimezone(timezone.utc)
        task = Task(
            id=task_id,
            workspace_id=command.workspace_id,
            message_id=f"durable-timer:{command.timer_id}",
            execution_id=task_id,
            pack_id=tool_name,
            task_type="tool_execution",
            status=TaskStatus.PENDING,
            params=dict(command.payload),
            execution_context={
                "tool_name": tool_name,
                "capability_code": command.selector.capability_code,
                "root_execution_id": task_id,
                "trigger_source": "durable_timer",
                "durable_workflow_id": command.workflow_id,
                "durable_timer_id": command.timer_id,
                "payload_digest": command.payload_digest,
                "single_flight_key": (
                    f"{command.workflow_id}:{command.timer_id}"
                ),
            },
            next_eligible_at=deadline,
        )
        self._tasks_store.prepare_task_for_create(task)
        with self._tasks_store.transaction() as conn:
            timer_event = self._durable_timer.record_timer(
                conn,
                workflow_id=command.workflow_id,
                expected_sequence=command.expected_sequence,
                timer={
                    "timer_id": command.timer_id,
                    "deadline": deadline.isoformat(),
                    "selector": tool_name,
                    "payload_digest": command.payload_digest,
                },
                idempotency_key=command.idempotency_key,
                actor=dict(command.actor),
            )
            task, task_created = self._tasks_store.create_task_with_conn(
                conn,
                task,
                already_prepared=True,
                idempotent=True,
            )
        self._tasks_store.finalize_task_create_after_commit(
            task,
            created=task_created,
        )
        timer_sequence = int(
            timer_event.get("sequence")
            or timer_event.get("current_sequence")
            or command.expected_sequence + 1
        )
        return DurableScheduledTaskReceipt(
            state="scheduled" if task_created else "reused",
            workflow_id=command.workflow_id,
            timer_id=command.timer_id,
            task_id=task.id,
            deadline=task.next_eligible_at,
            qualified_tool_name=tool_name,
            payload_digest=command.payload_digest,
            task_created=task_created,
            timer_sequence=timer_sequence,
        )


__all__ = [
    "DurableScheduledTaskCommand",
    "DurableScheduledTaskFacade",
    "DurableScheduledTaskReceipt",
    "DurableTimerAppender",
    "InstalledToolSelector",
]
