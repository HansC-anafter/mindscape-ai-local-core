"""Existing-lane timer, message, and cancellation facade adapter."""

from __future__ import annotations

from .facade import DurableWorkflowFacade


class DurableControlAdapter:
    def __init__(self, facade: DurableWorkflowFacade) -> None:
        self._facade = facade

    def record_timer(self, conn, **kwargs) -> dict:
        return self._facade.record_timer(conn, **kwargs)

    def record_external_message(self, conn, **kwargs) -> dict:
        return self._facade.record_external_message(conn, **kwargs)

    def request_cancellation(self, conn, **kwargs) -> dict:
        return self._facade.request_cancellation(conn, **kwargs)
