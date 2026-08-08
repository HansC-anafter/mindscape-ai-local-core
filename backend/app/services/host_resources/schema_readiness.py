"""Read-only schema readiness checks for host resource durable ledger."""

from __future__ import annotations

from contextlib import nullcontext
from typing import Any

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase


REQUIRED_REVISION = "20260604173000"
UPGRADE_COMMAND = "alembic -c backend/alembic.postgres.ini upgrade heads"
REQUIRED_TABLES = (
    "host_resource_reservations",
    "host_resource_events",
    "host_resource_lanes",
    "host_resource_workspace_allocations",
    "host_resource_allocation_blueprints",
    "host_resource_allocation_blueprint_entries",
    "host_resource_workspace_allocation_applications",
)
REQUIRED_INDEXES = (
    "idx_host_resource_reservations_active",
    "idx_host_resource_reservations_lane_created",
    "idx_host_resource_events_reservation_time",
    "idx_host_resource_events_type_time",
    "idx_host_resource_lanes_workspace_scope",
    "idx_host_resource_lanes_capability_kind",
    "idx_host_resource_lanes_queue_shard",
    "uq_host_resource_workspace_allocations_workspace_lane",
    "idx_host_resource_workspace_allocations_lane_state",
    "idx_host_resource_workspace_allocations_workspace_state",
    "uq_host_resource_workspace_allocations_workspace_queue_family",
    "uq_host_resource_allocation_blueprint_entries_blueprint_queue_family",
    "uq_host_resource_workspace_allocation_applications_workspace_blueprint",
    "idx_host_resource_workspace_allocations_queue_family_state",
    "idx_host_resource_workspace_allocations_blueprint",
    "idx_tasks_workspace_queue_running_pack",
)
REQUIRED_COLUMNS = {
    "host_resource_workspace_allocations": (
        "queue_shard",
        "task_family",
        "max_parallel_task_claims",
        "share_policy",
        "priority_ceiling",
        "blueprint_id",
        "blueprint_entry_id",
        "applied_at",
    ),
    "host_resource_allocation_blueprints": (
        "blueprint_id",
        "label",
        "scope",
        "state",
        "metadata",
    ),
    "host_resource_allocation_blueprint_entries": (
        "blueprint_entry_id",
        "blueprint_id",
        "queue_shard",
        "task_family",
        "max_parallel_task_claims",
        "task_selectors",
    ),
    "host_resource_workspace_allocation_applications": (
        "application_id",
        "workspace_id",
        "blueprint_id",
        "state",
        "applied_at",
    ),
}


def _revision_covers_required(version_num: str) -> bool:
    normalized = str(version_num or "").strip()
    if normalized == REQUIRED_REVISION:
        return True
    if normalized.isdigit() and REQUIRED_REVISION.isdigit():
        return normalized >= REQUIRED_REVISION
    return False


def _connection_context(store: Any):
    if store is None:
        return PostgresStoreBase("core").get_connection()
    return store.get_connection() if hasattr(store, "get_connection") else nullcontext(store)


def _regclass_exists(conn: Any, object_name: str) -> bool:
    row = conn.execute(
        text("SELECT to_regclass(:object_name) IS NOT NULL AS exists"),
        {"object_name": f"public.{object_name}"},
    )
    return bool(row.scalar())


def _table_columns(conn: Any, table_name: str) -> set[str]:
    rows = conn.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    ).fetchall()
    return {
        str(row._mapping.get("column_name") if hasattr(row, "_mapping") else row[0])
        for row in rows
        if row
    }


def check_host_resource_schema_readiness(store: Any | None = None) -> dict[str, Any]:
    """Return a read-only readiness report for host resource ledger schema."""

    tables: dict[str, bool] = {}
    indexes: dict[str, bool] = {}
    columns: dict[str, dict[str, bool]] = {}
    applied_revisions: list[str] = []
    migration_applied = False
    connectable = False
    error: str | None = None

    try:
        with _connection_context(store) as conn:
            connectable = True
            for table_name in REQUIRED_TABLES:
                tables[table_name] = _regclass_exists(conn, table_name)
            for index_name in REQUIRED_INDEXES:
                indexes[index_name] = _regclass_exists(conn, index_name)
            for table_name, required_columns in REQUIRED_COLUMNS.items():
                existing_columns = _table_columns(conn, table_name)
                columns[table_name] = {
                    column_name: column_name in existing_columns
                    for column_name in required_columns
                }

            if _regclass_exists(conn, "alembic_version"):
                rows = conn.execute(
                    text("SELECT version_num FROM alembic_version ORDER BY version_num")
                ).fetchall()
                for row in rows:
                    mapping = getattr(row, "_mapping", None)
                    if mapping is not None:
                        version_num = mapping.get("version_num")
                    elif isinstance(row, dict):
                        version_num = row.get("version_num")
                    else:
                        version_num = row[0] if row else None
                    if version_num:
                        applied_revisions.append(str(version_num))
                migration_applied = any(
                    _revision_covers_required(version)
                    for version in applied_revisions
                )
    except Exception as exc:
        error = str(exc)

    missing_tables = [
        table_name for table_name, exists in tables.items() if not exists
    ] or ([] if tables else list(REQUIRED_TABLES))
    missing_indexes = [
        index_name for index_name, exists in indexes.items() if not exists
    ] or ([] if indexes else list(REQUIRED_INDEXES))
    missing_columns = {
        table_name: [
            column_name
            for column_name, exists in table_columns.items()
            if not exists
        ]
        for table_name, table_columns in columns.items()
    }
    missing_columns = {
        table_name: column_names
        for table_name, column_names in missing_columns.items()
        if column_names
    }
    if not columns:
        missing_columns = {
            table_name: list(required_columns)
            for table_name, required_columns in REQUIRED_COLUMNS.items()
        }
    ready = bool(
        connectable
        and not missing_tables
        and not missing_indexes
        and not missing_columns
        and migration_applied
    )
    return {
        "scope": "host-resource-only",
        "ready": ready,
        "connectable": connectable,
        "required_revision": REQUIRED_REVISION,
        "migration_applied": migration_applied,
        "applied_revisions": applied_revisions,
        "tables": tables,
        "indexes": indexes,
        "columns": columns,
        "missing_tables": missing_tables,
        "missing_indexes": missing_indexes,
        "missing_columns": missing_columns,
        "upgrade_command": UPGRADE_COMMAND,
        "error": error,
    }
