"""One-statement evidence read for workspace-group shared asset scopes."""

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase


@dataclass(frozen=True)
class SharedAssetScopeEvidence:
    """Raw evidence needed to decide one configured shared-asset scope."""

    binding_id: Optional[str]
    active_workspace_id: str
    active_workspace_owner_user_id: str
    consumer_access_mode: Optional[str]
    consumer_overrides: dict[str, Any]
    resource_id: Optional[str]
    source_binding_id: Optional[str]
    source_workspace_id: Optional[str]
    source_workspace_title: Optional[str]
    source_access_mode: Optional[str]
    source_overrides: dict[str, Any]
    group_id: Optional[str]
    group_title: Optional[str]
    group_owner_user_id: Optional[str]
    group_revision: Optional[int]
    consumer_is_member: bool
    source_is_member: bool
    topology_is_ready: bool


class SharedAssetScopeRepository(PostgresStoreBase):
    """Load configured shared-asset authorization evidence in one statement."""

    def list_evidence(
        self,
        *,
        workspace_id: str,
        group_id: Optional[str] = None,
    ) -> list[SharedAssetScopeEvidence]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT
                        consumer.id AS binding_id,
                        consumer.workspace_id AS active_workspace_id,
                        active_workspace.owner_user_id
                            AS active_workspace_owner_user_id,
                        consumer.access_mode AS consumer_access_mode,
                        consumer.overrides AS consumer_overrides,
                        consumer.resource_id,
                        source_binding.id AS source_binding_id,
                        source_binding.workspace_id AS source_workspace_id,
                        source_workspace.title AS source_workspace_title,
                        source_binding.access_mode AS source_access_mode,
                        source_binding.overrides AS source_overrides,
                        definition.id AS group_id,
                        definition.display_name AS group_title,
                        definition.owner_user_id AS group_owner_user_id,
                        definition.revision AS group_revision,
                        consumer_membership.workspace_id IS NOT NULL
                            AS consumer_is_member,
                        source_membership.workspace_id IS NOT NULL
                            AS source_is_member,
                        definition.id IS NOT NULL
                            AND EXISTS (
                                SELECT 1
                                FROM workspace_group_memberships AS dispatch_member
                                WHERE dispatch_member.group_id = definition.id
                                  AND dispatch_member.role = 'dispatch'
                            )
                            AND EXISTS (
                                SELECT 1
                                FROM workspace_group_memberships AS cell_member
                                WHERE cell_member.group_id = definition.id
                                  AND cell_member.role = 'cell'
                            ) AS topology_is_ready
                    FROM workspaces AS active_workspace
                    LEFT JOIN workspace_resource_bindings AS consumer
                      ON consumer.workspace_id = active_workspace.id
                     AND consumer.resource_type = 'asset'
                     AND consumer.overrides->>'share_scope' = 'workspace_group'
                     AND consumer.workspace_id <> COALESCE(
                         consumer.overrides->>'source_workspace_id', ''
                     )
                     AND (
                         CAST(:group_id AS varchar) IS NULL
                         OR consumer.overrides->>'group_id' = :group_id
                     )
                    LEFT JOIN workspace_group_definitions AS definition
                      ON definition.id = NULLIF(
                          consumer.overrides->>'group_id', ''
                      )
                    LEFT JOIN workspace_group_memberships AS consumer_membership
                      ON consumer_membership.group_id = definition.id
                     AND consumer_membership.workspace_id = consumer.workspace_id
                    LEFT JOIN LATERAL (
                        SELECT candidate.*
                        FROM workspace_resource_bindings AS candidate
                        WHERE candidate.workspace_id = NULLIF(
                                  consumer.overrides->>'source_workspace_id', ''
                              )
                          AND candidate.resource_type = consumer.resource_type
                          AND candidate.resource_id = consumer.resource_id
                          AND candidate.access_mode = 'read'
                          AND candidate.overrides->>'share_scope' =
                              'workspace_group'
                          AND candidate.overrides->>'source_workspace_id' =
                              candidate.workspace_id
                          AND candidate.overrides->>'group_id' =
                              consumer.overrides->>'group_id'
                          AND CAST(
                              candidate.overrides->'dynamic_selector' AS jsonb
                          ) = CAST(
                              consumer.overrides->'dynamic_selector' AS jsonb
                          )
                        ORDER BY candidate.id
                        LIMIT 1
                    ) AS source_binding ON TRUE
                    LEFT JOIN workspaces AS source_workspace
                      ON source_workspace.id = source_binding.workspace_id
                    LEFT JOIN workspace_group_memberships AS source_membership
                      ON source_membership.group_id = definition.id
                     AND source_membership.workspace_id = source_binding.workspace_id
                    WHERE active_workspace.id = :workspace_id
                    ORDER BY
                        consumer.overrides->>'group_id',
                        consumer.overrides->>'source_workspace_id',
                        consumer.resource_id,
                        consumer.id
                    """
                ),
                {"workspace_id": workspace_id, "group_id": group_id},
            ).fetchall()
        return [self._row_to_evidence(row) for row in rows]

    def _row_to_evidence(self, row: Any) -> SharedAssetScopeEvidence:
        return SharedAssetScopeEvidence(
            binding_id=row.binding_id,
            active_workspace_id=row.active_workspace_id,
            active_workspace_owner_user_id=row.active_workspace_owner_user_id,
            consumer_access_mode=row.consumer_access_mode,
            consumer_overrides=self.deserialize_json(
                row.consumer_overrides,
                default={},
            ),
            resource_id=row.resource_id,
            source_binding_id=row.source_binding_id,
            source_workspace_id=row.source_workspace_id,
            source_workspace_title=row.source_workspace_title,
            source_access_mode=row.source_access_mode,
            source_overrides=self.deserialize_json(row.source_overrides, default={}),
            group_id=row.group_id,
            group_title=row.group_title,
            group_owner_user_id=row.group_owner_user_id,
            group_revision=row.group_revision,
            consumer_is_member=bool(row.consumer_is_member),
            source_is_member=bool(row.source_is_member),
            topology_is_ready=bool(row.topology_is_ready),
        )
