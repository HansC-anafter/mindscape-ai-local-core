"""Bounded on-demand coverage and crash-gap inventory for projections."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

from sqlalchemy import text

from backend.app.services.knowledge_authorization import (
    RetrievalAccessContext,
    set_local_knowledge_context,
)
from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.services.vector_search import VectorSearchService


@dataclass(frozen=True)
class ProjectionCoverageItem:
    intake_id: str
    source_instance_id: str
    source_revision: str
    source_ref: str
    content_hash: str
    capability_code: str
    descriptor_id: str
    trigger_mode: str
    task_id: Optional[str]
    task_status: Optional[str]
    projection_status: Optional[str]
    projection_active: bool
    resource_active: bool
    state: str
    reason: Optional[str]
    created_at: datetime


@dataclass(frozen=True)
class ProjectionCoveragePage:
    items: tuple[ProjectionCoverageItem, ...]
    next_before_created_at: Optional[datetime]
    limit: int


class ProjectionCoverageCoreRepository(PostgresStoreBase):
    """Read the source ledger and existing task truth in one core query."""

    def list_page(
        self,
        *,
        scope_type: str,
        scope_id: str,
        limit: int,
        before_created_at: Optional[datetime],
    ) -> tuple[dict[str, Any], ...]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        intake.id,
                        intake.source_instance_id,
                        intake.source_revision,
                        intake.content_hash,
                        intake.metadata,
                        intake.created_at,
                        task.id AS task_id,
                        task.status AS task_status
                    FROM knowledge_source_intakes AS intake
                    JOIN knowledge_source_states AS state
                      ON state.source_instance_id =
                         intake.source_instance_id
                    LEFT JOIN tasks AS task
                      ON task.id =
                         intake.metadata->>'projection_task_id'
                    WHERE state.owner_type = :scope_type
                      AND state.owner_id = :scope_id
                      AND (
                          CAST(:before_created_at AS timestamptz) IS NULL
                          OR intake.created_at <
                             CAST(:before_created_at AS timestamptz)
                      )
                    ORDER BY intake.created_at DESC, intake.id DESC
                    LIMIT :limit
                    """
                ),
                {
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "before_created_at": before_created_at,
                    "limit": limit,
                },
            ).fetchall()
        result = []
        for row in rows:
            mapping = row._mapping if hasattr(row, "_mapping") else None
            result.append(
                {
                    "intake_id": (
                        mapping["id"] if mapping is not None else row[0]
                    ),
                    "source_instance_id": (
                        mapping["source_instance_id"]
                        if mapping is not None
                        else row[1]
                    ),
                    "source_revision": (
                        mapping["source_revision"]
                        if mapping is not None
                        else row[2]
                    ),
                    "content_hash": (
                        mapping["content_hash"]
                        if mapping is not None
                        else row[3]
                    ),
                    "metadata": (
                        mapping["metadata"]
                        if mapping is not None
                        else row[4]
                    ),
                    "created_at": (
                        mapping["created_at"]
                        if mapping is not None
                        else row[5]
                    ),
                    "task_id": (
                        mapping["task_id"]
                        if mapping is not None
                        else row[6]
                    ),
                    "task_status": (
                        mapping["task_status"]
                        if mapping is not None
                        else row[7]
                    ),
                }
            )
        return tuple(result)


class ProjectionCoverageService:
    """Compare core admission/task truth with vector activation on demand."""

    def __init__(
        self,
        *,
        core_repository: ProjectionCoverageCoreRepository | None = None,
        vector_connection_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._core = core_repository or ProjectionCoverageCoreRepository()
        self._vector_connection_factory = (
            vector_connection_factory or VectorSearchService()._get_connection
        )

    def list_page(
        self,
        *,
        access_context: RetrievalAccessContext,
        scope_type: str,
        scope_id: str,
        limit: int = 100,
        before_created_at: Optional[datetime] = None,
    ) -> ProjectionCoveragePage:
        if scope_type not in {"workspace", "group"}:
            raise ValueError("knowledge_projection_coverage_scope_invalid")
        if not (
            access_context.has_permission(
                "knowledge.read",
                scope_type=scope_type,
                scope_id=scope_id,
            )
            or access_context.has_permission(
                "knowledge.project",
                scope_type=scope_type,
                scope_id=scope_id,
            )
        ):
            raise PermissionError(
                "knowledge_projection_coverage_permission_required"
            )
        bounded_limit = max(1, min(int(limit), 200))
        core_rows = self._core.list_page(
            scope_type=scope_type,
            scope_id=scope_id,
            limit=bounded_limit,
            before_created_at=before_created_at,
        )
        vector_rows = self._vector_state(
            access_context=access_context,
            scope_type=scope_type,
            scope_id=scope_id,
            source_refs=tuple(
                str((row["metadata"] or {}).get("source_ref") or "")
                for row in core_rows
                if str((row["metadata"] or {}).get("source_ref") or "")
            ),
        )
        items = tuple(
            self._merge(row, vector_rows) for row in core_rows
        )
        return ProjectionCoveragePage(
            items=items,
            next_before_created_at=(
                items[-1].created_at
                if len(items) == bounded_limit
                else None
            ),
            limit=bounded_limit,
        )

    def _vector_state(
        self,
        *,
        access_context: RetrievalAccessContext,
        scope_type: str,
        scope_id: str,
        source_refs: tuple[str, ...],
    ) -> dict[tuple[str, str], dict[str, Any]]:
        if not source_refs:
            return {}
        connection = self._vector_connection_factory()
        try:
            cursor = connection.cursor()
            set_local_knowledge_context(cursor, access_context)
            cursor.execute(
                """
                SELECT
                    resource.source_ref,
                    resource.source_revision,
                    resource.active,
                    projection.status,
                    projection.active
                FROM knowledge_resources AS resource
                LEFT JOIN knowledge_resource_projections AS projection
                  ON projection.knowledge_resource_id =
                     resource.knowledge_resource_id
                 AND (
                     projection.active
                     OR projection.status = 'revoked'
                 )
                WHERE resource.owner_scope_type = %s
                  AND resource.owner_scope_id = %s
                  AND resource.source_ref = ANY(%s)
                ORDER BY
                    resource.source_ref,
                    projection.active DESC,
                    projection.activated_at DESC NULLS LAST
                """,
                (scope_type, scope_id, list(source_refs)),
            )
            rows = cursor.fetchall()
        finally:
            connection.close()
        states: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            key = (str(row[0]), str(row[1]))
            states.setdefault(
                key,
                {
                    "resource_active": bool(row[2]),
                    "projection_status": (
                        str(row[3]) if row[3] is not None else None
                    ),
                    "projection_active": bool(row[4]),
                },
            )
        return states

    @staticmethod
    def _merge(
        core_row: dict[str, Any],
        vector_rows: dict[tuple[str, str], dict[str, Any]],
    ) -> ProjectionCoverageItem:
        metadata = (
            core_row["metadata"]
            if isinstance(core_row["metadata"], dict)
            else {}
        )
        source_ref = str(metadata.get("source_ref") or "")
        vector = vector_rows.get(
            (source_ref, str(core_row["source_revision"])),
            {},
        )
        task_status = (
            str(core_row["task_status"])
            if core_row["task_status"] is not None
            else None
        )
        projection_status = vector.get("projection_status")
        projection_active = bool(vector.get("projection_active"))
        resource_active = bool(vector.get("resource_active"))
        trigger_mode = str(metadata.get("trigger_mode") or "")
        if (
            trigger_mode == "revoke"
            and not resource_active
            and projection_status == "revoked"
        ):
            state, reason = "revoked", None
        elif projection_active and projection_status == "active":
            state, reason = "active", None
        elif projection_active and projection_status in {
            "degraded_channels",
            "degraded_graph",
        }:
            state, reason = "degraded", projection_status
        elif task_status in {"pending", "running"}:
            state, reason = task_status, None
        elif task_status in {"failed", "cancelled", "cancelled_by_user"}:
            state, reason = "blocked", f"task_{task_status}"
        elif core_row["task_id"] is None:
            state, reason = "missing", "missing_projection_task"
        elif task_status == "succeeded":
            state, reason = "missing", "missing_active_projection"
        else:
            state, reason = "admitted", None
        return ProjectionCoverageItem(
            intake_id=str(core_row["intake_id"]),
            source_instance_id=str(core_row["source_instance_id"]),
            source_revision=str(core_row["source_revision"]),
            source_ref=source_ref,
            content_hash=str(core_row["content_hash"]),
            capability_code=str(metadata.get("capability_code") or ""),
            descriptor_id=str(metadata.get("descriptor_id") or ""),
            trigger_mode=trigger_mode,
            task_id=(
                str(core_row["task_id"])
                if core_row["task_id"] is not None
                else None
            ),
            task_status=task_status,
            projection_status=projection_status,
            projection_active=projection_active,
            resource_active=resource_active,
            state=state,
            reason=reason,
            created_at=core_row["created_at"],
        )


__all__ = [
    "ProjectionCoverageCoreRepository",
    "ProjectionCoverageItem",
    "ProjectionCoveragePage",
    "ProjectionCoverageService",
]
