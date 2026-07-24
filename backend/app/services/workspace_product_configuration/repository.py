"""PostgreSQL statements for PCS catalog and WPC scopes."""

from __future__ import annotations

from typing import Any, Sequence
from uuid import uuid4

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase

from .contracts import CatalogArtifactEnvelope, ProductAssignment, ScopeKind
from .errors import ActiveCatalogMissingError, ScopeRevisionConflictError


class WorkspaceProductConfigurationRepository(PostgresStoreBase):
    """One catalog materialization, one CAS writer, and bounded aggregate reads."""

    def import_catalog(
        self,
        artifact: CatalogArtifactEnvelope,
        *,
        actor_user_id: str,
    ) -> bool:
        artifact_payload = artifact.model_dump(mode="json")
        serialized = self.serialize_json(artifact_payload)
        imported = False
        with self.transaction() as conn:
            existing = conn.execute(
                text(
                    """
                    SELECT artifact_json, status
                    FROM product_capability_catalog_versions
                    WHERE artifact_hash = :artifact_hash
                    FOR UPDATE
                    """
                ),
                {"artifact_hash": artifact.artifact_hash},
            ).fetchone()
            if existing is not None:
                current_payload = self.deserialize_json(
                    existing.artifact_json,
                    default={},
                )
                if current_payload != artifact_payload:
                    raise ValueError("catalog_artifact_hash_content_conflict")
                if existing.status == "active":
                    return False

            conn.execute(
                text(
                    """
                    UPDATE product_capability_catalog_versions
                    SET status = 'inactive'
                    WHERE status = 'active'
                    """
                )
            )
            if existing is None:
                conn.execute(
                    text(
                        """
                        INSERT INTO product_capability_catalog_versions
                            (artifact_hash, catalog_hash, source_commit,
                             compiler_version, artifact_json, status, imported_by)
                        VALUES
                            (:artifact_hash, :catalog_hash, :source_commit,
                             :compiler_version, CAST(:artifact_json AS jsonb),
                             'active', :imported_by)
                        """
                    ),
                    {
                        "artifact_hash": artifact.artifact_hash,
                        "catalog_hash": artifact.catalog_hash,
                        "source_commit": artifact.source_commit,
                        "compiler_version": artifact.compiler_version,
                        "artifact_json": serialized,
                        "imported_by": actor_user_id,
                    },
                )
                imported = True
            else:
                conn.execute(
                    text(
                        """
                        UPDATE product_capability_catalog_versions
                        SET status = 'active', imported_by = :imported_by,
                            imported_at = NOW()
                        WHERE artifact_hash = :artifact_hash
                        """
                    ),
                    {
                        "artifact_hash": artifact.artifact_hash,
                        "imported_by": actor_user_id,
                    },
                )
        return imported

    def load_effective_state(
        self,
        *,
        workspace_id: str,
        group_id: str | None,
    ) -> dict[str, Any]:
        """Load active catalog plus workspace/explicit-group scopes in one statement."""
        with self.get_connection() as conn:
            row = conn.execute(
                text(
                    """
                    WITH active_catalog AS (
                        SELECT artifact_hash, catalog_hash, source_commit,
                               compiler_version, artifact_json
                        FROM product_capability_catalog_versions
                        WHERE status = 'active'
                        LIMIT 1
                    ),
                    selected_scopes AS (
                        SELECT
                            scope.scope_kind,
                            scope.scope_id,
                            scope.catalog_hash,
                            scope.revision,
                            scope.admission_mode,
                            COALESCE(
                                (
                                    SELECT jsonb_agg(
                                        jsonb_build_object(
                                            'pcs_id', assignment.pcs_id,
                                            'pcs_version', assignment.pcs_version
                                        )
                                        ORDER BY assignment.pcs_id
                                    )
                                    FROM workspace_product_configuration_assignments
                                        AS assignment
                                    WHERE assignment.scope_kind = scope.scope_kind
                                      AND assignment.scope_id = scope.scope_id
                                ),
                                '[]'::jsonb
                            ) AS assignments
                        FROM workspace_product_configuration_scopes AS scope
                        WHERE (
                            scope.scope_kind = 'workspace'
                            AND scope.scope_id = :workspace_id
                        ) OR (
                            :group_id IS NOT NULL
                            AND scope.scope_kind = 'workspace_group'
                            AND scope.scope_id = :group_id
                        )
                    )
                    SELECT
                        (SELECT artifact_hash FROM active_catalog) AS artifact_hash,
                        (SELECT catalog_hash FROM active_catalog) AS catalog_hash,
                        (SELECT source_commit FROM active_catalog) AS source_commit,
                        (SELECT compiler_version FROM active_catalog)
                            AS compiler_version,
                        (SELECT artifact_json FROM active_catalog) AS artifact_json,
                        COALESCE(
                            (
                                SELECT jsonb_agg(
                                    jsonb_build_object(
                                        'scope_kind', scope_kind,
                                        'scope_id', scope_id,
                                        'catalog_hash', catalog_hash,
                                        'revision', revision,
                                        'admission_mode', admission_mode,
                                        'assignments', assignments
                                    )
                                    ORDER BY scope_kind, scope_id
                                )
                                FROM selected_scopes
                            ),
                            '[]'::jsonb
                        ) AS scopes
                    """
                ),
                {"workspace_id": workspace_id, "group_id": group_id},
            ).fetchone()
        return {
            "artifact_hash": row.artifact_hash,
            "catalog_hash": row.catalog_hash,
            "source_commit": row.source_commit,
            "compiler_version": row.compiler_version,
            "artifact": self.deserialize_json(row.artifact_json, default={}),
            "scopes": self.deserialize_json(row.scopes, default=[]),
        }

    def load_pack_readiness(
        self,
        pack_codes: Sequence[str],
    ) -> dict[str, dict[str, Any]]:
        if not pack_codes:
            return {}
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        pack_id,
                        enabled,
                        COALESCE(
                            metadata ->> 'version',
                            metadata -> 'manifest' ->> 'version',
                            ''
                        ) AS version
                    FROM installed_packs
                    WHERE pack_id = ANY(CAST(:pack_codes AS varchar[]))
                    """
                ),
                {"pack_codes": sorted(set(pack_codes))},
            ).fetchall()
        return {
            row.pack_id: {
                "enabled": bool(row.enabled),
                "version": str(row.version or ""),
            }
            for row in rows
        }

    def replace_scope(
        self,
        *,
        scope_kind: ScopeKind,
        scope_id: str,
        expected_revision: int,
        catalog_hash: str,
        admission_mode: str | None,
        assignments: list[ProductAssignment],
        actor_user_id: str,
    ) -> dict[str, Any]:
        with self.transaction() as conn:
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
            if catalog_row is None:
                raise ActiveCatalogMissingError()
            if catalog_row.catalog_hash != catalog_hash:
                raise ValueError("product_catalog_revision_conflict")

            existing = conn.execute(
                text(
                    """
                    SELECT revision
                    FROM workspace_product_configuration_scopes
                    WHERE scope_kind = :scope_kind AND scope_id = :scope_id
                    FOR UPDATE
                    """
                ),
                {"scope_kind": scope_kind, "scope_id": scope_id},
            ).fetchone()
            actual_revision = int(existing.revision) if existing else 0
            if actual_revision != expected_revision:
                raise ScopeRevisionConflictError(
                    expected_revision=expected_revision,
                    actual_revision=actual_revision,
                )
            new_revision = actual_revision + 1
            if existing is None:
                conn.execute(
                    text(
                        """
                        INSERT INTO workspace_product_configuration_scopes
                            (scope_kind, scope_id, catalog_hash, revision,
                             admission_mode, updated_by)
                        VALUES
                            (:scope_kind, :scope_id, :catalog_hash, :revision,
                             :admission_mode, :updated_by)
                        """
                    ),
                    {
                        "scope_kind": scope_kind,
                        "scope_id": scope_id,
                        "catalog_hash": catalog_hash,
                        "revision": new_revision,
                        "admission_mode": admission_mode,
                        "updated_by": actor_user_id,
                    },
                )
            else:
                conn.execute(
                    text(
                        """
                        UPDATE workspace_product_configuration_scopes
                        SET catalog_hash = :catalog_hash,
                            revision = :revision,
                            admission_mode = :admission_mode,
                            updated_by = :updated_by,
                            updated_at = NOW()
                        WHERE scope_kind = :scope_kind AND scope_id = :scope_id
                        """
                    ),
                    {
                        "scope_kind": scope_kind,
                        "scope_id": scope_id,
                        "catalog_hash": catalog_hash,
                        "revision": new_revision,
                        "admission_mode": admission_mode,
                        "updated_by": actor_user_id,
                    },
                )
            conn.execute(
                text(
                    """
                    DELETE FROM workspace_product_configuration_assignments
                    WHERE scope_kind = :scope_kind AND scope_id = :scope_id
                    """
                ),
                {"scope_kind": scope_kind, "scope_id": scope_id},
            )
            if assignments:
                conn.execute(
                    text(
                        """
                        INSERT INTO workspace_product_configuration_assignments
                            (scope_kind, scope_id, pcs_id, pcs_version)
                        VALUES
                            (:scope_kind, :scope_id, :pcs_id, :pcs_version)
                        """
                    ),
                    [
                        {
                            "scope_kind": scope_kind,
                            "scope_id": scope_id,
                            **assignment.model_dump(),
                        }
                        for assignment in assignments
                    ],
                )
            serialized_assignments = self.serialize_json(
                [assignment.model_dump() for assignment in assignments]
            )
            conn.execute(
                text(
                    """
                    INSERT INTO workspace_product_configuration_receipts
                        (id, scope_kind, scope_id, previous_revision, new_revision,
                         catalog_hash, admission_mode, assignments, actor_user_id)
                    VALUES
                        (:id, :scope_kind, :scope_id, :previous_revision,
                         :new_revision, :catalog_hash, :admission_mode,
                         CAST(:assignments AS jsonb), :actor_user_id)
                    """
                ),
                {
                    "id": f"wpcr_{uuid4().hex}",
                    "scope_kind": scope_kind,
                    "scope_id": scope_id,
                    "previous_revision": actual_revision,
                    "new_revision": new_revision,
                    "catalog_hash": catalog_hash,
                    "admission_mode": admission_mode,
                    "assignments": serialized_assignments,
                    "actor_user_id": actor_user_id,
                },
            )
        return {
            "scope_kind": scope_kind,
            "scope_id": scope_id,
            "revision": new_revision,
            "catalog_hash": catalog_hash,
            "admission_mode": admission_mode,
            "assignments": assignments,
        }
