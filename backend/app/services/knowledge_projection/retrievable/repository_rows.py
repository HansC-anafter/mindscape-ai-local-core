"""Record, facet, evidence, and channel SQL leaves."""

from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from backend.app.services.knowledge_authorization.write_contracts import (
    KnowledgeResourceBinding,
)

from .identity import stable_projection_id
from .repository_contracts import ProjectionWriteConflictError
from .write_contracts import RetrievableProjectionWrite


def _json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


class RetrievableKnowledgeProjectionRowsMixin:
    @staticmethod
    def _insert_records(
        cursor: Any,
        *,
        projection_id: str,
        resource_id: str,
        payload: RetrievableProjectionWrite,
    ) -> dict[str, str]:
        rows: dict[str, str] = {}
        for record in payload.records:
            record_id = stable_projection_id(
                "krec",
                (projection_id, record.record_kind, record.record_key),
            )
            rows[record.record_key] = record_id
            cursor.execute(
                """
                INSERT INTO knowledge_projection_records (
                    projection_record_id, projection_revision_id,
                    knowledge_resource_id, record_kind, record_key,
                    search_text, citation, values, content_hash
                ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
                """,
                (
                    record_id,
                    projection_id,
                    resource_id,
                    record.record_kind,
                    record.record_key,
                    record.search_text,
                    _json(record.citation),
                    _json(record.values),
                    record.content_hash,
                ),
            )
            for facet in record.facets:
                value_columns: dict[str, Any] = {
                    "text": None,
                    "number": None,
                    "bool": None,
                    "timestamp": None,
                    "ref": None,
                }
                if facet.value_type in {"string", "enum"}:
                    value_columns["text"] = str(facet.value)
                elif facet.value_type == "number":
                    value_columns["number"] = facet.value
                elif facet.value_type == "boolean":
                    value_columns["bool"] = bool(facet.value)
                elif facet.value_type == "timestamp":
                    value_columns["timestamp"] = (
                        facet.value
                        if isinstance(facet.value, datetime)
                        else datetime.fromisoformat(str(facet.value))
                    )
                elif facet.value_type == "ref":
                    value_columns["ref"] = str(facet.value)
                else:
                    raise ValueError(
                        "knowledge_projection_facet_type_forbidden"
                    )
                cursor.execute(
                    """
                    INSERT INTO knowledge_projection_facets (
                        projection_facet_id, projection_record_id,
                        facet_key, facet_type, text_value, number_value,
                        bool_value, timestamp_value, ref_value, ordinal
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        stable_projection_id(
                            "kfacet",
                            (record_id, facet.key, str(facet.ordinal)),
                        ),
                        record_id,
                        facet.key,
                        facet.value_type,
                        value_columns["text"],
                        value_columns["number"],
                        value_columns["bool"],
                        value_columns["timestamp"],
                        value_columns["ref"],
                        facet.ordinal,
                    ),
                )
        return rows

    @staticmethod
    def _insert_evidence_units(
        cursor: Any,
        *,
        projection_id: str,
        binding: KnowledgeResourceBinding,
        payload: RetrievableProjectionWrite,
    ) -> dict[str, str]:
        rows: dict[str, str] = {}
        for unit in payload.evidence_units:
            row_id = stable_projection_id(
                "keu",
                (projection_id, unit.unit_key),
            )
            rows[unit.unit_key] = row_id
            cursor.execute(
                """
                INSERT INTO knowledge_evidence_units (
                    evidence_unit_row_id, projection_revision_id,
                    knowledge_resource_id, security_label_id, unit_key,
                    unit_kind, owner_asset_ref, content_hash, media_type,
                    anchor, derivative_refs
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s::jsonb, %s::jsonb
                )
                """,
                (
                    row_id,
                    projection_id,
                    binding.knowledge_resource_id,
                    binding.security_label_id,
                    unit.unit_key,
                    unit.unit_kind,
                    unit.owner_asset_ref,
                    unit.content_hash,
                    unit.media_type,
                    _json(unit.anchor),
                    _json(unit.derivative_refs),
                ),
            )
        return rows

    @staticmethod
    def _insert_channels(
        cursor: Any,
        *,
        projection_id: str,
        evidence_rows: dict[str, str],
        payload: RetrievableProjectionWrite,
    ) -> None:
        for channel in payload.channels:
            evidence_row_id = evidence_rows[channel.unit_key]
            cursor.execute(
                """
                INSERT INTO knowledge_embedding_channel_receipts (
                    channel_receipt_id, projection_revision_id,
                    evidence_unit_row_id, channel_id, modality,
                    profile_revision, model_revision, dimension,
                    calibration_revision, index_revision, required,
                    state, row_count, byte_count, reason, physical_store_ref
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    stable_projection_id(
                        "kcr",
                        (projection_id, evidence_row_id, channel.channel_id),
                    ),
                    projection_id,
                    evidence_row_id,
                    channel.channel_id,
                    channel.modality,
                    channel.profile_revision,
                    channel.model_revision,
                    channel.dimension,
                    channel.calibration_revision,
                    channel.index_revision,
                    channel.required,
                    channel.state,
                    channel.row_count,
                    channel.byte_count,
                    channel.reason,
                    channel.physical_store_ref,
                ),
            )

    @staticmethod
    def _restore_channel_receipts(
        cursor: Any,
        *,
        projection_id: str,
        payload: RetrievableProjectionWrite,
    ) -> None:
        """Restore declared channel receipts for explicit reindex."""

        cursor.execute(
            """
            SELECT unit_key, evidence_unit_row_id
            FROM knowledge_evidence_units
            WHERE projection_revision_id = %s
            """,
            (projection_id,),
        )
        evidence_rows = {
            str(row[0]): str(row[1]) for row in cursor.fetchall()
        }
        for channel in payload.channels:
            evidence_row_id = evidence_rows.get(channel.unit_key)
            if evidence_row_id is None:
                raise ProjectionWriteConflictError(
                    "knowledge_projection_restore_evidence_missing"
                )
            cursor.execute(
                """
                UPDATE knowledge_embedding_channel_receipts
                SET modality = %s,
                    profile_revision = %s,
                    model_revision = %s,
                    dimension = %s,
                    calibration_revision = %s,
                    index_revision = %s,
                    required = %s,
                    state = %s,
                    row_count = %s,
                    byte_count = %s,
                    reason = %s,
                    physical_store_ref = %s
                WHERE projection_revision_id = %s
                  AND evidence_unit_row_id = %s
                  AND channel_id = %s
                RETURNING channel_receipt_id
                """,
                (
                    channel.modality,
                    channel.profile_revision,
                    channel.model_revision,
                    channel.dimension,
                    channel.calibration_revision,
                    channel.index_revision,
                    channel.required,
                    channel.state,
                    channel.row_count,
                    channel.byte_count,
                    channel.reason,
                    channel.physical_store_ref,
                    projection_id,
                    evidence_row_id,
                    channel.channel_id,
                ),
            )
            if cursor.fetchone() is None:
                raise ProjectionWriteConflictError(
                    "knowledge_projection_restore_channel_missing"
                )


__all__ = ["RetrievableKnowledgeProjectionRowsMixin"]
