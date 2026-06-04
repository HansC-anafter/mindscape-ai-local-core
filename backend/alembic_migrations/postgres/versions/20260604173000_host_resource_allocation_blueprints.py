"""Add host resource allocation blueprints.

Revision ID: 20260604173000
Revises: 20260604024130
Create Date: 2026-06-04 17:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260604173000"
down_revision = "20260604024130"
branch_labels = None
depends_on = None


DEFAULT_BLUEPRINT_ID = "ig-content-production-default"
DEFAULT_WORKSPACE_ID = "bac7ce63-e768-454d-96f3-3a00e8e1df69"


def upgrade():
    op.execute(
        """
        ALTER TABLE host_resource_workspace_allocations
        DROP CONSTRAINT IF EXISTS host_resource_workspace_allocations_lane_id_fkey
        """
    )
    op.create_table(
        "host_resource_allocation_blueprints",
        sa.Column("blueprint_id", sa.Text(), primary_key=True),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=False, server_default="workspace_default"),
        sa.Column("state", sa.Text(), nullable=False, server_default="enabled"),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_table(
        "host_resource_allocation_blueprint_entries",
        sa.Column("blueprint_entry_id", sa.Text(), primary_key=True),
        sa.Column("blueprint_id", sa.Text(), nullable=False),
        sa.Column("queue_shard", sa.Text(), nullable=False),
        sa.Column("task_family", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column(
            "max_parallel_task_claims",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "share_policy",
            sa.Text(),
            nullable=False,
            server_default="shared_pool",
        ),
        sa.Column(
            "priority_ceiling",
            sa.Text(),
            nullable=False,
            server_default="normal",
        ),
        sa.Column(
            "task_selectors",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["blueprint_id"],
            ["host_resource_allocation_blueprints.blueprint_id"],
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "host_resource_workspace_allocation_applications",
        sa.Column("application_id", sa.Text(), primary_key=True),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("blueprint_id", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False, server_default="applied"),
        sa.Column("applied_by", sa.Text(), nullable=True),
        sa.Column(
            "applied_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.ForeignKeyConstraint(
            ["blueprint_id"],
            ["host_resource_allocation_blueprints.blueprint_id"],
            ondelete="CASCADE",
        ),
    )

    op.add_column(
        "host_resource_workspace_allocations",
        sa.Column("queue_shard", sa.Text(), nullable=True),
    )
    op.add_column(
        "host_resource_workspace_allocations",
        sa.Column("task_family", sa.Text(), nullable=True),
    )
    op.add_column(
        "host_resource_workspace_allocations",
        sa.Column(
            "max_parallel_task_claims",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )
    op.add_column(
        "host_resource_workspace_allocations",
        sa.Column(
            "share_policy",
            sa.Text(),
            nullable=False,
            server_default="shared_pool",
        ),
    )
    op.add_column(
        "host_resource_workspace_allocations",
        sa.Column(
            "priority_ceiling",
            sa.Text(),
            nullable=False,
            server_default="normal",
        ),
    )
    op.add_column(
        "host_resource_workspace_allocations",
        sa.Column("blueprint_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "host_resource_workspace_allocations",
        sa.Column("blueprint_entry_id", sa.Text(), nullable=True),
    )
    op.add_column(
        "host_resource_workspace_allocations",
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_host_resource_workspace_allocations_workspace_queue_family
        ON host_resource_workspace_allocations (workspace_id, queue_shard, task_family)
        WHERE queue_shard IS NOT NULL AND task_family IS NOT NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_host_resource_allocation_blueprint_entries_blueprint_queue_family
        ON host_resource_allocation_blueprint_entries (blueprint_id, queue_shard, task_family)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_host_resource_workspace_allocation_applications_workspace_blueprint
        ON host_resource_workspace_allocation_applications (workspace_id, blueprint_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_host_resource_workspace_allocations_queue_family_state
        ON host_resource_workspace_allocations (queue_shard, task_family, state)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_host_resource_workspace_allocations_blueprint
        ON host_resource_workspace_allocations (blueprint_id, blueprint_entry_id)
        """
    )

    op.execute(
        f"""
        INSERT INTO host_resource_allocation_blueprints (
            blueprint_id,
            label,
            scope,
            state,
            metadata
        ) VALUES (
            '{DEFAULT_BLUEPRINT_ID}',
            'IG Content Production Default',
            'workspace_default',
            'enabled',
            '{{"source":"migration_seed","resource_semantics":"shared_pool_admission_quota"}}'::jsonb
        )
        ON CONFLICT (blueprint_id) DO UPDATE SET
            label = EXCLUDED.label,
            scope = EXCLUDED.scope,
            state = EXCLUDED.state,
            metadata = EXCLUDED.metadata,
            updated_at = NOW()
        """
    )
    op.execute(
        f"""
        INSERT INTO host_resource_allocation_blueprint_entries (
            blueprint_entry_id,
            blueprint_id,
            queue_shard,
            task_family,
            label,
            max_parallel_task_claims,
            share_policy,
            priority_ceiling,
            task_selectors,
            metadata
        ) VALUES
            (
                'hrabe_{DEFAULT_BLUEPRINT_ID}_browser',
                '{DEFAULT_BLUEPRINT_ID}',
                'browser_local',
                'ig_browser_capture',
                'IG browser capture',
                3,
                'shared_pool',
                'normal',
                '["ig_pin_post_detail","ig_analyze_following"]'::jsonb,
                '{{"source":"current_queue_capacity_snapshot"}}'::jsonb
            ),
            (
                'hrabe_{DEFAULT_BLUEPRINT_ID}_batch',
                '{DEFAULT_BLUEPRINT_ID}',
                'default_local',
                'ig_reference_batch',
                'IG reference batch',
                8,
                'shared_pool',
                'normal',
                '["ig_batch_pin_references"]'::jsonb,
                '{{"source":"current_queue_capacity_snapshot"}}'::jsonb
            ),
            (
                'hrabe_{DEFAULT_BLUEPRINT_ID}_vision',
                '{DEFAULT_BLUEPRINT_ID}',
                'vision_local',
                'ig_reference_vision',
                'IG reference vision',
                4,
                'shared_pool',
                'normal',
                '["ig_analyze_pinned_reference"]'::jsonb,
                '{{"source":"current_queue_capacity_snapshot"}}'::jsonb
            )
        ON CONFLICT (blueprint_id, queue_shard, task_family) DO UPDATE SET
            label = EXCLUDED.label,
            max_parallel_task_claims = EXCLUDED.max_parallel_task_claims,
            share_policy = EXCLUDED.share_policy,
            priority_ceiling = EXCLUDED.priority_ceiling,
            task_selectors = EXCLUDED.task_selectors,
            metadata = EXCLUDED.metadata,
            updated_at = NOW()
        """
    )
    op.execute(
        f"""
        INSERT INTO host_resource_workspace_allocations (
            allocation_id,
            workspace_id,
            lane_id,
            label,
            max_worker_target,
            max_concurrency,
            state,
            metadata,
            created_by,
            updated_by,
            queue_shard,
            task_family,
            max_parallel_task_claims,
            share_policy,
            priority_ceiling,
            blueprint_id,
            blueprint_entry_id,
            applied_at
        )
        SELECT
            'hrwa_' || replace('{DEFAULT_WORKSPACE_ID}', '-', '') || '_' || e.queue_shard || '_' || e.task_family,
            '{DEFAULT_WORKSPACE_ID}',
            'quota:' || e.queue_shard || ':' || e.task_family,
            e.label,
            e.max_parallel_task_claims,
            e.max_parallel_task_claims,
            'enabled',
            jsonb_build_object(
                'source', 'migration_seed',
                'task_selectors', e.task_selectors,
                'resource_semantics', 'shared_pool_admission_quota'
            ),
            'migration',
            'migration',
            e.queue_shard,
            e.task_family,
            e.max_parallel_task_claims,
            e.share_policy,
            e.priority_ceiling,
            e.blueprint_id,
            e.blueprint_entry_id,
            NOW()
        FROM host_resource_allocation_blueprint_entries e
        WHERE e.blueprint_id = '{DEFAULT_BLUEPRINT_ID}'
          AND EXISTS (
              SELECT 1 FROM workspaces WHERE id = '{DEFAULT_WORKSPACE_ID}'
          )
        ON CONFLICT (workspace_id, queue_shard, task_family)
        WHERE queue_shard IS NOT NULL AND task_family IS NOT NULL
        DO UPDATE SET
            label = EXCLUDED.label,
            lane_id = EXCLUDED.lane_id,
            max_worker_target = EXCLUDED.max_worker_target,
            max_concurrency = EXCLUDED.max_concurrency,
            state = EXCLUDED.state,
            metadata = EXCLUDED.metadata,
            updated_by = EXCLUDED.updated_by,
            updated_at = NOW(),
            max_parallel_task_claims = EXCLUDED.max_parallel_task_claims,
            share_policy = EXCLUDED.share_policy,
            priority_ceiling = EXCLUDED.priority_ceiling,
            blueprint_id = EXCLUDED.blueprint_id,
            blueprint_entry_id = EXCLUDED.blueprint_entry_id,
            applied_at = EXCLUDED.applied_at
        """
    )
    op.execute(
        f"""
        INSERT INTO host_resource_workspace_allocation_applications (
            application_id,
            workspace_id,
            blueprint_id,
            state,
            applied_by,
            applied_at,
            metadata
        )
        SELECT
            'hrwaa_' || replace('{DEFAULT_WORKSPACE_ID}', '-', '') || '_{DEFAULT_BLUEPRINT_ID}',
            '{DEFAULT_WORKSPACE_ID}',
            '{DEFAULT_BLUEPRINT_ID}',
            'applied',
            'migration',
            NOW(),
            '{{"source":"migration_seed"}}'::jsonb
        WHERE EXISTS (
            SELECT 1 FROM workspaces WHERE id = '{DEFAULT_WORKSPACE_ID}'
        )
        ON CONFLICT (workspace_id, blueprint_id) DO UPDATE SET
            state = EXCLUDED.state,
            applied_by = EXCLUDED.applied_by,
            applied_at = EXCLUDED.applied_at,
            metadata = EXCLUDED.metadata
        """
    )

    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_tasks_workspace_queue_running_pack
            ON tasks (workspace_id, queue_shard, pack_id)
            INCLUDE (task_type)
            WHERE status = 'running'
            """
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_tasks_workspace_queue_running_pack")

    op.execute("DROP INDEX IF EXISTS idx_host_resource_workspace_allocations_blueprint")
    op.execute(
        "DROP INDEX IF EXISTS idx_host_resource_workspace_allocations_queue_family_state"
    )
    op.execute(
        "DROP INDEX IF EXISTS uq_host_resource_workspace_allocation_applications_workspace_blueprint"
    )
    op.execute(
        "DROP INDEX IF EXISTS uq_host_resource_allocation_blueprint_entries_blueprint_queue_family"
    )
    op.execute(
        "DROP INDEX IF EXISTS uq_host_resource_workspace_allocations_workspace_queue_family"
    )
    op.drop_column("host_resource_workspace_allocations", "applied_at")
    op.drop_column("host_resource_workspace_allocations", "blueprint_entry_id")
    op.drop_column("host_resource_workspace_allocations", "blueprint_id")
    op.drop_column("host_resource_workspace_allocations", "priority_ceiling")
    op.drop_column("host_resource_workspace_allocations", "share_policy")
    op.drop_column("host_resource_workspace_allocations", "max_parallel_task_claims")
    op.drop_column("host_resource_workspace_allocations", "task_family")
    op.drop_column("host_resource_workspace_allocations", "queue_shard")
    op.drop_table("host_resource_workspace_allocation_applications")
    op.drop_table("host_resource_allocation_blueprint_entries")
    op.drop_table("host_resource_allocation_blueprints")
