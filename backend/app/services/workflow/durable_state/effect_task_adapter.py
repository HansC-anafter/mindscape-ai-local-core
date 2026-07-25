"""Atomic effect-intent and existing-task-lane seam."""

from __future__ import annotations

from typing import Callable

from .facade import DurableWorkflowFacade


class DurableEffectTaskAdapter:
    """Uses an injected caller-owned-connection task creator; never a queue."""

    def __init__(
        self,
        facade: DurableWorkflowFacade,
        *,
        create_task_with_conn: Callable,
    ) -> None:
        self._facade = facade
        self._create_task_with_conn = create_task_with_conn

    def prepare(self, conn, *, prepared_receipt: dict, task) -> tuple[dict, object]:
        receipt = self._facade.record_side_effect(conn, prepared_receipt)
        created_task = self._create_task_with_conn(conn, task)
        return receipt, created_task

    def record_owner_terminal(self, conn, receipt: dict) -> dict:
        return self._facade.record_side_effect(conn, receipt)
