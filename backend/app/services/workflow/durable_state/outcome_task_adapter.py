"""TasksStore adapter for one neutral product outcome evaluation intent."""

from __future__ import annotations

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.stores.tasks_store import TasksStore

from .outcome_task_admission import build_outcome_task_admission
from .signature import Ed25519Signer


class OutcomeTaskAdapter:
    """Converts the neutral intent into the existing task model and lane."""

    def __init__(
        self,
        *,
        tasks_store: TasksStore,
        admission_signer: Ed25519Signer,
    ) -> None:
        self.tasks_store = tasks_store
        self._admission_signer = admission_signer

    def create_with_conn(
        self,
        conn,
        task_intent: dict,
        *,
        idempotency_key: str,
    ) -> tuple[Task, bool]:
        if task_intent.get("authorized_lane") != "runner:existing":
            raise ValueError("outcome_task_authorized_lane_mismatch")
        params = dict(task_intent["params"])
        task_id = str(task_intent["task_id"])
        workspace_id = str(task_intent["workspace_id"])
        admission = build_outcome_task_admission(
            self._admission_signer,
            task_id=task_id,
            workspace_id=workspace_id,
            terminal_receipt_id=params["terminal_receipt_id"],
            enrollment_id=params["enrollment_id"],
            iteration_id=params["iteration_id"],
            descriptor_sha256=params["descriptor_sha256"],
            task_params=params,
        )
        task = Task(
            id=task_id,
            workspace_id=workspace_id,
            message_id=params["terminal_receipt_id"],
            execution_id=task_id,
            pack_id=str(task_intent["capability_code"]),
            task_type="product_outcome_evaluation",
            status=TaskStatus.PENDING,
            params=params,
            execution_context={
                "status": "queued",
                "inputs": params,
                "product_outcome_evaluation_admission": admission,
            },
        )
        return self.tasks_store.create_task_with_conn(
            conn,
            task,
            idempotent=True,
        )

    def finalize_after_commit(
        self,
        created_task: tuple[Task, bool],
    ) -> Task:
        task, created = created_task
        return self.tasks_store.finalize_task_create_after_commit(
            task,
            created=created,
        )


__all__ = ("OutcomeTaskAdapter",)
