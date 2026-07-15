"""Single owner-write seam for knowledge source checkpoints and intake receipts."""

import hashlib
import json
from typing import Any, Dict, Optional

from sqlalchemy import text

from backend.app.services.knowledge_projection.contracts import (
    KnowledgeSourceIntake,
    KnowledgeSourceIntakeReceipt,
)
from backend.app.services.stores.postgres_base import PostgresStoreBase


_SECRET_KEY_FRAGMENTS = (
    "api_key",
    "authorization",
    "credential",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "token",
)
_MAX_LEDGER_JSON_BYTES = 64 * 1024


class KnowledgeSourceOwnershipError(PermissionError):
    pass


class KnowledgeSourcePayloadError(ValueError):
    pass


class KnowledgeSourceLedgerRepository(PostgresStoreBase):
    """Bounded PostgreSQL transaction; source connectors remain capability-owned."""

    def record_intake(
        self,
        intake: KnowledgeSourceIntake,
        *,
        intake_id: str,
    ) -> KnowledgeSourceIntakeReceipt:
        with self.transaction() as conn:
            state = conn.execute(
                text(
                    """
                    WITH inserted AS (
                        INSERT INTO knowledge_source_states (
                            source_instance_id, owner_type, owner_id, binding_id,
                            visibility
                        ) VALUES (
                            :source_instance_id, :owner_type, :owner_id,
                            :binding_id, :visibility
                        )
                        ON CONFLICT (source_instance_id) DO NOTHING
                        RETURNING owner_type, owner_id
                    )
                    SELECT owner_type, owner_id FROM inserted
                    UNION ALL
                    SELECT owner_type, owner_id
                    FROM knowledge_source_states
                    WHERE source_instance_id = :source_instance_id
                    LIMIT 1
                    """
                ),
                intake.model_dump(
                    include={
                        "source_instance_id",
                        "owner_type",
                        "owner_id",
                        "binding_id",
                        "visibility",
                    }
                ),
            ).fetchone()
            if (
                state is None
                or state.owner_type != intake.owner_type
                or state.owner_id != intake.owner_id
            ):
                raise KnowledgeSourceOwnershipError(
                    f"source owner mismatch: {intake.source_instance_id}"
                )

            inserted = conn.execute(
                text(
                    """
                    INSERT INTO knowledge_source_intakes (
                        id, source_instance_id, source_revision, content_hash,
                        evidence_type, evidence_id, metadata
                    ) VALUES (
                        :id, :source_instance_id, :source_revision, :content_hash,
                        :evidence_type, :evidence_id, CAST(:metadata AS jsonb)
                    )
                    ON CONFLICT (
                        source_instance_id, source_revision, content_hash
                    ) DO NOTHING
                    RETURNING id
                    """
                ),
                {
                    "id": intake_id,
                    "source_instance_id": intake.source_instance_id,
                    "source_revision": intake.source_revision,
                    "content_hash": intake.content_hash,
                    "evidence_type": intake.evidence_type,
                    "evidence_id": intake.evidence_id,
                    "metadata": self.serialize_json(intake.metadata),
                },
            ).fetchone()
            created = inserted is not None
            if created:
                conn.execute(
                    text(
                        """
                        UPDATE knowledge_source_states
                        SET binding_id = :binding_id,
                            cursor = CAST(:cursor AS jsonb),
                            checkpoint = CAST(:checkpoint AS jsonb),
                            last_evidence_revision = :source_revision,
                            last_result = CAST(:last_result AS jsonb),
                            visibility = :visibility,
                            updated_at = NOW()
                        WHERE source_instance_id = :source_instance_id
                          AND owner_type = :owner_type
                          AND owner_id = :owner_id
                        """
                    ),
                    {
                        "source_instance_id": intake.source_instance_id,
                        "owner_type": intake.owner_type,
                        "owner_id": intake.owner_id,
                        "binding_id": intake.binding_id,
                        "source_revision": intake.source_revision,
                        "cursor": self.serialize_json(intake.cursor),
                        "checkpoint": self.serialize_json(intake.checkpoint),
                        "last_result": self.serialize_json(intake.last_result),
                        "visibility": intake.visibility,
                    },
                )
            else:
                existing = conn.execute(
                    text(
                        """
                        SELECT id FROM knowledge_source_intakes
                        WHERE source_instance_id = :source_instance_id
                          AND source_revision = :source_revision
                          AND content_hash = :content_hash
                        """
                    ),
                    {
                        "source_instance_id": intake.source_instance_id,
                        "source_revision": intake.source_revision,
                        "content_hash": intake.content_hash,
                    },
                ).fetchone()
                if existing is None:
                    raise RuntimeError("knowledge source intake conflict lookup failed")
                intake_id = existing.id

        return KnowledgeSourceIntakeReceipt(
            intake_id=intake_id,
            source_instance_id=intake.source_instance_id,
            source_revision=intake.source_revision,
            content_hash=intake.content_hash,
            created=created,
        )


class KnowledgeSourceLedgerFacade:
    def __init__(
        self,
        repository: Optional[KnowledgeSourceLedgerRepository] = None,
    ) -> None:
        self.repository = repository or KnowledgeSourceLedgerRepository()

    def record_intake(
        self,
        intake: KnowledgeSourceIntake,
    ) -> KnowledgeSourceIntakeReceipt:
        self._validate_bounded_nonsecret_payload(intake)
        intake_id = "ksi_" + hashlib.sha256(
            (
                f"{intake.source_instance_id}\0{intake.source_revision}\0"
                f"{intake.content_hash}"
            ).encode("utf-8")
        ).hexdigest()[:32]
        return self.repository.record_intake(intake, intake_id=intake_id)

    @staticmethod
    def _validate_bounded_nonsecret_payload(intake: KnowledgeSourceIntake) -> None:
        bounded_payload = {
            "cursor": intake.cursor,
            "checkpoint": intake.checkpoint,
            "last_result": intake.last_result,
            "metadata": intake.metadata,
        }
        secret_path = _find_secret_key(bounded_payload)
        if secret_path:
            raise KnowledgeSourcePayloadError(
                f"secret-like field is not allowed in ledger payload: {secret_path}"
            )
        encoded = json.dumps(
            bounded_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > _MAX_LEDGER_JSON_BYTES:
            raise KnowledgeSourcePayloadError(
                f"ledger metadata exceeds {_MAX_LEDGER_JSON_BYTES} bytes"
            )


def _find_secret_key(value: Any, path: str = "") -> Optional[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            child_path = f"{path}.{key}" if path else str(key)
            if any(fragment in normalized for fragment in _SECRET_KEY_FRAGMENTS):
                return child_path
            found = _find_secret_key(child, child_path)
            if found:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _find_secret_key(child, f"{path}[{index}]")
            if found:
                return found
    return None
