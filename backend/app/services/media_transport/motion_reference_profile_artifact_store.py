"""Bounded Postgres lookup for live motion reference profile artifacts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase

from .motion_reference_profile_artifact import (
    MOTION_REFERENCE_PROFILE_ARTIFACT_CONTRACT,
)

MOTION_REFERENCE_PROFILE_OWNER_PLAYBOOK = "yogacoach_reference_profile"
MOTION_REFERENCE_PROFILE_ARTIFACT_TYPE = "file"


@dataclass(frozen=True)
class MotionReferenceProfileArtifactRecord:
    id: str
    workspace_id: str
    storage_ref: str | None
    metadata: dict[str, Any]


def _metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _record(row: Any) -> MotionReferenceProfileArtifactRecord:
    mapping = row._mapping if hasattr(row, "_mapping") else row
    return MotionReferenceProfileArtifactRecord(
        id=str(mapping["id"]),
        workspace_id=str(mapping["workspace_id"]),
        storage_ref=str(mapping["storage_ref"]) if mapping["storage_ref"] else None,
        metadata=_metadata(mapping["metadata"]),
    )


class MotionReferenceProfileArtifactStore(PostgresStoreBase):
    """Read only the columns needed to admit one reference profile."""

    def get_artifact(self, artifact_id: str) -> MotionReferenceProfileArtifactRecord | None:
        with self.get_connection() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT id, workspace_id, storage_ref, metadata
                    FROM artifacts
                    WHERE id = :artifact_id
                    LIMIT 1
                    """
                ),
                {"artifact_id": artifact_id},
            ).fetchone()
        return _record(row) if row is not None else None

    def find_by_source_ref(
        self,
        *,
        workspace_id: str,
        source_ref: str,
        limit: int = 2,
    ) -> list[MotionReferenceProfileArtifactRecord]:
        bounded_limit = min(2, max(1, int(limit)))
        with self.get_connection() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT id, workspace_id, storage_ref, metadata
                    FROM artifacts
                    WHERE workspace_id = :workspace_id
                      AND playbook_code = :playbook_code
                      AND artifact_type = :artifact_type
                      AND metadata IS NOT NULL
                      AND metadata::jsonb ->> 'artifact_contract' = :artifact_contract
                      AND metadata::jsonb ->> 'source_ref' = :source_ref
                    ORDER BY updated_at DESC, id DESC
                    LIMIT :limit
                    """
                ),
                {
                    "workspace_id": workspace_id,
                    "playbook_code": MOTION_REFERENCE_PROFILE_OWNER_PLAYBOOK,
                    "artifact_type": MOTION_REFERENCE_PROFILE_ARTIFACT_TYPE,
                    "artifact_contract": MOTION_REFERENCE_PROFILE_ARTIFACT_CONTRACT,
                    "source_ref": source_ref,
                    "limit": bounded_limit,
                },
            ).fetchall()
        return [_record(row) for row in rows]


__all__ = [
    "MOTION_REFERENCE_PROFILE_ARTIFACT_TYPE",
    "MOTION_REFERENCE_PROFILE_OWNER_PLAYBOOK",
    "MotionReferenceProfileArtifactRecord",
    "MotionReferenceProfileArtifactStore",
]
