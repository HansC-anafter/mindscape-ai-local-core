"""Durable approval delivery seam without a worker, timer, or polling loop."""

from __future__ import annotations

from backend.app.services.workflow.durable_state import DurableWorkflowFacade


class DurableApprovalAdapter:
    def __init__(self, facade: DurableWorkflowFacade) -> None:
        self._facade = facade

    def request(self, conn, request: dict) -> dict:
        return self._facade.request_approval(conn, request)

    def decide(self, conn, **kwargs) -> dict:
        signed = self._facade.decide_approval(conn, **kwargs)
        return {
            "type": "approval.resolve",
            "approval_id": signed["approval_id"],
            "action_hash": signed["action_hash"],
            "resume_payload_hash": signed["resume_payload_hash"],
            "decision": signed["decision"],
            "decision_receipt": signed,
        }

    def accept_delivery(self, conn, **kwargs) -> dict:
        return self._facade.consume_approval(conn, **kwargs)
