"""Connection-bound playbook checkpoint adapter; not wired to live callers."""

from __future__ import annotations

from backend.app.services.workflow.durable_state import DurableWorkflowFacade


class DurableCheckpointAdapter:
    def __init__(self, facade: DurableWorkflowFacade) -> None:
        self._facade = facade

    def append(self, conn, checkpoint: dict) -> dict:
        return self._facade.append_checkpoint(conn, checkpoint)

    def list_after(
        self, conn, workflow_id: str, cursor: int = -1, limit: int = 50
    ) -> list[dict]:
        return self._facade.list_checkpoints(conn, workflow_id, cursor, limit)
