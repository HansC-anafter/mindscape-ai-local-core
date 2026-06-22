"""Canonicalize the host resource default allocation blueprint."""

from alembic import op


revision = "20260622193000"
down_revision = "20260621023000"
branch_labels = None
depends_on = None


LEGACY_BLUEPRINT_ID = "ig-content-production-default"
CANONICAL_BLUEPRINT_ID = "local-core-workspace-default"


def upgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(
        f"""
        INSERT INTO host_resource_allocation_blueprints (
            blueprint_id,
            label,
            scope,
            state,
            metadata
        ) VALUES (
            '{CANONICAL_BLUEPRINT_ID}',
            'Local Core Workspace Default',
            'workspace_default',
            'enabled',
            '{{"source":"migration_seed","resource_semantics":"shared_pool_admission_quota"}}'::jsonb
        )
        ON CONFLICT (blueprint_id) DO UPDATE SET
            label = EXCLUDED.label,
            scope = EXCLUDED.scope,
            state = 'enabled',
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
                'hrabe_{CANONICAL_BLUEPRINT_ID}_browser_interactive',
                '{CANONICAL_BLUEPRINT_ID}',
                'browser_local',
                'browser_interactive',
                'Browser interactive',
                3,
                'shared_pool',
                'normal',
                '[]'::jsonb,
                '{{"source":"canonical_blueprint_migration"}}'::jsonb
            ),
            (
                'hrabe_{CANONICAL_BLUEPRINT_ID}_default_local_browser_browser_batch',
                '{CANONICAL_BLUEPRINT_ID}',
                'default_local_browser',
                'browser_batch',
                'Browser batch',
                3,
                'shared_pool',
                'normal',
                '[]'::jsonb,
                '{{"source":"canonical_blueprint_migration"}}'::jsonb
            ),
            (
                'hrabe_{CANONICAL_BLUEPRINT_ID}_default_compute',
                '{CANONICAL_BLUEPRINT_ID}',
                'default_local',
                'default_compute',
                'Default compute',
                8,
                'shared_pool',
                'normal',
                '[]'::jsonb,
                '{{"source":"canonical_blueprint_migration"}}'::jsonb
            ),
            (
                'hrabe_{CANONICAL_BLUEPRINT_ID}_vision_analysis',
                '{CANONICAL_BLUEPRINT_ID}',
                'vision_local',
                'vision_analysis',
                'Vision analysis',
                4,
                'shared_pool',
                'normal',
                '[]'::jsonb,
                '{{"source":"canonical_blueprint_migration"}}'::jsonb
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
            'hrwaa_' || replace(workspace_id, '-', '') || '_{CANONICAL_BLUEPRINT_ID}',
            workspace_id,
            '{CANONICAL_BLUEPRINT_ID}',
            state,
            applied_by,
            applied_at,
            COALESCE(metadata, '{{}}'::jsonb)
                || '{{"source":"canonical_blueprint_migration","legacy_blueprint_id":"{LEGACY_BLUEPRINT_ID}"}}'::jsonb
        FROM host_resource_workspace_allocation_applications
        WHERE blueprint_id = '{LEGACY_BLUEPRINT_ID}'
        ON CONFLICT (workspace_id, blueprint_id) DO UPDATE SET
            state = EXCLUDED.state,
            applied_by = EXCLUDED.applied_by,
            applied_at = EXCLUDED.applied_at,
            metadata = EXCLUDED.metadata
        """
    )
    op.execute(
        f"""
        WITH legacy_rows AS (
            SELECT
                allocation_id,
                workspace_id,
                queue_shard,
                CASE
                    WHEN task_family = 'ig_browser_capture' THEN 'browser_interactive'
                    WHEN task_family = 'ig_reference_batch' THEN 'default_compute'
                    WHEN task_family = 'ig_reference_vision' THEN 'vision_analysis'
                    ELSE task_family
                END AS canonical_task_family
            FROM host_resource_workspace_allocations
            WHERE blueprint_id = '{LEGACY_BLUEPRINT_ID}'
        )
        DELETE FROM host_resource_workspace_allocations old
        USING legacy_rows legacy, host_resource_workspace_allocations existing
        WHERE old.allocation_id = legacy.allocation_id
          AND existing.workspace_id = legacy.workspace_id
          AND existing.queue_shard = legacy.queue_shard
          AND existing.task_family = legacy.canonical_task_family
          AND existing.blueprint_id = '{CANONICAL_BLUEPRINT_ID}'
        """
    )
    op.execute(
        f"""
        UPDATE host_resource_workspace_allocations
        SET
            blueprint_id = '{CANONICAL_BLUEPRINT_ID}',
            task_family = CASE
                WHEN task_family = 'ig_browser_capture' THEN 'browser_interactive'
                WHEN task_family = 'ig_reference_batch' THEN 'default_compute'
                WHEN task_family = 'ig_reference_vision' THEN 'vision_analysis'
                ELSE task_family
            END,
            blueprint_entry_id = CASE
                WHEN queue_shard = 'browser_local'
                    THEN 'hrabe_{CANONICAL_BLUEPRINT_ID}_browser_interactive'
                WHEN queue_shard = 'default_local_browser'
                    THEN 'hrabe_{CANONICAL_BLUEPRINT_ID}_default_local_browser_browser_batch'
                WHEN queue_shard = 'default_local'
                    THEN 'hrabe_{CANONICAL_BLUEPRINT_ID}_default_compute'
                WHEN queue_shard = 'vision_local'
                    THEN 'hrabe_{CANONICAL_BLUEPRINT_ID}_vision_analysis'
                ELSE blueprint_entry_id
            END,
            label = CASE
                WHEN queue_shard = 'browser_local' THEN 'Browser interactive'
                WHEN queue_shard = 'default_local_browser' THEN 'Browser batch'
                WHEN queue_shard = 'default_local' THEN 'Default compute'
                WHEN queue_shard = 'vision_local' THEN 'Vision analysis'
                ELSE label
            END,
            metadata = COALESCE(metadata, '{{}}'::jsonb)
                || '{{"source":"canonical_blueprint_migration","legacy_blueprint_id":"{LEGACY_BLUEPRINT_ID}"}}'::jsonb,
            updated_at = NOW()
        WHERE blueprint_id = '{LEGACY_BLUEPRINT_ID}'
        """
    )
    op.execute(
        f"""
        DELETE FROM host_resource_workspace_allocation_applications
        WHERE blueprint_id = '{LEGACY_BLUEPRINT_ID}'
        """
    )
    op.execute(
        f"""
        UPDATE host_resource_allocation_blueprints
        SET
            state = 'disabled',
            metadata = COALESCE(metadata, '{{}}'::jsonb)
                || '{{"source":"canonical_blueprint_migration","replaced_by":"{CANONICAL_BLUEPRINT_ID}"}}'::jsonb,
            updated_at = NOW()
        WHERE blueprint_id = '{LEGACY_BLUEPRINT_ID}'
        """
    )


def downgrade():
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(
        f"""
        INSERT INTO host_resource_allocation_blueprints (
            blueprint_id,
            label,
            scope,
            state,
            metadata
        ) VALUES (
            '{LEGACY_BLUEPRINT_ID}',
            'IG Content Production Default',
            'workspace_default',
            'enabled',
            '{{"source":"downgrade_restore","resource_semantics":"shared_pool_admission_quota"}}'::jsonb
        )
        ON CONFLICT (blueprint_id) DO UPDATE SET
            label = EXCLUDED.label,
            scope = EXCLUDED.scope,
            state = 'enabled',
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
                'hrabe_{LEGACY_BLUEPRINT_ID}_browser',
                '{LEGACY_BLUEPRINT_ID}',
                'browser_local',
                'ig_browser_capture',
                'IG browser capture',
                3,
                'shared_pool',
                'normal',
                '["ig_pin_post_detail","ig_analyze_following"]'::jsonb,
                '{{"source":"downgrade_restore"}}'::jsonb
            ),
            (
                'hrabe_{LEGACY_BLUEPRINT_ID}_default_local_browser_batch',
                '{LEGACY_BLUEPRINT_ID}',
                'default_local_browser',
                'browser_batch',
                'Managed browser batch',
                3,
                'shared_pool',
                'normal',
                '[]'::jsonb,
                '{{"source":"downgrade_restore"}}'::jsonb
            ),
            (
                'hrabe_{LEGACY_BLUEPRINT_ID}_batch',
                '{LEGACY_BLUEPRINT_ID}',
                'default_local',
                'ig_reference_batch',
                'IG reference batch',
                8,
                'shared_pool',
                'normal',
                '["ig_batch_pin_references"]'::jsonb,
                '{{"source":"downgrade_restore"}}'::jsonb
            ),
            (
                'hrabe_{LEGACY_BLUEPRINT_ID}_vision',
                '{LEGACY_BLUEPRINT_ID}',
                'vision_local',
                'ig_reference_vision',
                'IG reference vision',
                4,
                'shared_pool',
                'normal',
                '["ig_analyze_pinned_reference"]'::jsonb,
                '{{"source":"downgrade_restore"}}'::jsonb
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
            'hrwaa_' || replace(workspace_id, '-', '') || '_{LEGACY_BLUEPRINT_ID}',
            workspace_id,
            '{LEGACY_BLUEPRINT_ID}',
            state,
            applied_by,
            applied_at,
            COALESCE(metadata, '{{}}'::jsonb)
                || '{{"source":"downgrade_restore","canonical_blueprint_id":"{CANONICAL_BLUEPRINT_ID}"}}'::jsonb
        FROM host_resource_workspace_allocation_applications
        WHERE blueprint_id = '{CANONICAL_BLUEPRINT_ID}'
        ON CONFLICT (workspace_id, blueprint_id) DO UPDATE SET
            state = EXCLUDED.state,
            applied_by = EXCLUDED.applied_by,
            applied_at = EXCLUDED.applied_at,
            metadata = EXCLUDED.metadata
        """
    )
    op.execute(
        f"""
        WITH canonical_rows AS (
            SELECT
                allocation_id,
                workspace_id,
                queue_shard,
                CASE
                    WHEN task_family = 'browser_interactive' THEN 'ig_browser_capture'
                    WHEN task_family = 'default_compute' THEN 'ig_reference_batch'
                    WHEN task_family = 'vision_analysis' THEN 'ig_reference_vision'
                    ELSE task_family
                END AS legacy_task_family
            FROM host_resource_workspace_allocations
            WHERE blueprint_id = '{CANONICAL_BLUEPRINT_ID}'
        )
        DELETE FROM host_resource_workspace_allocations canonical
        USING canonical_rows mapped, host_resource_workspace_allocations existing
        WHERE canonical.allocation_id = mapped.allocation_id
          AND existing.workspace_id = mapped.workspace_id
          AND existing.queue_shard = mapped.queue_shard
          AND existing.task_family = mapped.legacy_task_family
          AND existing.blueprint_id = '{LEGACY_BLUEPRINT_ID}'
        """
    )
    op.execute(
        f"""
        UPDATE host_resource_workspace_allocations
        SET
            blueprint_id = '{LEGACY_BLUEPRINT_ID}',
            task_family = CASE
                WHEN task_family = 'browser_interactive' THEN 'ig_browser_capture'
                WHEN task_family = 'default_compute' THEN 'ig_reference_batch'
                WHEN task_family = 'vision_analysis' THEN 'ig_reference_vision'
                ELSE task_family
            END,
            blueprint_entry_id = CASE
                WHEN queue_shard = 'browser_local'
                    THEN 'hrabe_{LEGACY_BLUEPRINT_ID}_browser'
                WHEN queue_shard = 'default_local_browser'
                    THEN 'hrabe_{LEGACY_BLUEPRINT_ID}_default_local_browser_batch'
                WHEN queue_shard = 'default_local'
                    THEN 'hrabe_{LEGACY_BLUEPRINT_ID}_batch'
                WHEN queue_shard = 'vision_local'
                    THEN 'hrabe_{LEGACY_BLUEPRINT_ID}_vision'
                ELSE blueprint_entry_id
            END,
            label = CASE
                WHEN queue_shard = 'browser_local' THEN 'IG browser capture'
                WHEN queue_shard = 'default_local_browser' THEN 'Managed browser batch'
                WHEN queue_shard = 'default_local' THEN 'IG reference batch'
                WHEN queue_shard = 'vision_local' THEN 'IG reference vision'
                ELSE label
            END,
            metadata = COALESCE(metadata, '{{}}'::jsonb)
                || '{{"source":"downgrade_restore","canonical_blueprint_id":"{CANONICAL_BLUEPRINT_ID}"}}'::jsonb,
            updated_at = NOW()
        WHERE blueprint_id = '{CANONICAL_BLUEPRINT_ID}'
        """
    )
    op.execute(
        f"""
        DELETE FROM host_resource_workspace_allocation_applications
        WHERE blueprint_id = '{CANONICAL_BLUEPRINT_ID}'
        """
    )
    op.execute(
        f"""
        UPDATE host_resource_allocation_blueprints
        SET
            state = 'disabled',
            metadata = COALESCE(metadata, '{{}}'::jsonb)
                || '{{"source":"downgrade_restore","replaced_by":"{LEGACY_BLUEPRINT_ID}"}}'::jsonb,
            updated_at = NOW()
        WHERE blueprint_id = '{CANONICAL_BLUEPRINT_ID}'
        """
    )
