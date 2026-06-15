from __future__ import annotations

import logging
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from ..postgres_base import PostgresStoreBase
from app.models.surface import Command, CommandStatus, SurfaceEvent
from app.models.workspace import ConversationThread, PlaybookExecution, ThreadReference
from app.models.lens_composition import LensComposition, LensReference

from .remaining_store_utils import _utc_now

logger = logging.getLogger(__name__)


class PostgresThreadReferencesStore(PostgresStoreBase):
    def create_reference(self, reference: ThreadReference) -> ThreadReference:
        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO thread_references (
                    id, workspace_id, thread_id, source_type, uri, title,
                    snippet, reason, pinned_by, created_at, updated_at
                ) VALUES (
                    :id, :workspace_id, :thread_id, :source_type, :uri, :title,
                    :snippet, :reason, :pinned_by, :created_at, :updated_at
                )
            """
            )
            conn.execute(
                query,
                {
                    "id": reference.id,
                    "workspace_id": reference.workspace_id,
                    "thread_id": reference.thread_id,
                    "source_type": reference.source_type,
                    "uri": reference.uri,
                    "title": reference.title,
                    "snippet": reference.snippet,
                    "reason": reference.reason,
                    "pinned_by": reference.pinned_by,
                    "created_at": reference.created_at,
                    "updated_at": reference.updated_at,
                },
            )
            return reference

    def get_by_thread(
        self, workspace_id: str, thread_id: str, limit: int = 100
    ) -> List[ThreadReference]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM thread_references WHERE workspace_id=:wid AND thread_id=:tid ORDER BY created_at DESC LIMIT :lim"
                ),
                {"wid": workspace_id, "tid": thread_id, "lim": limit},
            ).fetchall()
            return [self._row_to_reference(row) for row in rows]

    def _row_to_reference(self, row) -> ThreadReference:
        return ThreadReference(
            id=row.id,
            workspace_id=row.workspace_id,
            thread_id=row.thread_id,
            source_type=row.source_type,
            uri=row.uri,
            title=row.title,
            snippet=row.snippet,
            reason=row.reason,
            pinned_by=row.pinned_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def delete_reference(self, reference_id: str) -> bool:
        with self.transaction() as conn:
            return (
                conn.execute(
                    text("DELETE FROM thread_references WHERE id=:id"),
                    {"id": reference_id},
                ).rowcount
                > 0
            )
