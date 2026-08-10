"""Restore vision workspace capacity from its linked enabled blueprint.

Revision ID: 20260725140000
Revises: 20260725130000
Create Date: 2026-07-25 14:00:00.000000
"""

from alembic import op
from sqlalchemy import text


revision = "20260725140000"
down_revision = "20260725130000"
branch_labels = None
depends_on = "20260604173000"


UNAUTHORIZED_OVERRIDE_REASON = "workspace_vision_local_single_inflight_2026_06_07"


REQUIRED_TABLES = (
    "host_resource_workspace_allocations",
    "host_resource_allocation_blueprints",
    "host_resource_allocation_blueprint_entries",
)

REQUIRED_INDEXES = (
    "uq_host_resource_workspace_allocations_workspace_queue_family",
    "uq_host_resource_workspace_allocation_applications_workspace_blueprint",
    "uq_host_resource_allocation_blueprint_entries_blueprint_queue_family",
)

REQUIRED_COLUMNS = {
    "host_resource_workspace_allocations": (
        "allocation_id",
        "blueprint_id",
        "blueprint_entry_id",
        "queue_shard",
        "task_family",
        "max_worker_target",
        "max_concurrency",
        "max_parallel_task_claims",
        "metadata",
        "state",
    ),
    "host_resource_allocation_blueprints": ("blueprint_id", "scope", "state"),
    "host_resource_allocation_blueprint_entries": (
        "blueprint_entry_id",
        "blueprint_id",
        "task_family",
        "queue_shard",
        "max_parallel_task_claims",
    ),
}


def _require_host_resource_contract() -> None:
    connection = op.get_bind()

    missing_objects: list[str] = []
    for table_name in REQUIRED_TABLES:
        table_exists = bool(
            connection.execute(
                text("SELECT to_regclass(:object_name) IS NOT NULL"),
                {"object_name": f"public.{table_name}"},
            ).scalar()
        )
        if not table_exists:
            missing_objects.append(f"table:{table_name}")

    for index_name in REQUIRED_INDEXES:
        index_exists = bool(
            connection.execute(
                text("SELECT to_regclass(:object_name) IS NOT NULL"),
                {"object_name": f"public.{index_name}"},
            ).scalar()
        )
        if not index_exists:
            missing_objects.append(f"index:{index_name}")

    for table_name, required_columns in REQUIRED_COLUMNS.items():
        columns = {
            row[0]
            for row in connection.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                    """
                ),
                {"table_name": table_name},
            )
        }
        for column_name in required_columns:
            if column_name not in columns:
                missing_objects.append(f"{table_name}.{column_name}")

    if missing_objects:
        raise RuntimeError(
            "host_resource_schema_drift: missing required host-resource schema objects "
            + ", ".join(sorted(missing_objects))
        )


def upgrade() -> None:
    _require_host_resource_contract()

    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("SET LOCAL statement_timeout = '30s'")
    op.execute(
        f"""
        UPDATE host_resource_workspace_allocations AS allocation
        SET
            max_worker_target = entry.max_parallel_task_claims,
            max_concurrency = entry.max_parallel_task_claims,
            max_parallel_task_claims = entry.max_parallel_task_claims,
            metadata = (
                COALESCE(allocation.metadata, '{{}}'::jsonb)
                - 'operator_override'
            ) || jsonb_build_object(
                'capacity_restoration',
                jsonb_build_object(
                    'source', 'linked_enabled_blueprint_entry',
                    'reason', 'owner_directed_authorization_restoration_2026_07_25',
                    'restored_from', 1,
                    'restored_to', entry.max_parallel_task_claims,
                    'replaced_override_reason', '{UNAUTHORIZED_OVERRIDE_REASON}',
                    'migration_revision', '{revision}'
                )
            ),
            updated_by = 'migration:{revision}',
            updated_at = NOW()
        FROM host_resource_allocation_blueprint_entries AS entry
        JOIN host_resource_allocation_blueprints AS blueprint
          ON blueprint.blueprint_id = entry.blueprint_id
         AND blueprint.state = 'enabled'
        WHERE allocation.blueprint_entry_id = entry.blueprint_entry_id
          AND allocation.blueprint_id = entry.blueprint_id
          AND allocation.queue_shard = 'vision_local'
          AND allocation.task_family IN ('ig_reference_vision', 'vision_analysis')
          AND allocation.state = 'enabled'
          AND allocation.max_worker_target = 1
          AND allocation.max_concurrency = 1
          AND allocation.max_parallel_task_claims = 1
          AND entry.queue_shard = allocation.queue_shard
          AND entry.task_family = allocation.task_family
          AND entry.max_parallel_task_claims = 4
          AND allocation.metadata->'operator_override'->>'reason'
              = '{UNAUTHORIZED_OVERRIDE_REASON}'
          AND COALESCE(
                (allocation.metadata->'operator_override'
                    ->>'previous_max_parallel_task_claims')::integer,
                0
              ) = entry.max_parallel_task_claims
        """
    )


def downgrade() -> None:
    # Capacity restoration is deliberately irreversible. Reapplying the
    # unauthorized single-inflight override would silently reduce capability;
    # any future reduction requires a separately authorized migration.
    pass
