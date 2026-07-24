"""PostgreSQL singleton state and atomic deployment-envelope replacement."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase

from .contracts import (
    DeploymentControlState,
    SignedDeploymentCapabilityEnvelope,
)
from .errors import (
    DeploymentCatalogConflict,
    DeploymentControlStateRevisionConflict,
    DeploymentEnvelopeRevisionConflict,
)


class DeploymentControlStateRepository(PostgresStoreBase):
    SINGLETON_ID = 1

    def get_active_catalog_hash(self) -> str:
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT catalog_hash
                    FROM product_capability_catalog_versions
                    WHERE status = 'active'
                    """
                )
            ).fetchone()
        if row is None:
            raise DeploymentCatalogConflict("", "")
        return str(row.catalog_hash)

    def get_state(self) -> DeploymentControlState:
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT mode, provider_code, active_envelope, envelope_hash,
                           issuer, key_id, expires_at, envelope_revision,
                           state_revision, updated_at, updated_by
                    FROM deployment_control_state
                    WHERE id = :singleton_id
                    """
                ),
                {"singleton_id": self.SINGLETON_ID},
            ).fetchone()
        return self._row_to_state(row)

    def replace(
        self,
        *,
        expected_state_revision: int,
        mode: str,
        provider_code: str | None,
        envelope: SignedDeploymentCapabilityEnvelope | None,
        envelope_hash: str | None,
        actor_user_id: str,
    ) -> tuple[DeploymentControlState, bool]:
        with self.transaction() as conn:
            current = conn.execute(
                text(
                    """
                    SELECT mode, provider_code, active_envelope, envelope_hash,
                           issuer, key_id, expires_at, envelope_revision,
                           state_revision, updated_at, updated_by
                    FROM deployment_control_state
                    WHERE id = :singleton_id
                    FOR UPDATE
                    """
                ),
                {"singleton_id": self.SINGLETON_ID},
            ).fetchone()
            current_state = self._row_to_state(current)
            if (
                mode == current_state.mode
                and envelope_hash == current_state.envelope_hash
                and provider_code == current_state.provider_code
            ):
                return current_state, False
            if current_state.state_revision != expected_state_revision:
                raise DeploymentControlStateRevisionConflict(
                    expected_state_revision,
                    current_state.state_revision,
                )

            if envelope is not None:
                catalog_row = conn.execute(
                    text(
                        """
                        SELECT catalog_hash
                        FROM product_capability_catalog_versions
                        WHERE status = 'active'
                        FOR SHARE
                        """
                    )
                ).fetchone()
                current_catalog = (
                    str(catalog_row.catalog_hash) if catalog_row else ""
                )
                if envelope.claims.catalog_hash != current_catalog:
                    raise DeploymentCatalogConflict(
                        envelope.claims.catalog_hash,
                        current_catalog,
                    )
                previous_revision = current_state.envelope_revision or 0
                if envelope.claims.envelope_revision <= previous_revision:
                    raise DeploymentEnvelopeRevisionConflict(
                        previous_revision,
                        envelope.claims.envelope_revision,
                    )

            new_revision = current_state.state_revision + 1
            params = self._replacement_params(
                mode=mode,
                provider_code=provider_code,
                envelope=envelope,
                envelope_hash=envelope_hash,
                state_revision=new_revision,
                actor_user_id=actor_user_id,
            )
            if current is None:
                inserted = conn.execute(
                    text(
                        """
                        INSERT INTO deployment_control_state
                            (id, mode, provider_code, active_envelope,
                             envelope_hash, issuer, key_id, expires_at,
                             envelope_revision, state_revision, updated_by)
                        VALUES
                            (:singleton_id, :mode, :provider_code,
                             CAST(:active_envelope AS jsonb), :envelope_hash,
                             :issuer, :key_id, :expires_at,
                             :envelope_revision, :state_revision, :updated_by)
                        ON CONFLICT (id) DO NOTHING
                        RETURNING state_revision
                        """
                    ),
                    {"singleton_id": self.SINGLETON_ID, **params},
                ).fetchone()
                if inserted is None:
                    concurrent = conn.execute(
                        text(
                            """
                            SELECT state_revision
                            FROM deployment_control_state
                            WHERE id = :singleton_id
                            FOR UPDATE
                            """
                        ),
                        {"singleton_id": self.SINGLETON_ID},
                    ).fetchone()
                    raise DeploymentControlStateRevisionConflict(
                        expected_state_revision,
                        int(concurrent.state_revision),
                    )
            else:
                conn.execute(
                    text(
                        """
                        UPDATE deployment_control_state
                        SET mode = :mode,
                            provider_code = :provider_code,
                            active_envelope = CAST(:active_envelope AS jsonb),
                            envelope_hash = :envelope_hash,
                            issuer = :issuer,
                            key_id = :key_id,
                            expires_at = :expires_at,
                            envelope_revision = :envelope_revision,
                            state_revision = :state_revision,
                            updated_at = NOW(),
                            updated_by = :updated_by
                        WHERE id = :singleton_id
                        """
                    ),
                    {"singleton_id": self.SINGLETON_ID, **params},
                )
            row = conn.execute(
                text(
                    """
                    SELECT mode, provider_code, active_envelope, envelope_hash,
                           issuer, key_id, expires_at, envelope_revision,
                           state_revision, updated_at, updated_by
                    FROM deployment_control_state
                    WHERE id = :singleton_id
                    """
                ),
                {"singleton_id": self.SINGLETON_ID},
            ).fetchone()
        return self._row_to_state(row), True

    def _replacement_params(
        self,
        *,
        mode: str,
        provider_code: str | None,
        envelope: SignedDeploymentCapabilityEnvelope | None,
        envelope_hash: str | None,
        state_revision: int,
        actor_user_id: str,
    ) -> dict[str, Any]:
        claims = envelope.claims if envelope else None
        return {
            "mode": mode,
            "provider_code": provider_code,
            "active_envelope": self.serialize_json(
                envelope.model_dump(mode="json") if envelope else None
            ),
            "envelope_hash": envelope_hash,
            "issuer": claims.issuer if claims else None,
            "key_id": envelope.kid if envelope else None,
            "expires_at": claims.expires_at if claims else None,
            "envelope_revision": claims.envelope_revision if claims else None,
            "state_revision": state_revision,
            "updated_by": actor_user_id,
        }

    def _row_to_state(self, row: Any) -> DeploymentControlState:
        if row is None:
            return DeploymentControlState(
                mode="unmanaged_local",
                state_revision=0,
            )
        envelope_payload = self.deserialize_json(
            row.active_envelope,
            default=None,
        )
        return DeploymentControlState(
            mode=row.mode,
            provider_code=row.provider_code,
            signed_envelope=(
                SignedDeploymentCapabilityEnvelope.model_validate(
                    envelope_payload
                )
                if envelope_payload
                else None
            ),
            envelope_hash=row.envelope_hash,
            issuer=row.issuer,
            key_id=row.key_id,
            expires_at=row.expires_at,
            envelope_revision=row.envelope_revision,
            state_revision=int(row.state_revision),
            updated_at=row.updated_at,
            updated_by=row.updated_by,
        )
