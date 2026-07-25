"""Control-plane methods inherited by the single durable facade."""

from __future__ import annotations

from .approvals import (
    _consume_approval,
    _decide_approval,
    _request_approval,
)
from .checkpoints import _append_checkpoint, _list_checkpoints
from .side_effects import _record_side_effect
from .terminal_receipts import _append_execution_terminal


class DurableControlPlaneMixin:
    def append_checkpoint(self, conn, checkpoint: dict) -> dict:
        return _append_checkpoint(conn, self._signer, checkpoint)

    def list_checkpoints(
        self, conn, workflow_id: str, cursor: int = -1, limit: int = 50
    ) -> list[dict]:
        return _list_checkpoints(conn, workflow_id, cursor, limit)

    def request_approval(self, conn, request: dict) -> dict:
        return _request_approval(conn, self._signer, request)

    def decide_approval(self, conn, **kwargs) -> dict:
        return _decide_approval(conn, self._signer, **kwargs)

    def consume_approval(self, conn, **kwargs) -> dict:
        return _consume_approval(conn, self._signer, **kwargs)

    def record_side_effect(self, conn, receipt: dict) -> dict:
        return _record_side_effect(conn, self._signer, receipt)

    def append_execution_terminal(self, conn, **kwargs) -> dict:
        return _append_execution_terminal(self, conn, **kwargs)
