"""Core-ledger lookup for revision-checked projection actions."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from backend.app.services.knowledge_projection.retrievable.source_admission import (
    RetrievableSourceAdmissionCommand,
)
from backend.app.services.stores.postgres_base import PostgresStoreBase


class KnowledgeProjectionActionSourceRepository(PostgresStoreBase):
    """Resolve only an already-admitted, exact source revision."""

    def resolve(
        self,
        *,
        workspace_id: str,
        source_instance_id: str,
        source_revision: str,
        owner_capability_code: str,
        source_kind: str,
        source_ref: str,
        trigger_mode: str,
    ) -> RetrievableSourceAdmissionCommand | None:
        with self.transaction() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                        intake.source_instance_id,
                        intake.source_revision,
                        intake.content_hash,
                        intake.evidence_type,
                        intake.evidence_id,
                        intake.metadata,
                        state.checkpoint
                    FROM knowledge_source_intakes AS intake
                    JOIN knowledge_source_states AS state
                      ON state.source_instance_id =
                         intake.source_instance_id
                    WHERE intake.source_instance_id = :source_instance_id
                      AND intake.source_revision = :source_revision
                      AND state.owner_type = 'workspace'
                      AND state.owner_id = :workspace_id
                    ORDER BY intake.created_at DESC, intake.id DESC
                    LIMIT 1
                    """
                ),
                {
                    "source_instance_id": source_instance_id,
                    "source_revision": source_revision,
                    "workspace_id": workspace_id,
                },
            ).mappings().first()
        if row is None:
            return None
        metadata = (
            dict(row["metadata"])
            if isinstance(row["metadata"], dict)
            else {}
        )
        if (
            metadata.get("capability_code") != owner_capability_code
            or metadata.get("source_kind") != source_kind
            or metadata.get("source_ref") != source_ref
            or metadata.get("workspace_id", workspace_id) != workspace_id
            or metadata.get("group_id") not in (None, "")
        ):
            raise ValueError(
                "knowledge_projection_action_source_identity_mismatch"
            )
        required = (
            "capability_version",
            "descriptor_id",
            "descriptor_hash",
            "manifest_hash",
        )
        if any(not metadata.get(field) for field in required):
            raise ValueError(
                "knowledge_projection_action_source_descriptor_incomplete"
            )
        return RetrievableSourceAdmissionCommand(
            capability_code=owner_capability_code,
            capability_version=str(metadata["capability_version"]),
            descriptor_id=str(metadata["descriptor_id"]),
            descriptor_hash=str(metadata["descriptor_hash"]),
            manifest_hash=str(metadata["manifest_hash"]),
            source_kind=source_kind,
            source_instance_id=str(row["source_instance_id"]),
            source_ref=source_ref,
            source_revision=str(row["source_revision"]),
            content_hash=str(row["content_hash"]),
            evidence_type=str(row["evidence_type"]),
            evidence_id=str(row["evidence_id"]),
            workspace_id=workspace_id,
            object_kind=(
                str(metadata["object_kind"])
                if metadata.get("object_kind")
                else None
            ),
            artifact_selector=(
                str(metadata["artifact_selector"])
                if metadata.get("artifact_selector")
                else None
            ),
            trigger_mode=trigger_mode,
            checkpoint=(
                dict(row["checkpoint"])
                if isinstance(row["checkpoint"], dict)
                else {}
            ),
            auto_triggered=False,
        )


__all__ = ["KnowledgeProjectionActionSourceRepository"]
