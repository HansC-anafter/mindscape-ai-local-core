"""Postgres store for run harness episode ledger metadata."""

from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import text

from backend.app.models.run_harness import (
    RunHarnessEpisode,
    RunHarnessObservation,
    RunHarnessResult,
    RunHarnessStatus,
)
from backend.app.services.run_harness.episode_ledger_mapping import (
    TERMINAL_STATUS_VALUES,
    first_non_empty,
    pending_result_from_episode,
    row_mapping,
    row_to_result,
    rows_to_episode,
)

from ..postgres_base import PostgresStoreBase


_TERMINAL_STATUSES = TERMINAL_STATUS_VALUES
_mapping = row_mapping
_first_non_empty = first_non_empty


class PostgresRunHarnessEpisodeLedgerStore(PostgresStoreBase):
    """Persist and read compact run harness episode metadata."""

    def create_episode(
        self,
        episode: RunHarnessEpisode,
        selection_snapshot: dict[str, Any],
    ) -> RunHarnessEpisode:
        row = {
            "episode_id": episode.episode_id,
            "run_id": self._required_snapshot_value(selection_snapshot, "run_id"),
            "intent_envelope_ref": episode.intent_envelope_ref,
            "selection_ref": episode.selection_ref,
            "harness_kind": self._required_snapshot_value(
                selection_snapshot,
                "harness_kind",
            ),
            "status": episode.status.value,
            "workspace_id": self._required_snapshot_value(
                selection_snapshot,
                "workspace_id",
            ),
            "project_id": selection_snapshot.get("project_id"),
            "profile_id": selection_snapshot.get("profile_id"),
            "source_execution_id": selection_snapshot.get("source_execution_id"),
            "selection_snapshot": self.serialize_json(selection_snapshot),
            "capability_snapshot_refs": self.serialize_json(
                selection_snapshot.get("capability_snapshot_refs") or []
            ),
            "created_at": episode.created_at,
            "updated_at": episode.updated_at,
            "terminal_at": (
                episode.updated_at if episode.status.value in _TERMINAL_STATUSES else None
            ),
        }
        with self.transaction() as conn:
            stored = conn.execute(
                text(
                    """
                    INSERT INTO run_harness_episodes (
                        episode_id,
                        run_id,
                        intent_envelope_ref,
                        selection_ref,
                        harness_kind,
                        status,
                        workspace_id,
                        project_id,
                        profile_id,
                        source_execution_id,
                        selection_snapshot,
                        capability_snapshot_refs,
                        created_at,
                        updated_at,
                        terminal_at
                    ) VALUES (
                        :episode_id,
                        :run_id,
                        :intent_envelope_ref,
                        :selection_ref,
                        :harness_kind,
                        :status,
                        :workspace_id,
                        :project_id,
                        :profile_id,
                        :source_execution_id,
                        CAST(:selection_snapshot AS JSONB),
                        CAST(:capability_snapshot_refs AS JSONB),
                        :created_at,
                        :updated_at,
                        :terminal_at
                    )
                    ON CONFLICT (episode_id) DO UPDATE SET
                        run_id = EXCLUDED.run_id,
                        intent_envelope_ref = EXCLUDED.intent_envelope_ref,
                        selection_ref = EXCLUDED.selection_ref,
                        harness_kind = EXCLUDED.harness_kind,
                        status = EXCLUDED.status,
                        workspace_id = EXCLUDED.workspace_id,
                        project_id = EXCLUDED.project_id,
                        profile_id = EXCLUDED.profile_id,
                        source_execution_id = EXCLUDED.source_execution_id,
                        selection_snapshot = EXCLUDED.selection_snapshot,
                        capability_snapshot_refs = EXCLUDED.capability_snapshot_refs,
                        updated_at = EXCLUDED.updated_at,
                        terminal_at = COALESCE(
                            run_harness_episodes.terminal_at,
                            EXCLUDED.terminal_at
                        )
                    RETURNING *
                    """
                ),
                row,
            ).fetchone()
        return self._rows_to_episode(stored, [])

    def append_event(
        self,
        episode_id: str,
        event_type: str,
        status: str,
        payload: dict[str, Any],
    ) -> int:
        event_id = _first_non_empty(payload.get("event_id")) or str(uuid.uuid4())
        with self.transaction() as conn:
            episode_row = conn.execute(
                text(
                    """
                    SELECT episode_id, run_id
                    FROM run_harness_episodes
                    WHERE episode_id = :episode_id
                    FOR UPDATE
                    """
                ),
                {"episode_id": episode_id},
            ).fetchone()
            if episode_row is None:
                raise ValueError("run harness episode not found")
            run_id = _mapping(episode_row)["run_id"]
            sequence_row = conn.execute(
                text(
                    """
                    SELECT COALESCE(MAX(sequence_no), 0) + 1 AS sequence_no
                    FROM run_harness_episode_events
                    WHERE episode_id = :episode_id
                    """
                ),
                {"episode_id": episode_id},
            ).fetchone()
            sequence_no = int(_mapping(sequence_row)["sequence_no"])
            params = {
                "event_id": event_id,
                "episode_id": episode_id,
                "run_id": run_id,
                "attempt_id": payload.get("attempt_id"),
                "attempt_number": payload.get("attempt_number"),
                "sequence_no": sequence_no,
                "event_type": event_type,
                "status": status,
                "payload_ref": payload.get("payload_ref"),
                "policy_eval": self.serialize_json(payload.get("policy_eval") or {}),
                "trace_refs": self.serialize_json(payload.get("trace_refs") or []),
                "artifact_lineage": self.serialize_json(
                    payload.get("artifact_lineage") or []
                ),
                "metadata": self.serialize_json(payload.get("metadata") or {}),
                "terminal": status in _TERMINAL_STATUSES,
            }
            conn.execute(
                text(
                    """
                    INSERT INTO run_harness_episode_events (
                        event_id,
                        episode_id,
                        run_id,
                        attempt_id,
                        attempt_number,
                        sequence_no,
                        event_type,
                        status,
                        payload_ref,
                        policy_eval,
                        trace_refs,
                        artifact_lineage,
                        metadata
                    ) VALUES (
                        :event_id,
                        :episode_id,
                        :run_id,
                        :attempt_id,
                        :attempt_number,
                        :sequence_no,
                        :event_type,
                        :status,
                        :payload_ref,
                        CAST(:policy_eval AS JSONB),
                        CAST(:trace_refs AS JSONB),
                        CAST(:artifact_lineage AS JSONB),
                        CAST(:metadata AS JSONB)
                    )
                    """
                ),
                params,
            )
            conn.execute(
                text(
                    """
                    UPDATE run_harness_episodes
                    SET
                        status = :status,
                        updated_at = now(),
                        terminal_at = CASE
                            WHEN :terminal THEN COALESCE(terminal_at, now())
                            ELSE terminal_at
                        END
                    WHERE episode_id = :episode_id
                    """
                ),
                params,
            )
        return sequence_no

    def upsert_result(self, result: RunHarnessResult) -> RunHarnessResult:
        failure = result.failure
        params = {
            "episode_id": result.episode_id,
            "run_id": result.run_id,
            "harness_kind": result.harness_kind.value,
            "status": result.status.value,
            "failure_code": failure.code if failure else None,
            "failure_message": failure.message if failure else None,
            "failure_details": self.serialize_json(failure.details if failure else {}),
            "wait_state": self.serialize_json(
                result.wait_state.model_dump(mode="json") if result.wait_state else None
            ),
            "score": self.serialize_json(
                result.score.model_dump(mode="json") if result.score else None
            ),
            "next_action": self.serialize_json(
                result.next_action.model_dump(mode="json") if result.next_action else None
            ),
            "trace_refs": self.serialize_json(
                [trace.model_dump(mode="json") for trace in result.trace_refs]
            ),
            "output_artifact_refs": self.serialize_json(result.output_artifact_refs),
            "result_metadata": self.serialize_json(result.metadata),
            "terminal": result.status.value in _TERMINAL_STATUSES,
        }
        with self.transaction() as conn:
            stored = conn.execute(
                text(
                    """
                    INSERT INTO run_harness_episode_results (
                        episode_id,
                        run_id,
                        harness_kind,
                        status,
                        failure_code,
                        failure_message,
                        failure_details,
                        wait_state,
                        score,
                        next_action,
                        trace_refs,
                        output_artifact_refs,
                        result_metadata,
                        updated_at
                    ) VALUES (
                        :episode_id,
                        :run_id,
                        :harness_kind,
                        :status,
                        :failure_code,
                        :failure_message,
                        CAST(:failure_details AS JSONB),
                        CAST(:wait_state AS JSONB),
                        CAST(:score AS JSONB),
                        CAST(:next_action AS JSONB),
                        CAST(:trace_refs AS JSONB),
                        CAST(:output_artifact_refs AS JSONB),
                        CAST(:result_metadata AS JSONB),
                        now()
                    )
                    ON CONFLICT (episode_id) DO UPDATE SET
                        run_id = EXCLUDED.run_id,
                        harness_kind = EXCLUDED.harness_kind,
                        status = EXCLUDED.status,
                        failure_code = EXCLUDED.failure_code,
                        failure_message = EXCLUDED.failure_message,
                        failure_details = EXCLUDED.failure_details,
                        wait_state = EXCLUDED.wait_state,
                        score = EXCLUDED.score,
                        next_action = EXCLUDED.next_action,
                        trace_refs = EXCLUDED.trace_refs,
                        output_artifact_refs = EXCLUDED.output_artifact_refs,
                        result_metadata = EXCLUDED.result_metadata,
                        updated_at = now()
                    RETURNING *
                    """
                ),
                params,
            ).fetchone()
            conn.execute(
                text(
                    """
                    UPDATE run_harness_episodes
                    SET
                        status = :status,
                        updated_at = now(),
                        terminal_at = CASE
                            WHEN :terminal THEN COALESCE(terminal_at, now())
                            ELSE terminal_at
                        END
                    WHERE episode_id = :episode_id
                    """
                ),
                params,
            )
        return self._row_to_result(stored)

    def get_observation(self, episode_id: str) -> Optional[RunHarnessObservation]:
        with self.get_connection() as conn:
            episode_row = self._get_episode_row(conn, episode_id)
            if episode_row is None:
                return None
            event_rows = conn.execute(
                text(
                    """
                    SELECT *
                    FROM run_harness_episode_events
                    WHERE episode_id = :episode_id
                    ORDER BY sequence_no ASC
                    """
                ),
                {"episode_id": episode_id},
            ).fetchall()
            result_row = conn.execute(
                text(
                    """
                    SELECT *
                    FROM run_harness_episode_results
                    WHERE episode_id = :episode_id
                    """
                ),
                {"episode_id": episode_id},
            ).fetchone()
        episode = self._rows_to_episode(episode_row, event_rows)
        result = (
            self._row_to_result(result_row)
            if result_row is not None
            else self._pending_result_from_episode(episode_row)
        )
        return RunHarnessObservation(
            workspace_id=_mapping(episode_row)["workspace_id"],
            episode=episode,
            result=result,
            source="run_harness_episode_ledger",
            metadata={"run_id": _mapping(episode_row)["run_id"]},
        )

    def get_terminal_result(self, episode_id: str) -> Optional[RunHarnessResult]:
        with self.get_connection() as conn:
            result_row = conn.execute(
                text(
                    """
                    SELECT *
                    FROM run_harness_episode_results
                    WHERE episode_id = :episode_id
                      AND status IN ('succeeded', 'failed', 'canceled', 'escalated')
                    """
                ),
                {"episode_id": episode_id},
            ).fetchone()
        return self._row_to_result(result_row) if result_row is not None else None

    def _get_episode_row(self, conn: Any, episode_id: str) -> Any:
        return conn.execute(
            text(
                """
                SELECT *
                FROM run_harness_episodes
                WHERE episode_id = :episode_id
                """
            ),
            {"episode_id": episode_id},
        ).fetchone()

    @staticmethod
    def _required_snapshot_value(snapshot: dict[str, Any], key: str) -> str:
        value = str(snapshot.get(key) or "").strip()
        if not value:
            raise ValueError(f"selection_snapshot requires {key}")
        return value

    _rows_to_episode = staticmethod(rows_to_episode)
    _row_to_result = staticmethod(row_to_result)
    _pending_result_from_episode = staticmethod(pending_result_from_episode)
