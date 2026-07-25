"""Bounded upper read model for the unmounted Phase 07 seam."""

from __future__ import annotations

import base64
import binascii
from copy import deepcopy
from typing import Callable

from sqlalchemy import text

from .product_outcome_compare import compare_iteration_states
from .replay import reduce_as_of

MAX_PAGE = 50


class ProductOutcomeReviewService:
    """Reads only the durable ledger/projection through caller connections."""

    def __init__(self, *, reducers: dict[str, Callable]) -> None:
        self._reducers = reducers

    def iteration_summary(
        self, conn, *, workspace_id: str, iteration_id: str
    ) -> dict:
        row = self._require_kind(
            conn, workspace_id, iteration_id, "product_iteration"
        )
        state = deepcopy(row["projection_state"])
        definition = state["definition"]
        selected_arm = next(
            item
            for item in definition["arms"]
            if item["arm_id"] == definition["release_target"]["arm_id"]
        )
        adapter = state.get("adapter_refs_by_arm", {}).get(
            selected_arm["arm_id"]
        )
        governance = self._governance_receipts(conn, iteration_id)
        release = self._release_summary(
            conn,
            workspace_id=workspace_id,
            promotion_link=state.get("promotion_link"),
        )
        evaluation = state.get("evaluation")
        return {
            "iteration_id": iteration_id,
            "workspace_id": workspace_id,
            "current_sequence": row["current_sequence"],
            "current_event_hash": row["current_event_hash"],
            "state": row["current_state"],
            "terminal": row["terminal"],
            "objective": definition["objective"],
            "revision": definition["revision"],
            "parent_iteration_id": definition["parent_iteration_id"],
            "definition_sha256": definition["definition_sha256"],
            "arms": deepcopy(definition["arms"]),
            "selected_arm_id": selected_arm["arm_id"],
            "validation_design": deepcopy(
                definition["validation_design"]
            ),
            "evaluator": deepcopy(definition["evaluator"]),
            "metric_definitions": deepcopy(
                definition["metric_definitions"]
            ),
            "evidence_frontier": {
                **deepcopy(state["evidence_frontier"]),
                "accepted_observation_count": int(
                    state.get("accepted_observation_count", 0)
                ),
                "minimum_sample_size": definition["validation_design"][
                    "minimum_sample_size"
                ],
            },
            "evaluation_attempt_count": int(
                state.get("evaluation_attempt_count", 0)
            ),
            "evaluation": deepcopy(evaluation),
            "gate_results": deepcopy(
                (evaluation or {}).get("gate_results", [])
            ),
            "governance_receipts": governance,
            "product_release": release,
            "evidence_lifecycle": deepcopy(
                state.get("evidence_lifecycle")
            ),
            "experience_summary": deepcopy(
                state.get("experience_summary")
            ),
            "review_lens": self._review_lens(adapter),
            "effect_policy": "read_only_no_effect",
        }

    def observations_page(
        self,
        conn,
        *,
        workspace_id: str,
        iteration_id: str,
        cursor: str | None,
        limit: int,
    ) -> dict:
        self._require_page(limit)
        self._require_kind(
            conn, workspace_id, iteration_id, "product_iteration"
        )
        cursor_sequence = self._decode_cursor(cursor)
        rows = conn.execute(
            text(
                """
                SELECT sequence, occurred_at, event_hash, event_type, payload
                FROM durable_workflow_events
                WHERE workflow_id = :workflow_id
                  AND sequence > :cursor
                  AND event_type IN (
                    'outcome_observation_accepted',
                    'outcome_observation_rejected'
                  )
                ORDER BY sequence
                LIMIT :limit
                """
            ),
            {
                "workflow_id": iteration_id,
                "cursor": cursor_sequence,
                "limit": limit,
            },
        ).mappings().all()
        items = [self._compact_observation(dict(row)) for row in rows]
        return {
            "observations": items,
            "next_cursor": (
                self._encode_cursor(rows[-1]["sequence"])
                if len(rows) == limit
                else None
            ),
        }

    def evaluations_page(
        self,
        conn,
        *,
        workspace_id: str,
        iteration_id: str,
        cursor: str | None,
        limit: int,
    ) -> dict:
        self._require_page(limit)
        self._require_kind(
            conn, workspace_id, iteration_id, "product_iteration"
        )
        cursor_sequence = self._decode_cursor(cursor)
        rows = conn.execute(
            text(
                """
                SELECT sequence, occurred_at, event_hash, payload
                FROM durable_workflow_events
                WHERE workflow_id = :workflow_id
                  AND sequence > :cursor
                  AND event_type = 'transition'
                  AND payload->'typed_receipt'->>'receipt_type'
                    = 'evaluation_receipt'
                ORDER BY sequence
                LIMIT :limit
                """
            ),
            {
                "workflow_id": iteration_id,
                "cursor": cursor_sequence,
                "limit": limit,
            },
        ).mappings().all()
        items = [
            {
                "sequence": row["sequence"],
                "occurred_at": row["occurred_at"],
                "event_hash": row["event_hash"],
                "evaluation": deepcopy(
                    row["payload"]["typed_receipt"]["receipt"]
                ),
            }
            for row in rows
        ]
        return {
            "evaluations": items,
            "next_cursor": (
                self._encode_cursor(rows[-1]["sequence"])
                if len(rows) == limit
                else None
            ),
        }

    def as_of(
        self,
        conn,
        *,
        workspace_id: str,
        iteration_id: str,
        target_sequence: int,
    ) -> dict:
        row = self._require_kind(
            conn, workspace_id, iteration_id, "product_iteration"
        )
        if target_sequence > MAX_PAGE:
            raise ValueError(
                "upper as-of target requires a bounded signed checkpoint"
            )
        reducer = self._reducers.get(row["reducer_version"])
        if reducer is None:
            raise KeyError("pinned upper reducer is unavailable")
        events = self._events_window(conn, iteration_id)
        result = reduce_as_of(
            initial_state={
                "current_state": "draft",
                "cancellation_state": None,
                "last_sequence": 0,
                "last_event_hash": None,
            },
            events=events,
            target_sequence=target_sequence,
            reducer=reducer,
            reducer_version=row["reducer_version"],
        )
        return {
            "iteration_id": iteration_id,
            "sequence": result.sequence,
            "event_hash": result.event_hash,
            "state": result.state,
            "reducer_version": result.reducer_version,
            "effect_policy": "read_only_no_effect",
        }

    def compare(
        self,
        conn,
        *,
        workspace_id: str,
        left: dict,
        right: dict,
    ) -> dict:
        left_snapshot = self.as_of(
            conn,
            workspace_id=workspace_id,
            iteration_id=left["iteration_id"],
            target_sequence=left["sequence"],
        )
        right_snapshot = self.as_of(
            conn,
            workspace_id=workspace_id,
            iteration_id=right["iteration_id"],
            target_sequence=right["sequence"],
        )
        result = compare_iteration_states(
            left_snapshot["state"], right_snapshot["state"]
        )
        return {
            "left": {
                "iteration_id": left["iteration_id"],
                "sequence": left_snapshot["sequence"],
                "event_hash": left_snapshot["event_hash"],
            },
            "right": {
                "iteration_id": right["iteration_id"],
                "sequence": right_snapshot["sequence"],
                "event_hash": right_snapshot["event_hash"],
            },
            **result,
        }

    @staticmethod
    def _review_lens(adapter: dict | None) -> dict | None:
        if not adapter or not adapter.get("review_lens"):
            return None
        identity = adapter["capability_identity"]
        return {
            "capability_code": identity["capability_code"],
            "pack_version": identity["pack_version"],
            "manifest_sha256": identity["manifest_sha256"],
            "descriptor_sha256": adapter["descriptor_sha256"],
            **deepcopy(adapter["review_lens"]),
        }

    @staticmethod
    def _compact_observation(row: dict) -> dict:
        payload = row["payload"]
        observation = payload.get("observation")
        if observation:
            return {
                "sequence": row["sequence"],
                "occurred_at": row["occurred_at"],
                "event_hash": row["event_hash"],
                "status": "accepted",
                "observation_id": observation["observation_id"],
                "arm_id": observation["arm_id"],
                "case_id": observation["case_id"],
                "metric_id": observation["metric_id"],
                "quality_state": observation["quality_state"],
                "provenance_hash": observation["provenance_hash"],
                "comparability_key": observation["comparability_key"],
            }
        return {
            "sequence": row["sequence"],
            "occurred_at": row["occurred_at"],
            "event_hash": row["event_hash"],
            "status": "rejected",
            "observation_id": payload["observation_id"],
            "observation_sha256": payload["observation_sha256"],
            "reason": payload["reason"],
        }

    def _events_window(self, conn, workflow_id: str) -> list[dict]:
        return [
            dict(row)
            for row in conn.execute(
                text(
                    """
                    SELECT *
                    FROM durable_workflow_events
                    WHERE workflow_id = :workflow_id
                    ORDER BY sequence
                    LIMIT :limit
                    """
                ),
                {"workflow_id": workflow_id, "limit": MAX_PAGE},
            ).mappings()
        ]

    @staticmethod
    def _governance_receipts(conn, workflow_id: str) -> dict:
        row = conn.execute(
            text(
                """
                SELECT
                  (SELECT payload
                   FROM durable_workflow_approval_requests
                   WHERE workflow_id = :workflow_id
                   ORDER BY created_at DESC, approval_id DESC LIMIT 1)
                    AS approval_request,
                  (SELECT d.payload
                   FROM durable_workflow_approval_decisions d
                   JOIN durable_workflow_approval_requests r
                     ON r.approval_id = d.approval_id
                   WHERE r.workflow_id = :workflow_id
                   ORDER BY d.decided_at DESC, d.decision_id DESC LIMIT 1)
                    AS approval_decision,
                  (SELECT c.payload
                   FROM durable_workflow_approval_consumptions c
                   JOIN durable_workflow_approval_requests r
                     ON r.approval_id = c.approval_id
                   WHERE r.workflow_id = :workflow_id
                   ORDER BY c.consumed_at DESC, c.consumption_id DESC LIMIT 1)
                    AS approval_consumption,
                  (SELECT payload
                   FROM durable_workflow_side_effect_receipts
                   WHERE workflow_id = :workflow_id
                     AND effect_type = 'product_promotion'
                   ORDER BY recorded_at DESC, receipt_id DESC LIMIT 1)
                    AS release_effect
                """
            ),
            {"workflow_id": workflow_id},
        ).mappings().one()
        return {
            key: deepcopy(row[key])
            for key in (
                "approval_request",
                "approval_decision",
                "approval_consumption",
                "release_effect",
            )
        }

    def _release_summary(
        self, conn, *, workspace_id: str, promotion_link: dict | None
    ) -> dict:
        if not promotion_link:
            return {"state": "not_started", "release_workflow_id": None}
        release_id = promotion_link["release_workflow_id"]
        row = conn.execute(
            text(
                """
                SELECT i.current_state, i.terminal, p.state
                FROM durable_workflow_instances i
                LEFT JOIN durable_workflow_projection_offsets p
                  ON p.projection_name = 'current'
                 AND p.workflow_id = i.workflow_id
                WHERE i.workflow_id = :workflow_id
                  AND i.workspace_id = :workspace_id
                  AND i.workflow_kind = 'product_release'
                """
            ),
            {"workflow_id": release_id, "workspace_id": workspace_id},
        ).mappings().one_or_none()
        if row is None:
            return {
                "state": "not_started",
                "release_workflow_id": release_id,
            }
        projection = dict(row["state"] or {})
        return {
            "state": row["current_state"],
            "terminal": row["terminal"],
            "release_workflow_id": release_id,
            "release_link": deepcopy(projection.get("release_link")),
            "health": deepcopy(projection.get("release_health")),
            "lifecycle": deepcopy(
                projection.get("evidence_lifecycle")
            ),
        }

    @staticmethod
    def _require_page(limit: int) -> None:
        if not 1 <= limit <= MAX_PAGE:
            raise ValueError("outcome review page must be between 1 and 50")

    @staticmethod
    def _encode_cursor(sequence: int) -> str:
        return base64.urlsafe_b64encode(
            f"sequence:{sequence}".encode("ascii")
        ).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str | None) -> int:
        if cursor is None:
            return 0
        try:
            padded = cursor + "=" * (-len(cursor) % 4)
            decoded = base64.urlsafe_b64decode(padded).decode("ascii")
            prefix, value = decoded.split(":", 1)
            sequence = int(value)
        except (binascii.Error, ValueError, UnicodeError) as exc:
            raise ValueError("outcome review cursor is invalid") from exc
        if prefix != "sequence" or sequence < 0:
            raise ValueError("outcome review cursor is invalid")
        return sequence

    @staticmethod
    def _require_kind(
        conn,
        workspace_id: str,
        workflow_id: str,
        expected_kind: str,
    ) -> dict:
        row = conn.execute(
            text(
                """
                SELECT i.*, p.last_sequence AS projection_sequence,
                       p.state AS projection_state
                FROM durable_workflow_instances i
                JOIN durable_workflow_projection_offsets p
                  ON p.projection_name = 'current'
                 AND p.workflow_id = i.workflow_id
                WHERE i.workflow_id = :workflow_id
                  AND i.workspace_id = :workspace_id
                  AND i.workflow_kind = :workflow_kind
                """
            ),
            {
                "workflow_id": workflow_id,
                "workspace_id": workspace_id,
                "workflow_kind": expected_kind,
            },
        ).mappings().one_or_none()
        if row is None:
            raise KeyError("upper workflow was not found in workspace")
        if row["projection_sequence"] != row["current_sequence"]:
            raise ValueError("upper current projection is stale")
        return dict(row)
