"""Disabled-by-default run-harness seam for the durable workflow facade."""

from __future__ import annotations

from typing import Callable

from backend.app.services.workflow.durable_state import DurableWorkflowFacade


class DurableRunHarnessAdapter:
    """Connection-bound adapter; no legacy ledger or best-effort fallback."""

    def __init__(
        self,
        facade: DurableWorkflowFacade,
        *,
        attestation_verifier: Callable[[dict], dict],
    ) -> None:
        self._facade = facade
        self._attestation_verifier = attestation_verifier

    def admit_execution(
        self,
        conn,
        *,
        identity: dict,
        development_attestation: dict,
    ) -> dict:
        verified = self._attestation_verifier(development_attestation)
        expected = {
            "development_attestation_id": verified["attestation_id"],
            "development_attestation_sha256": verified["sha256"],
        }
        for field_name, value in expected.items():
            if identity.get(field_name) != value:
                raise ValueError(
                    f"execution identity {field_name} does not match attestation"
                )
        return self._facade.open_workflow(conn, identity)

    def record_started(
        self,
        conn,
        *,
        workflow_id: str,
        expected_sequence: int,
        actor: dict,
    ) -> dict:
        return self._facade.append_transition(
            conn,
            workflow_id=workflow_id,
            expected_sequence=expected_sequence,
            target_state="running",
            idempotency_key=f"{workflow_id}:started",
            actor=actor,
        )

    def record_terminal(self, conn, **kwargs) -> dict:
        return self._facade.append_execution_terminal(conn, **kwargs)
