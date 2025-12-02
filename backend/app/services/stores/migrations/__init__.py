"""
Database migrations for Mindscape stores
Handles schema versioning and incremental migrations
"""

from backend.app.services.stores.migrations.migration_001_add_workspace_id import migrate_001_add_workspace_id
from backend.app.services.stores.migrations.migration_002_add_events_pagination_index import migrate_002_add_events_pagination_index
from backend.app.services.stores.migrations.migration_003_add_artifacts_table import migrate_003_add_artifacts_table
from backend.app.services.stores.migrations.migration_004_add_workspace_storage_config import migrate_004_add_workspace_storage_config
from backend.app.services.stores.migrations.migration_005_add_readiness_status import migrate_005_add_readiness_status
from backend.app.services.stores.migrations.migration_006_add_task_feedback import migrate_006_add_task_feedback
from backend.app.services.stores.migrations.migration_007_add_task_preference import migrate_007_add_task_preference

# Migration registry: (version, name, function)
MIGRATIONS = [
    (1, 'add_workspace_id', migrate_001_add_workspace_id),
    (2, 'add_events_pagination_index', migrate_002_add_events_pagination_index),
    (3, 'add_artifacts_table', migrate_003_add_artifacts_table),
    (4, 'add_workspace_storage_config', migrate_004_add_workspace_storage_config),
    (5, 'add_readiness_status', migrate_005_add_readiness_status),
    (6, 'add_task_feedback', migrate_006_add_task_feedback),
    (7, 'add_task_preference', migrate_007_add_task_preference),
]


def get_current_version(cursor) -> int:
    """
    Get current database schema version

    Uses PRAGMA user_version to track schema version
    """
    cursor.execute("PRAGMA user_version")
    result = cursor.fetchone()
    return result[0] if result else 0


def set_version(cursor, version: int):
    """Set database schema version"""
    cursor.execute(f"PRAGMA user_version = {version}")


def run_migrations(cursor, target_version: int = None):
    """
    Run all pending migrations

    Args:
        cursor: Database cursor
        target_version: Target version (None = run all pending)
    """
    current_version = get_current_version(cursor)

    if target_version is None:
        target_version = max(version for version, _, _ in MIGRATIONS)

    for version, name, migrate_func in MIGRATIONS:
        if version > current_version and version <= target_version:
            migrate_func(cursor)
            set_version(cursor, version)
