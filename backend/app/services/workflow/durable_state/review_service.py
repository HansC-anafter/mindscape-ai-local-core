"""Bounded review reads for an unmounted Phase 04 route seam."""

from __future__ import annotations

from typing import Callable

from sqlalchemy import text

from .replay import compare_results, reduce_as_of

MAX_PAGE = 50


class DurableWorkflowReviewService:
    def __init__(self, *, reducers: dict[str, Callable]) -> None:
        self._reducers = reducers

    def execution_summary(
        self, conn, *, workspace_id: str, execution_id: str
    ) -> dict:
        row = conn.execute(
            text(
                """
                SELECT i.*,
                  (SELECT COUNT(*) FROM durable_workflow_checkpoints c
                   WHERE c.workflow_id = i.workflow_id) AS checkpoint_count,
                  (SELECT COUNT(*) FROM durable_workflow_approval_requests a
                   WHERE a.workflow_id = i.workflow_id
                     AND a.expires_at > NOW()
                     AND NOT EXISTS (
                       SELECT 1
                       FROM durable_workflow_approval_consumptions ac
                       WHERE ac.approval_id = a.approval_id
                     )
                     AND NOT EXISTS (
                       SELECT 1
                       FROM durable_workflow_approval_decisions ad
                       WHERE ad.approval_id = a.approval_id
                         AND ad.decision IN ('rejected', 'expired', 'revoked')
                     )) AS open_approval_count,
                  (SELECT COUNT(*) FROM durable_workflow_side_effect_receipts s
                   WHERE s.workflow_id = i.workflow_id) AS side_effect_count,
                  (SELECT jsonb_build_object(
                     'manifest_id',
                       e.payload->'typed_receipt'->'receipt'->>'manifest_id',
                     'evidence_class',
                       e.payload->'typed_receipt'->'receipt'->>'evidence_class',
                     'lifecycle_action',
                       e.payload->'typed_receipt'->'receipt'->>'lifecycle_action',
                     'reconciliation_state',
                       e.payload->'typed_receipt'->'receipt'
                         ->>'reconciliation_state')
                   FROM durable_workflow_events e
                   WHERE e.workflow_id = i.workflow_id
                     AND e.payload->'typed_receipt'->>'receipt_type'
                       = 'evidence_lifecycle_manifest'
                   ORDER BY e.sequence DESC
                   LIMIT 1) AS evidence_lifecycle
                FROM durable_workflow_instances i
                WHERE i.workspace_id = :workspace_id
                  AND i.execution_id = :execution_id
                ORDER BY i.created_at DESC
                LIMIT 1
                """
            ),
            {"workspace_id": workspace_id, "execution_id": execution_id},
        ).mappings().one_or_none()
        if row is None:
            raise KeyError("durable execution was not found in workspace")
        identity = row["semantic_identity"]
        return {
            "workflow_id": row["workflow_id"],
            "root_workflow_id": row["root_workflow_id"],
            "segment_id": row["segment_id"],
            "segment_number": row["segment_number"],
            "current_sequence": row["current_sequence"],
            "current_event_hash": row["current_event_hash"],
            "current_state": row["current_state"],
            "terminal": row["terminal"],
            "next_durable_deadline": row["next_durable_deadline"],
            "cancellation_state": row["cancellation_state"],
            "workflow_definition_version": row["workflow_definition_version"],
            "reducer_version": row["reducer_version"],
            "effect_adapter_registry_version": row[
                "effect_adapter_registry_version"
            ],
            "runtime_build_id": row["runtime_build_id"],
            "development_attestation_id": identity[
                "development_attestation_id"
            ],
            "development_attestation_sha256": identity[
                "development_attestation_sha256"
            ],
            "consumer_compatibility_class": identity[
                "consumer_compatibility_class"
            ],
            "configuration_fingerprint": identity[
                "configuration_fingerprint"
            ],
            "environment_fingerprint": identity["environment_fingerprint"],
            "data_fingerprint": identity["data_fingerprint"],
            "evidence_lifecycle": row["evidence_lifecycle"],
            "checkpoint_count": row["checkpoint_count"],
            "open_approval_count": row["open_approval_count"],
            "side_effect_count": row["side_effect_count"],
        }

    def events_after(
        self,
        conn,
        *,
        workspace_id: str,
        workflow_id: str,
        cursor: int,
        limit: int,
    ) -> list[dict]:
        self._require_page(limit)
        self._require_workspace(conn, workspace_id, workflow_id)
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

    def checkpoints_after(
        self,
        conn,
        *,
        workspace_id: str,
        workflow_id: str,
        cursor: int,
        limit: int,
    ) -> list[dict]:
        self._require_page(limit)
        self._require_workspace(conn, workspace_id, workflow_id)
        return [
            dict(row["payload"])
            for row in conn.execute(
                text(
                    """
                    SELECT payload
                    FROM durable_workflow_checkpoints
                    WHERE workflow_id = :workflow_id AND sequence > :cursor
                    ORDER BY sequence
                    LIMIT :limit
                    """
                ),
                {"workflow_id": workflow_id, "cursor": cursor, "limit": limit},
            ).mappings()
        ]

    def as_of(
        self,
        conn,
        *,
        workspace_id: str,
        workflow_id: str,
        target_sequence: int,
    ) -> dict:
        instance = self._require_workspace(conn, workspace_id, workflow_id)
        reducer_version = instance["reducer_version"]
        reducer = self._reducers.get(reducer_version)
        if reducer is None:
            raise KeyError(f"pinned reducer {reducer_version!r} is unavailable")
        if target_sequence > MAX_PAGE:
            raise ValueError("as-of target requires a bounded signed checkpoint")
        events = self.events_after(
            conn,
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            cursor=0,
            limit=MAX_PAGE,
        )
        result = reduce_as_of(
            initial_state={
                "current_state": {
                    "execution": "pending",
                    "product_iteration": "draft",
                    "product_release": "draft",
                }[instance["workflow_kind"]],
                "cancellation_state": None,
                "last_sequence": 0,
                "last_event_hash": None,
            },
            events=events,
            target_sequence=target_sequence,
            reducer=reducer,
            reducer_version=reducer_version,
        )
        return {
            "workflow_id": workflow_id,
            "sequence": result.sequence,
            "event_hash": result.event_hash,
            "state": result.state,
            "reducer_version": result.reducer_version,
            "workflow_definition_version": instance[
                "workflow_definition_version"
            ],
            "effect_adapter_registry_version": instance[
                "effect_adapter_registry_version"
            ],
            "runtime_build_id": instance["runtime_build_id"],
            "replay_compatibility_class": instance[
                "replay_compatibility_class"
            ],
            "development_attestation_id": instance["semantic_identity"][
                "development_attestation_id"
            ],
            "development_attestation_sha256": instance[
                "semantic_identity"
            ]["development_attestation_sha256"],
            "consumer_compatibility_class": instance["semantic_identity"][
                "consumer_compatibility_class"
            ],
            "configuration_fingerprint": instance["semantic_identity"][
                "configuration_fingerprint"
            ],
            "environment_fingerprint": instance["semantic_identity"][
                "environment_fingerprint"
            ],
            "data_fingerprint": instance["semantic_identity"][
                "data_fingerprint"
            ],
            "effect_policy": "receipts_only_no_direct_effect",
        }

    def compare_as_of(
        self,
        conn,
        *,
        workspace_id: str,
        left_workflow_id: str,
        left_sequence: int,
        right_workflow_id: str,
        right_sequence: int,
    ) -> dict:
        from .replay import ReplayResult

        left = self.as_of(
            conn,
            workspace_id=workspace_id,
            workflow_id=left_workflow_id,
            target_sequence=left_sequence,
        )
        right = self.as_of(
            conn,
            workspace_id=workspace_id,
            workflow_id=right_workflow_id,
            target_sequence=right_sequence,
        )
        return compare_results(
            ReplayResult(
                sequence=left["sequence"],
                event_hash=left["event_hash"],
                state=left["state"],
                reducer_version=left["reducer_version"],
                compatibility_identity=self._compatibility_identity(left),
            ),
            ReplayResult(
                sequence=right["sequence"],
                event_hash=right["event_hash"],
                state=right["state"],
                reducer_version=right["reducer_version"],
                compatibility_identity=self._compatibility_identity(right),
            ),
        )

    @staticmethod
    def _compatibility_identity(snapshot: dict) -> dict[str, str]:
        fields = (
            "workflow_definition_version",
            "effect_adapter_registry_version",
            "runtime_build_id",
            "replay_compatibility_class",
            "development_attestation_id",
            "development_attestation_sha256",
            "consumer_compatibility_class",
            "configuration_fingerprint",
            "environment_fingerprint",
            "data_fingerprint",
        )
        return {field: snapshot[field] for field in fields}

    @staticmethod
    def _require_page(limit: int) -> None:
        if not 1 <= limit <= MAX_PAGE:
            raise ValueError("review page limit must be between 1 and 50")

    @staticmethod
    def _require_workspace(conn, workspace_id: str, workflow_id: str) -> dict:
        row = conn.execute(
            text(
                """
                SELECT *
                FROM durable_workflow_instances
                WHERE workflow_id = :workflow_id AND workspace_id = :workspace_id
                """
            ),
            {"workflow_id": workflow_id, "workspace_id": workspace_id},
        ).mappings().one_or_none()
        if row is None:
            raise KeyError("durable workflow was not found in workspace")
        return dict(row)
