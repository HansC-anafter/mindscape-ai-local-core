#!/usr/bin/env python3
"""
Complete Data Migration: SQLite -> PostgreSQL

Migrates ALL data from SQLite to PostgreSQL.
Run inside Docker: docker compose exec backend python /app/backend/scripts/migrate_all_data_to_postgres.py

Or from host with correct DATABASE_URL_CORE pointing to localhost:5432.
"""

import os
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv

load_dotenv()

# Tables to migrate (ordered by dependency)
PRIORITY_TABLES = [
    "profiles",  # No deps
    "workspaces",  # Depends on profiles
    "projects",  # Depends on workspaces
    "tasks",  # Depends on projects
    "playbooks",
    "playbook_flows",
    "playbook_executions",
    "intents",
    "intent_tags",
    "intent_logs",
    "artifacts",
    "timeline_items",
    "mind_events",
    "surface_events",
    "conversation_threads",
    "thread_references",
    "tool_calls",
    "background_routines",
    "lens_receipts",
    "lens_compositions",
    "lens_profile_nodes",
    "lens_specs",
    "lens_snapshots",
    "mind_lens_profiles",
    "mind_lens_schemas",
    "mind_lens_instances",
    "mind_lens_workspace_bindings",
    "mind_lens_active_nodes",
    "workspace_lens_overrides",
    "graph_nodes",
    "graph_edges",
    "graph_node_entity_links",
    "graph_node_intent_links",
    "graph_node_playbook_links",
    "entities",
    "entity_tags",
    "tags",
    "habit_candidates",
    "habit_observations",
    "habit_audit_logs",
    "model_configs",
    "model_providers",
    "system_settings",
    "user_configs",
    "user_playbook_meta",
    "personalized_playbooks",
    "workspace_pinned_playbooks",
    "saved_views",
    "tool_slot_mappings",
    "task_feedback",
    "task_preference",
    "preview_votes",
    "baseline_events",
    "web_generation_baselines",
    "stage_results",
    "project_phases",
    "commands",
    "agent_executions",
    "runner_locks",
    "embedding_migrations",
    "embedding_migration_items",
    "capability_ui_components",
    "intent_clusters",
    "intent_playbook_associations",
    "artifact_registry",
    "mindscape_personal",
    "installed_packs",
    "tool_registry",
    "tool_connections",
]


def get_sqlite_connection(sqlite_path: str) -> sqlite3.Connection:
    """Get SQLite connection with row factory"""
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_postgres_connection():
    """Get PostgreSQL connection via SQLAlchemy"""
    from sqlalchemy import create_engine, text

    db_url = os.environ.get("DATABASE_URL_CORE")
    if not db_url:
        raise ValueError("DATABASE_URL_CORE not set")

    engine = create_engine(db_url)
    return engine


def get_table_columns(sqlite_conn: sqlite3.Connection, table_name: str) -> List[str]:
    """Get column names for a SQLite table"""
    cursor = sqlite_conn.execute(f"PRAGMA table_info({table_name})")
    return [row["name"] for row in cursor.fetchall()]


def get_postgres_columns(pg_engine, table_name: str) -> List[str]:
    """Get column names for a PostgreSQL table"""
    from sqlalchemy import text

    with pg_engine.connect() as conn:
        result = conn.execute(
            text(
                f"""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = :table_name
            AND table_schema = 'public'
            ORDER BY ordinal_position
        """
            ),
            {"table_name": table_name},
        )
        return [row[0] for row in result.fetchall()]


def table_exists_postgres(pg_engine, table_name: str) -> bool:
    """Check if table exists in PostgreSQL"""
    from sqlalchemy import text

    with pg_engine.connect() as conn:
        result = conn.execute(
            text(
                """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.tables
                WHERE table_name = :table_name
                AND table_schema = 'public'
            )
        """
            ),
            {"table_name": table_name},
        )
        return result.scalar()


def get_postgres_count(pg_engine, table_name: str) -> int:
    """Get row count in PostgreSQL table"""
    from sqlalchemy import text

    with pg_engine.connect() as conn:
        result = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
        return result.scalar()


def sanitize_value(value: Any, col_name: str) -> Any:
    """Sanitize value for PostgreSQL insertion"""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        # Handle JSON columns
        if col_name in [
            "metadata",
            "config",
            "data",
            "content",
            "schema",
            "expected_artifacts",
            "data_sources",
            "playbook_auto_execution_config",
            "suggestion_history",
            "storage_config",
            "playbook_storage_config",
            "cloud_remote_tools_config",
            "workspace_blueprint",
            "associated_roles",
            "allowed_agent_roles",
            "input_schema",
            "methods",
            "artifact_types",
            "playbook_codes",
            "x_platform",
            "oauth_token",
            "oauth_refresh_token",
        ]:
            # Return as-is, will be stored as text
            return value
    return value


def migrate_table(
    sqlite_conn: sqlite3.Connection, pg_engine, table_name: str, batch_size: int = 1000
) -> tuple:
    """Migrate a single table from SQLite to PostgreSQL"""
    from sqlalchemy import text

    # Check if table exists in both databases
    sqlite_cols = get_table_columns(sqlite_conn, table_name)
    if not sqlite_cols:
        return 0, 0, f"Table {table_name} not found in SQLite"

    if not table_exists_postgres(pg_engine, table_name):
        return 0, 0, f"Table {table_name} not found in PostgreSQL"

    pg_cols = get_postgres_columns(pg_engine, table_name)

    # Find common columns
    common_cols = [c for c in sqlite_cols if c in pg_cols]
    if not common_cols:
        return 0, 0, f"No common columns between SQLite and PostgreSQL for {table_name}"

    # Get existing count in PostgreSQL
    existing_count = get_postgres_count(pg_engine, table_name)

    # Read from SQLite
    cols_str = ", ".join([f'"{c}"' for c in common_cols])
    cursor = sqlite_conn.execute(f'SELECT {cols_str} FROM "{table_name}"')
    rows = cursor.fetchall()

    if not rows:
        return 0, existing_count, "No data in SQLite"

    # Build INSERT statement with ON CONFLICT DO NOTHING
    placeholders = ", ".join([f":{c}" for c in common_cols])
    insert_sql = f"""
        INSERT INTO "{table_name}" ({cols_str})
        VALUES ({placeholders})
        ON CONFLICT DO NOTHING
    """

    migrated = 0
    skipped = 0
    with pg_engine.connect() as conn:
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            for row in batch:
                # Use savepoint to isolate individual row failures
                savepoint = conn.begin_nested()
                try:
                    row_dict = {c: sanitize_value(row[c], c) for c in common_cols}
                    conn.execute(text(insert_sql), row_dict)
                    savepoint.commit()
                    migrated += 1
                except Exception as e:
                    # Rollback savepoint and continue with next row
                    savepoint.rollback()
                    skipped += 1
            # Commit the batch
            conn.commit()

    return migrated, skipped, None


def main():
    print("=" * 70)
    print("Complete Data Migration: SQLite -> PostgreSQL")
    print("=" * 70)

    # Find SQLite database
    sqlite_paths = [
        Path("/app/data/mindscape.db"),  # Docker
        Path(__file__).parent.parent.parent / "data" / "mindscape.db",
        Path(__file__).parent.parent / "data" / "mindscape.db",
        Path(__file__).parent.parent / "mindscape.db",
    ]

    sqlite_path = None
    for p in sqlite_paths:
        if p.exists():
            sqlite_path = p
            break

    if not sqlite_path:
        print("ERROR: SQLite database not found")
        print("Tried paths:", [str(p) for p in sqlite_paths])
        sys.exit(1)

    print(f"\nSource: {sqlite_path}")
    print(f"Target: PostgreSQL (DATABASE_URL_CORE)")

    # Connect to databases
    sqlite_conn = get_sqlite_connection(str(sqlite_path))
    pg_engine = get_postgres_connection()

    # Get all SQLite tables
    cursor = sqlite_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'alembic%'"
    )
    sqlite_tables = {row["name"] for row in cursor.fetchall()}

    # Determine migration order
    tables_to_migrate = []
    for t in PRIORITY_TABLES:
        if t in sqlite_tables:
            tables_to_migrate.append(t)

    # Add any remaining tables not in priority list
    for t in sorted(sqlite_tables):
        if t not in tables_to_migrate and t != "alembic_version":
            tables_to_migrate.append(t)

    print(f"\nFound {len(tables_to_migrate)} tables to migrate\n")
    print("-" * 70)

    total_migrated = 0
    total_skipped = 0
    errors = []

    for table in tables_to_migrate:
        try:
            migrated, skipped, error = migrate_table(sqlite_conn, pg_engine, table)

            if error:
                print(f"  [SKIP] {table}: {error}")
                total_skipped += 1
            else:
                status = "OK" if migrated > 0 else "NONE"
                skip_info = f", {skipped} skipped" if skipped > 0 else ""
                print(f"  [{status}] {table}: +{migrated} rows{skip_info}")
                total_migrated += migrated
        except Exception as e:
            print(f"  [ERROR] {table}: {str(e)[:50]}")
            errors.append((table, str(e)))

    print("-" * 70)
    print(f"\nMigration complete!")
    print(f"  Total rows migrated: {total_migrated}")
    print(f"  Tables skipped: {total_skipped}")
    print(f"  Errors: {len(errors)}")

    if errors:
        print("\nErrors:")
        for table, err in errors:
            print(f"  - {table}: {err[:80]}")

    print("=" * 70)

    sqlite_conn.close()


if __name__ == "__main__":
    main()
