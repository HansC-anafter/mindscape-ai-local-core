"""Service facade for run harness episode ledger read/write contracts."""

from __future__ import annotations

import json
from typing import Any, Mapping, Optional

from backend.app.models.run_harness import (
    RunHarnessEpisode,
    RunHarnessObservation,
    RunHarnessResult,
    RunHarnessStatus,
)
from backend.app.services.stores.postgres.run_harness_episode_ledger_store import (
    PostgresRunHarnessEpisodeLedgerStore,
)


EVENT_PAYLOAD_BUDGET_BYTES = 16 * 1024
RESULT_PAYLOAD_BUDGET_BYTES = 32 * 1024
_BLOB_KEY_NAMES = {
    "artifact_blob",
    "artifact_payload",
    "base64",
    "binary_data",
    "blob",
    "data_uri",
    "payload_bytes",
    "raw_payload",
}


class RunHarnessEpisodeLedgerService:
    """Validate and persist run harness ledger metadata."""

    def __init__(
        self,
        store: Optional[PostgresRunHarnessEpisodeLedgerStore] = None,
    ) -> None:
        self.store = store or PostgresRunHarnessEpisodeLedgerStore(db_role="core")

    def create_episode(
        self,
        episode: RunHarnessEpisode,
        selection_snapshot: dict[str, Any],
    ) -> RunHarnessEpisode:
        self._require_snapshot_fields(
            selection_snapshot,
            "run_id",
            "workspace_id",
            "harness_kind",
        )
        self._reject_artifact_payload(selection_snapshot)
        return self.store.create_episode(episode, selection_snapshot)

    def append_event(
        self,
        episode_id: str,
        event_type: str,
        status: str,
        payload: dict[str, Any],
    ) -> int:
        RunHarnessStatus(status)
        self._reject_artifact_payload(payload)
        self._validate_json_budget(
            "run harness event payload",
            {
                "policy_eval": payload.get("policy_eval") or {},
                "trace_refs": payload.get("trace_refs") or [],
                "artifact_lineage": payload.get("artifact_lineage") or [],
                "metadata": payload.get("metadata") or {},
            },
            EVENT_PAYLOAD_BUDGET_BYTES,
        )
        return self.store.append_event(episode_id, event_type, status, payload)

    def upsert_result(self, result: RunHarnessResult) -> RunHarnessResult:
        payload = {
            "wait_state": (
                result.wait_state.model_dump(mode="json") if result.wait_state else None
            ),
            "score": result.score.model_dump(mode="json") if result.score else None,
            "next_action": (
                result.next_action.model_dump(mode="json")
                if result.next_action
                else None
            ),
            "trace_refs": [
                trace.model_dump(mode="json") for trace in result.trace_refs
            ],
            "output_artifact_refs": result.output_artifact_refs,
            "result_metadata": result.metadata,
        }
        self._reject_artifact_payload(payload)
        self._validate_json_budget(
            "run harness result payload",
            payload,
            RESULT_PAYLOAD_BUDGET_BYTES,
        )
        return self.store.upsert_result(result)

    def get_observation(self, episode_id: str) -> Optional[RunHarnessObservation]:
        return self.store.get_observation(episode_id)

    def get_terminal_result(self, episode_id: str) -> Optional[RunHarnessResult]:
        return self.store.get_terminal_result(episode_id)

    @staticmethod
    def _require_snapshot_fields(
        selection_snapshot: Mapping[str, Any],
        *field_names: str,
    ) -> None:
        missing = [
            field_name
            for field_name in field_names
            if not str(selection_snapshot.get(field_name) or "").strip()
        ]
        if missing:
            raise ValueError(
                "selection_snapshot requires " + ", ".join(sorted(missing))
            )

    @staticmethod
    def _validate_json_budget(
        label: str,
        payload: Mapping[str, Any],
        max_bytes: int,
    ) -> None:
        try:
            encoded = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} is not JSON serializable: {exc}") from exc
        if len(encoded) > max_bytes:
            raise ValueError(f"{label} exceeds {max_bytes} bytes")

    @classmethod
    def _reject_artifact_payload(cls, payload: Any, path: str = "payload") -> None:
        if isinstance(payload, Mapping):
            for key, value in payload.items():
                key_text = str(key)
                normalized_key = key_text.lower()
                if normalized_key in _BLOB_KEY_NAMES:
                    raise ValueError(
                        f"artifact payload field is not allowed at {path}.{key_text}"
                    )
                cls._reject_artifact_payload(value, f"{path}.{key_text}")
        elif isinstance(payload, list):
            for index, value in enumerate(payload):
                cls._reject_artifact_payload(value, f"{path}[{index}]")
        elif isinstance(payload, str) and payload.strip().startswith("data:"):
            raise ValueError(f"inline data URI is not allowed at {path}")
        elif isinstance(payload, (bytes, bytearray)):
            raise ValueError(f"binary payload is not allowed at {path}")
