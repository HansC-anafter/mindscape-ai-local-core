"""DB-backed artifact lifecycle candidate reader."""

from __future__ import annotations

from typing import Any, Dict, Iterator, Optional

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase

from .policy import ArtifactLifecycleCandidate


class ArtifactLifecycleManifestReader(PostgresStoreBase):
    """Read bounded artifact lifecycle candidates from DB pointer tables."""

    def iter_candidates(
        self,
        *,
        limit: Optional[int] = None,
        page_size: int = 200,
    ) -> Iterator[ArtifactLifecycleCandidate]:
        """Yield candidates from artifact_manifest joined to artifacts."""
        remaining = limit if limit is not None else None
        offset = 0
        while remaining is None or remaining > 0:
            batch_size = min(page_size, remaining) if remaining is not None else page_size
            rows = self._fetch_candidate_rows(limit=batch_size, offset=offset)
            if not rows:
                break
            for row in rows:
                yield _candidate_from_row(row)
            offset += len(rows)
            if remaining is not None:
                remaining -= len(rows)

    def _fetch_candidate_rows(self, *, limit: int, offset: int) -> list[Dict[str, Any]]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        m.artifact_id,
                        m.workspace_id,
                        COALESCE(m.task_id, a.task_id) AS task_id,
                        COALESCE(m.execution_id, a.execution_id) AS execution_id,
                        COALESCE(m.storage_ref, a.storage_ref) AS storage_ref,
                        m.result_json_path,
                        m.checksum_sha256,
                        m.bytes AS bytes_count,
                        a.summary AS artifact_summary,
                        m.summary AS manifest_summary,
                        t.status AS task_status,
                        a.metadata AS metadata
                    FROM artifact_manifest m
                    LEFT JOIN artifacts a ON a.id = m.artifact_id
                    LEFT JOIN tasks t ON t.id = COALESCE(m.task_id, a.task_id)
                    ORDER BY m.created_at ASC, m.artifact_id ASC
                    LIMIT :limit OFFSET :offset
                    """
                ),
                {"limit": limit, "offset": offset},
            ).fetchall()
        return [dict(row._mapping if hasattr(row, "_mapping") else row) for row in rows]


def _candidate_from_row(row: Dict[str, Any]) -> ArtifactLifecycleCandidate:
    metadata = row.get("metadata")
    return ArtifactLifecycleCandidate(
        artifact_id=str(row.get("artifact_id") or ""),
        workspace_id=str(row.get("workspace_id") or ""),
        task_id=_optional_str(row.get("task_id")),
        execution_id=_optional_str(row.get("execution_id")),
        storage_ref=_optional_str(row.get("storage_ref")),
        result_json_path=_optional_str(row.get("result_json_path")),
        checksum_sha256=_optional_str(row.get("checksum_sha256")),
        bytes_count=row.get("bytes_count") if isinstance(row.get("bytes_count"), int) else None,
        summary=_optional_str(row.get("artifact_summary")),
        manifest_summary=_optional_str(row.get("manifest_summary")),
        task_status=_optional_str(row.get("task_status")),
        metadata=metadata if isinstance(metadata, dict) else {},
    )


def _optional_str(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
