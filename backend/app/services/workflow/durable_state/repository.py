"""SQLAlchemy connection-bound persistence for the durable workflow ledger."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text


def _json(value: Any) -> str:
    return json.dumps(value, allow_nan=False, separators=(",", ":"), sort_keys=True)


class DurableWorkflowRepository:
    """Repository that never creates or commits a connection or transaction."""

    def insert_instance(self, conn, record: dict[str, Any]) -> None:
        conn.execute(
            text(
                """
                INSERT INTO durable_workflow_instances (
                    workflow_id, root_workflow_id, segment_id, segment_number,
                    predecessor_segment_id, predecessor_terminal_hash,
                    workflow_kind, workspace_id, execution_id, psc_ids,
                    semantic_identity, semantic_identity_hash, current_state,
                    workflow_definition_version, reducer_version,
                    effect_adapter_registry_version, runtime_build_id,
                    replay_compatibility_class
                ) VALUES (
                    :workflow_id, :root_workflow_id, :segment_id, :segment_number,
                    :predecessor_segment_id, :predecessor_terminal_hash,
                    :workflow_kind, :workspace_id, :execution_id,
                    CAST(:psc_ids AS JSONB), CAST(:semantic_identity AS JSONB),
                    :semantic_identity_hash, :current_state,
                    :workflow_definition_version, :reducer_version,
                    :effect_adapter_registry_version, :runtime_build_id,
                    :replay_compatibility_class
                )
                """
            ),
            {
                **record,
                "psc_ids": _json(record["psc_ids"]),
                "semantic_identity": _json(record["semantic_identity"]),
            },
        )

    def lock_instance(self, conn, workflow_id: str) -> dict[str, Any]:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM durable_workflow_instances
                WHERE workflow_id = :workflow_id
                FOR UPDATE
                """
            ),
            {"workflow_id": workflow_id},
        ).mappings().one_or_none()
        if row is None:
            raise KeyError(f"durable workflow {workflow_id!r} does not exist")
        return dict(row)

    def read_instance(self, conn, workflow_id: str) -> dict[str, Any]:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM durable_workflow_instances
                WHERE workflow_id = :workflow_id
                """
            ),
            {"workflow_id": workflow_id},
        ).mappings().one_or_none()
        if row is None:
            raise KeyError(f"durable workflow {workflow_id!r} does not exist")
        return dict(row)

    def find_idempotent_event(
        self, conn, workflow_id: str, idempotency_key: str
    ) -> dict[str, Any] | None:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM durable_workflow_events
                WHERE workflow_id = :workflow_id
                  AND idempotency_key = :idempotency_key
                """
            ),
            {"workflow_id": workflow_id, "idempotency_key": idempotency_key},
        ).mappings().one_or_none()
        return dict(row) if row else None

    def insert_event(self, conn, event: dict[str, Any]) -> None:
        conn.execute(
            text(
                """
                INSERT INTO durable_workflow_events (
                    event_id, workflow_id, segment_id, sequence, event_type,
                    idempotency_key, timer_id, external_message_id, actor,
                    payload, payload_sha256, previous_event_hash, event_hash,
                    canonical_bytes, occurred_at, key_id, signature
                ) VALUES (
                    :event_id, :workflow_id, :segment_id, :sequence, :event_type,
                    :idempotency_key, :timer_id, :external_message_id,
                    CAST(:actor AS JSONB), CAST(:payload AS JSONB),
                    :payload_sha256, :previous_event_hash, :event_hash,
                    :canonical_bytes, :occurred_at, :key_id, :signature
                )
                """
            ),
            {
                **event,
                "actor": _json(event["actor"]),
                "payload": _json(event["payload"]),
            },
        )

    def advance_instance(
        self,
        conn,
        *,
        workflow_id: str,
        expected_sequence: int,
        event_hash: str,
        event_bytes: int,
        current_state: str,
        terminal: bool,
        next_durable_deadline,
        cancellation_state: str | None,
    ) -> None:
        result = conn.execute(
            text(
                """
                UPDATE durable_workflow_instances
                SET current_sequence = current_sequence + 1,
                    current_event_hash = :event_hash,
                    current_state = :current_state,
                    terminal = :terminal,
                    event_count = event_count + 1,
                    canonical_event_bytes = canonical_event_bytes + :event_bytes,
                    next_durable_deadline = :next_durable_deadline,
                    cancellation_state = :cancellation_state,
                    updated_at = NOW()
                WHERE workflow_id = :workflow_id
                  AND current_sequence = :expected_sequence
                """
            ),
            {
                "workflow_id": workflow_id,
                "expected_sequence": expected_sequence,
                "event_hash": event_hash,
                "event_bytes": event_bytes,
                "current_state": current_state,
                "terminal": terminal,
                "next_durable_deadline": next_durable_deadline,
                "cancellation_state": cancellation_state,
            },
        )
        if result.rowcount != 1:
            raise RuntimeError("durable workflow sequence compare-and-swap failed")

    def upsert_projection(
        self,
        conn,
        *,
        workflow_id: str,
        sequence: int,
        reducer_version: str,
        state: dict[str, Any],
        state_hash: str,
    ) -> None:
        conn.execute(
            text(
                """
                INSERT INTO durable_workflow_projection_offsets (
                    projection_name, workflow_id, last_sequence,
                    reducer_version, state_hash, state, updated_at
                ) VALUES (
                    'current', :workflow_id, :sequence, :reducer_version,
                    :state_hash, CAST(:state AS JSONB), NOW()
                )
                ON CONFLICT (projection_name, workflow_id) DO UPDATE
                SET last_sequence = EXCLUDED.last_sequence,
                    reducer_version = EXCLUDED.reducer_version,
                    state_hash = EXCLUDED.state_hash,
                    state = EXCLUDED.state,
                    updated_at = EXCLUDED.updated_at
                WHERE durable_workflow_projection_offsets.last_sequence
                    = EXCLUDED.last_sequence - 1
                """
            ),
            {
                "workflow_id": workflow_id,
                "sequence": sequence,
                "reducer_version": reducer_version,
                "state_hash": state_hash,
                "state": _json(state),
            },
        )

    def read_events_after(
        self, conn, workflow_id: str, cursor: int, limit: int
    ) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in conn.execute(
                text(
                    """
                    SELECT *
                    FROM durable_workflow_events
                    WHERE workflow_id = :workflow_id AND sequence > :cursor
                    ORDER BY sequence
                    LIMIT :limit
                    """
                ),
                {"workflow_id": workflow_id, "cursor": cursor, "limit": limit},
            ).mappings()
        ]
