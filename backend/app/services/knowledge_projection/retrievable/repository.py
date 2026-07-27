"""Projection/record/facet/evidence SQL leaves under the caller transaction."""

from __future__ import annotations

from typing import Any

from backend.app.services.knowledge_authorization.write_contracts import (
    KnowledgeResourceBinding,
    KnowledgeResourceIdentity,
)
from backend.app.services.knowledge_graph.repository import (
    KnowledgeGraphRepository,
)

from .identity import stable_projection_id
from .repository_contracts import ProjectionWriteConflictError
from .repository_rows import RetrievableKnowledgeProjectionRowsMixin
from .write_contracts import RetrievableProjectionWrite


class RetrievableKnowledgeProjectionRepository(
    RetrievableKnowledgeProjectionRowsMixin
):
    """Own pack-neutral projection rows; it never owns the transaction."""

    def __init__(
        self,
        graph_repository: KnowledgeGraphRepository | None = None,
    ) -> None:
        self._graph_repository = graph_repository or KnowledgeGraphRepository()

    def stage(
        self,
        cursor: Any,
        *,
        identity: KnowledgeResourceIdentity,
        binding: KnowledgeResourceBinding,
        payload: RetrievableProjectionWrite,
    ) -> tuple[str, bool, bool]:
        projection_id = stable_projection_id(
            "kpr",
            (
                binding.knowledge_resource_id,
                payload.source_revision,
                payload.content_hash,
                payload.projector_revision,
                payload.embedding_profile_revision,
                str(binding.authz_revision),
                binding.visibility_partition_hash,
            ),
        )
        cursor.execute(
            """
            SELECT
                projection_revision_id, projection_hash, active
            FROM knowledge_resource_projections
            WHERE knowledge_resource_id = %s
              AND source_revision = %s
              AND content_hash = %s
              AND projector_revision = %s
              AND embedding_profile_revision = %s
              AND authz_revision = %s
              AND visibility_partition_hash = %s
            FOR UPDATE
            """,
            (
                binding.knowledge_resource_id,
                payload.source_revision,
                payload.content_hash,
                payload.projector_revision,
                payload.embedding_profile_revision,
                binding.authz_revision,
                binding.visibility_partition_hash,
            ),
        )
        existing = cursor.fetchone()
        if existing is not None:
            if (
                str(existing[0]) != projection_id
                or str(existing[1]) != payload.projection_hash
            ):
                raise ProjectionWriteConflictError(
                    "knowledge_projection_idempotency_hash_conflict"
                )
            if not bool(existing[2]):
                self._restore_channel_receipts(
                    cursor,
                    projection_id=projection_id,
                    payload=payload,
                )
            return projection_id, False, bool(existing[2])

        cursor.execute(
            """
            INSERT INTO knowledge_resource_projections (
                projection_revision_id, knowledge_resource_id,
                source_instance_id, source_revision, content_hash,
                descriptor_id, descriptor_revision, projector_revision,
                facet_schema_revision, embedding_profile_revision,
                projection_hash, visibility_partition_hash, authz_revision,
                status, active, evidence_unit_count, record_count,
                relation_count
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, 'staged', FALSE, %s, %s, %s
            )
            """,
            (
                projection_id,
                binding.knowledge_resource_id,
                payload.source_instance_id,
                payload.source_revision,
                payload.content_hash,
                payload.descriptor_id,
                payload.descriptor_revision,
                payload.projector_revision,
                payload.facet_schema_revision,
                payload.embedding_profile_revision,
                payload.projection_hash,
                binding.visibility_partition_hash,
                binding.authz_revision,
                len(payload.evidence_units),
                len(payload.records),
                payload.relation_count,
            ),
        )
        record_rows = self._insert_records(
            cursor,
            projection_id=projection_id,
            resource_id=binding.knowledge_resource_id,
            payload=payload,
        )
        evidence_rows = self._insert_evidence_units(
            cursor,
            projection_id=projection_id,
            binding=binding,
            payload=payload,
        )
        self._insert_channels(
            cursor,
            projection_id=projection_id,
            evidence_rows=evidence_rows,
            payload=payload,
        )
        if payload.graph is not None:
            self._graph_repository.insert_generation(
                cursor,
                projection_revision_id=projection_id,
                identity=identity,
                binding=binding,
                graph=payload.graph,
                evidence_rows=evidence_rows,
                record_rows=record_rows,
            )
        return projection_id, True, False

    @staticmethod
    def rebind_active_authorization(
        cursor: Any,
        *,
        resource_id: str,
        authz_revision: int,
        visibility_partition_hash: str,
    ) -> bool:
        """Invalidate graph-derived visibility without rewriting provenance."""

        cursor.execute(
            """
            UPDATE knowledge_resource_projections
            SET status = 'degraded_graph'
            WHERE knowledge_resource_id = %s
              AND active
              AND relation_count > 0
            RETURNING relation_count
            """,
            (resource_id,),
        )
        rows = cursor.fetchall()
        graph_invalidated = any(int(row[0]) > 0 for row in rows)
        if graph_invalidated:
            cursor.execute(
                """
                UPDATE knowledge_graph_community_reports AS report
                SET active = FALSE
                FROM knowledge_graph_communities AS community
                WHERE report.community_id = community.community_id
                  AND community.knowledge_resource_id = %s
                  AND report.active
                """,
                (resource_id,),
            )
        return graph_invalidated

    @staticmethod
    def activate(
        cursor: Any,
        *,
        projection_id: str,
        resource_id: str,
        embedding_profile_revision: str,
        status: str = "active",
    ) -> None:
        if status not in {"active", "degraded_channels", "degraded_graph"}:
            raise ValueError("knowledge_projection_activation_status_forbidden")
        cursor.execute(
            """
            UPDATE knowledge_graph_community_reports AS report
            SET active = FALSE
            FROM knowledge_graph_communities AS community
            JOIN knowledge_resource_projections AS old_projection
              ON old_projection.projection_revision_id =
                 community.projection_revision_id
            WHERE report.community_id = community.community_id
              AND old_projection.knowledge_resource_id = %s
              AND old_projection.embedding_profile_revision = %s
              AND old_projection.active
              AND old_projection.projection_revision_id <> %s
            """,
            (resource_id, embedding_profile_revision, projection_id),
        )
        cursor.execute(
            """
            UPDATE knowledge_resource_projections
            SET active = FALSE,
                status = 'superseded',
                superseded_at = NOW()
            WHERE knowledge_resource_id = %s
              AND embedding_profile_revision = %s
              AND active
              AND projection_revision_id <> %s
            """,
            (resource_id, embedding_profile_revision, projection_id),
        )
        cursor.execute(
            """
            UPDATE knowledge_resource_projections
            SET active = TRUE,
                status = %s,
                activated_at = COALESCE(activated_at, NOW()),
                superseded_at = NULL
            WHERE projection_revision_id = %s
              AND knowledge_resource_id = %s
            RETURNING projection_revision_id
            """,
            (status, projection_id, resource_id),
        )
        row = cursor.fetchone()
        if row is None or str(row[0]) != projection_id:
            raise ProjectionWriteConflictError(
                "knowledge_projection_activation_failed"
            )
        cursor.execute(
            """
            UPDATE knowledge_graph_community_reports AS report
            SET active = TRUE
            FROM knowledge_graph_communities AS community
            WHERE report.community_id = community.community_id
              AND community.projection_revision_id = %s
            """,
            (projection_id,),
        )


__all__ = [
    "ProjectionWriteConflictError",
    "RetrievableKnowledgeProjectionRepository",
]
