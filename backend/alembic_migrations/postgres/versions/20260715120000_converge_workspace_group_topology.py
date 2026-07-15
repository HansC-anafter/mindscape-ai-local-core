"""Converge workspace group topology on normalized memberships.

Revision ID: 20260715120000
Revises: 20260715010000
Create Date: 2026-07-15 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260715120000"
down_revision = "20260715010000"
branch_labels = None
depends_on = None


def _create_compatibility_view() -> None:
    op.execute(
        """
        CREATE VIEW workspace_groups AS
        SELECT
            definition.id,
            definition.display_name,
            definition.owner_user_id,
            definition.description,
            COALESCE(
                jsonb_object_agg(membership.workspace_id, membership.role)
                    FILTER (WHERE membership.workspace_id IS NOT NULL),
                '{}'::jsonb
            ) AS role_map,
            definition.metadata,
            definition.revision,
            definition.created_at,
            definition.updated_at
        FROM workspace_group_definitions AS definition
        LEFT JOIN workspace_group_memberships AS membership
          ON membership.group_id = definition.id
        GROUP BY definition.id
        """
    )


def upgrade() -> None:
    op.execute("SET lock_timeout = '15s'")
    op.execute("SET statement_timeout = '120s'")

    # Refuse to guess when legacy representations disagree. Empty legacy JSON is
    # treated as absent; any populated representation must be valid and equal.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM workspace_group_memberships
                WHERE role NOT IN ('dispatch', 'cell')
            ) THEN
                RAISE EXCEPTION 'workspace_group_topology_conflict: invalid membership role';
            END IF;

            IF EXISTS (
                SELECT 1 FROM workspace_groups AS group_row
                WHERE jsonb_typeof(COALESCE(group_row.role_map, '{}'::jsonb)) <> 'object'
            ) OR EXISTS (
                SELECT 1
                FROM workspace_groups AS group_row,
                     LATERAL jsonb_each_text(COALESCE(group_row.role_map, '{}'::jsonb)) AS role_entry
                WHERE role_entry.value NOT IN ('dispatch', 'cell')
            ) THEN
                RAISE EXCEPTION 'workspace_group_topology_conflict: invalid role_map';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM workspace_groups AS group_row,
                     LATERAL jsonb_each_text(COALESCE(group_row.role_map, '{}'::jsonb)) AS role_entry
                LEFT JOIN workspaces AS workspace ON workspace.id = role_entry.key
                WHERE workspace.id IS NULL
            ) THEN
                RAISE EXCEPTION 'workspace_group_topology_conflict: role_map references unknown workspace';
            END IF;

            IF EXISTS (
                SELECT group_row.id
                FROM workspace_groups AS group_row,
                     LATERAL jsonb_each_text(COALESCE(group_row.role_map, '{}'::jsonb)) AS role_entry
                WHERE role_entry.value = 'dispatch'
                GROUP BY group_row.id
                HAVING COUNT(*) > 1
            ) THEN
                RAISE EXCEPTION 'workspace_group_topology_conflict: duplicate role_map dispatch';
            END IF;

            IF EXISTS (
                SELECT group_id
                FROM workspace_group_memberships
                WHERE role = 'dispatch'
                GROUP BY group_id
                HAVING COUNT(*) > 1
            ) THEN
                RAISE EXCEPTION 'workspace_group_topology_conflict: duplicate dispatch membership';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM workspace_groups AS group_row
                WHERE COALESCE(group_row.role_map, '{}'::jsonb) <> '{}'::jsonb
                  AND EXISTS (
                      SELECT 1 FROM workspace_group_memberships AS membership
                      WHERE membership.group_id = group_row.id
                  )
                  AND COALESCE(group_row.role_map, '{}'::jsonb) <> COALESCE(
                      (
                          SELECT jsonb_object_agg(membership.workspace_id, membership.role)
                          FROM workspace_group_memberships AS membership
                          WHERE membership.group_id = group_row.id
                      ),
                      '{}'::jsonb
                  )
            ) THEN
                RAISE EXCEPTION 'workspace_group_topology_conflict: membership and role_map differ';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM workspaces AS workspace
                LEFT JOIN workspace_groups AS group_row ON group_row.id = workspace.group_id
                WHERE workspace.group_id IS NOT NULL
                  AND (
                      group_row.id IS NULL
                      OR workspace.workspace_role IS NULL
                      OR workspace.workspace_role NOT IN ('dispatch', 'cell')
                  )
            ) THEN
                RAISE EXCEPTION 'workspace_group_topology_conflict: invalid workspace legacy membership';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM workspaces AS workspace
                JOIN workspace_group_memberships AS membership
                  ON membership.workspace_id = workspace.id
                 AND membership.group_id = workspace.group_id
                WHERE workspace.group_id IS NOT NULL
                  AND membership.role <> workspace.workspace_role
            ) THEN
                RAISE EXCEPTION 'workspace_group_topology_conflict: workspace legacy role differs';
            END IF;

            IF EXISTS (
                SELECT 1
                FROM workspaces AS workspace
                JOIN workspace_groups AS group_row ON group_row.id = workspace.group_id
                WHERE workspace.group_id IS NOT NULL
                  AND COALESCE(group_row.role_map, '{}'::jsonb) <> '{}'::jsonb
                  AND group_row.role_map ->> workspace.id IS DISTINCT FROM workspace.workspace_role
            ) THEN
                RAISE EXCEPTION 'workspace_group_topology_conflict: workspace legacy and role_map differ';
            END IF;

            IF EXISTS (
                SELECT workspace.group_id
                FROM workspaces AS workspace
                JOIN workspace_groups AS group_row ON group_row.id = workspace.group_id
                WHERE workspace.workspace_role = 'dispatch'
                  AND COALESCE(group_row.role_map, '{}'::jsonb) = '{}'::jsonb
                  AND NOT EXISTS (
                      SELECT 1 FROM workspace_group_memberships AS membership
                      WHERE membership.group_id = workspace.group_id
                  )
                GROUP BY workspace.group_id
                HAVING COUNT(*) > 1
            ) THEN
                RAISE EXCEPTION 'workspace_group_topology_conflict: duplicate workspace legacy dispatch';
            END IF;
        END $$
        """
    )

    op.rename_table("workspace_groups", "workspace_group_definitions")
    op.add_column(
        "workspace_group_definitions",
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default="1"),
    )

    # A populated membership set is authoritative. role_map is used only when
    # the group has no normalized rows yet.
    op.execute(
        """
        INSERT INTO workspace_group_memberships (workspace_id, group_id, role)
        SELECT role_entry.key, definition.id, role_entry.value
        FROM workspace_group_definitions AS definition,
             LATERAL jsonb_each_text(COALESCE(definition.role_map, '{}'::jsonb)) AS role_entry
        WHERE NOT EXISTS (
            SELECT 1 FROM workspace_group_memberships AS membership
            WHERE membership.group_id = definition.id
        )
        ON CONFLICT (workspace_id, group_id) DO NOTHING
        """
    )

    # Workspace legacy columns are the final source only when the group still
    # has no normalized membership after role_map backfill.
    op.execute(
        """
        INSERT INTO workspace_group_memberships (workspace_id, group_id, role)
        SELECT workspace.id, workspace.group_id, workspace.workspace_role
        FROM workspaces AS workspace
        WHERE workspace.group_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM workspace_group_memberships AS membership
              WHERE membership.group_id = workspace.group_id
          )
        ON CONFLICT (workspace_id, group_id) DO NOTHING
        """
    )

    op.create_check_constraint(
        "ck_workspace_group_membership_role",
        "workspace_group_memberships",
        "role IN ('dispatch', 'cell')",
    )
    op.create_index(
        "uq_workspace_group_dispatch",
        "workspace_group_memberships",
        ["group_id"],
        unique=True,
        postgresql_where=sa.text("role = 'dispatch'"),
    )

    op.drop_column("workspace_group_definitions", "role_map")
    op.drop_index("idx_ws_group", table_name="workspaces")
    op.drop_column("workspaces", "workspace_role")
    op.drop_column("workspaces", "group_id")
    _create_compatibility_view()

    op.execute("RESET statement_timeout")
    op.execute("RESET lock_timeout")


def downgrade() -> None:
    op.execute("SET lock_timeout = '15s'")
    op.execute("SET statement_timeout = '120s'")
    op.execute("DROP VIEW workspace_groups")

    op.add_column(
        "workspace_group_definitions",
        sa.Column(
            "role_map",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.execute(
        """
        UPDATE workspace_group_definitions AS definition
        SET role_map = COALESCE(
            (
                SELECT jsonb_object_agg(membership.workspace_id, membership.role)
                FROM workspace_group_memberships AS membership
                WHERE membership.group_id = definition.id
            ),
            '{}'::jsonb
        )
        """
    )

    op.add_column("workspaces", sa.Column("group_id", sa.String(64), nullable=True))
    op.add_column(
        "workspaces",
        sa.Column("workspace_role", sa.String(16), nullable=True, server_default="cell"),
    )
    op.execute(
        """
        UPDATE workspaces AS workspace
        SET group_id = only_membership.group_id,
            workspace_role = only_membership.role
        FROM (
            SELECT MIN(group_id) AS group_id, MIN(role) AS role, workspace_id
            FROM workspace_group_memberships
            GROUP BY workspace_id
            HAVING COUNT(*) = 1
        ) AS only_membership
        WHERE only_membership.workspace_id = workspace.id
        """
    )
    op.create_index("idx_ws_group", "workspaces", ["group_id"])

    op.drop_index("uq_workspace_group_dispatch", table_name="workspace_group_memberships")
    op.drop_constraint(
        "ck_workspace_group_membership_role",
        "workspace_group_memberships",
        type_="check",
    )
    op.drop_column("workspace_group_definitions", "revision")
    op.rename_table("workspace_group_definitions", "workspace_groups")

    op.execute("RESET statement_timeout")
    op.execute("RESET lock_timeout")
