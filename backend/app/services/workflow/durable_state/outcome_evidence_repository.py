"""Indexed durable lookup seam for outcome terminal and enrollment evidence."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from .canonical_json import MAX_INLINE_BYTES, encode


class OutcomeEvidenceRepository:
    """Reads exact signed records without scanning JSON event history."""

    def enrollment_for_terminal(
        self,
        conn,
        *,
        terminal_receipt_id: str,
        workspace_id: str,
    ) -> dict[str, Any] | None:
        rows = list(
            conn.execute(
                text(
                    """
                    SELECT e.workflow_id, e.payload -> 'enrollment' AS enrollment
                    FROM durable_workflow_events AS e
                    JOIN durable_workflow_instances AS i
                      ON i.workflow_id = e.workflow_id
                    WHERE e.event_type = 'iteration_enrollment_accepted'
                      AND e.payload #>> '{enrollment,terminal_receipt_id}'
                          = :terminal_receipt_id
                      AND i.workspace_id = :workspace_id
                      AND i.workflow_kind = 'product_iteration'
                    LIMIT 2
                    """
                ),
                {
                    "terminal_receipt_id": terminal_receipt_id,
                    "workspace_id": workspace_id,
                },
            ).mappings()
        )
        if len(rows) > 1:
            raise RuntimeError("outcome_terminal_has_multiple_enrollments")
        if not rows:
            return None
        return {
            "iteration_id": rows[0]["workflow_id"],
            "enrollment": dict(rows[0]["enrollment"]),
        }

    def task_evidence(
        self,
        conn,
        *,
        terminal_receipt_id: str,
        enrollment_id: str,
        iteration_id: str,
        workspace_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        terminal = (
            conn.execute(
                text(
                    """
                SELECT e.payload #> '{typed_receipt,receipt}' AS receipt
                FROM durable_workflow_events AS e
                JOIN durable_workflow_instances AS i
                  ON i.workflow_id = e.workflow_id
                WHERE e.event_type = 'transition'
                  AND e.payload #>> '{typed_receipt,receipt_type}'
                      = 'execution_terminal_receipt'
                  AND e.payload #>> '{typed_receipt,receipt,receipt_id}'
                      = :terminal_receipt_id
                  AND i.workspace_id = :workspace_id
                LIMIT 1
                """
                ),
                {
                    "terminal_receipt_id": terminal_receipt_id,
                    "workspace_id": workspace_id,
                },
            )
            .mappings()
            .one_or_none()
        )
        enrollment = (
            conn.execute(
                text(
                    """
                SELECT e.payload -> 'enrollment' AS enrollment
                FROM durable_workflow_events AS e
                JOIN durable_workflow_instances AS i
                  ON i.workflow_id = e.workflow_id
                WHERE e.workflow_id = :iteration_id
                  AND e.event_type = 'iteration_enrollment_accepted'
                  AND e.payload #>> '{enrollment,enrollment_id}'
                      = :enrollment_id
                  AND e.payload #>> '{enrollment,terminal_receipt_id}'
                      = :terminal_receipt_id
                  AND i.workspace_id = :workspace_id
                LIMIT 1
                """
                ),
                {
                    "iteration_id": iteration_id,
                    "enrollment_id": enrollment_id,
                    "terminal_receipt_id": terminal_receipt_id,
                    "workspace_id": workspace_id,
                },
            )
            .mappings()
            .one_or_none()
        )
        if terminal is None:
            raise KeyError("outcome_terminal_receipt_not_found")
        if enrollment is None:
            raise KeyError("outcome_iteration_enrollment_not_found")
        return dict(terminal["receipt"]), dict(enrollment["enrollment"])

    def iteration_definition(
        self,
        conn,
        *,
        iteration_id: str,
        workspace_id: str,
    ) -> dict[str, Any]:
        state = conn.execute(
            text(
                """
                SELECT p.state
                FROM durable_workflow_projection_offsets AS p
                JOIN durable_workflow_instances AS i
                  ON i.workflow_id = p.workflow_id
                WHERE p.projection_name = 'current'
                  AND p.workflow_id = :iteration_id
                  AND i.workspace_id = :workspace_id
                  AND i.workflow_kind = 'product_iteration'
                """
            ),
            {
                "iteration_id": iteration_id,
                "workspace_id": workspace_id,
            },
        ).scalar_one_or_none()
        definition = dict(state).get("definition") if isinstance(state, dict) else None
        if not isinstance(definition, dict):
            raise KeyError("outcome_iteration_definition_not_found")
        return definition

    def read_result_ref(
        self,
        conn,
        *,
        result_ref: dict[str, Any],
        workspace_id: str,
    ) -> Any:
        expected_bytes = int(result_ref.get("bytes", -1))
        if not 0 <= expected_bytes <= MAX_INLINE_BYTES:
            raise ValueError("outcome_result_ref_byte_budget_exceeded")
        uri = str(result_ref.get("uri") or "")
        prefix = "artifact://"
        if not uri.startswith(prefix):
            raise ValueError("outcome_result_ref_scheme_not_supported")
        artifact_id = uri[len(prefix) :]
        if not artifact_id or "/" in artifact_id:
            raise ValueError("outcome_result_ref_artifact_id_invalid")
        content = conn.execute(
            text(
                """
                SELECT content
                FROM artifacts
                WHERE id = :artifact_id
                  AND workspace_id = :workspace_id
                """
            ),
            {
                "artifact_id": artifact_id,
                "workspace_id": workspace_id,
            },
        ).scalar_one_or_none()
        if content is None:
            raise KeyError("outcome_result_artifact_not_found")
        payload_bytes = encode(content)
        if len(payload_bytes) != expected_bytes:
            raise ValueError("outcome_result_ref_size_mismatch")
        import hashlib

        if hashlib.sha256(payload_bytes).hexdigest() != result_ref["sha256"]:
            raise ValueError("outcome_result_ref_hash_mismatch")
        return content


__all__ = ("OutcomeEvidenceRepository",)
