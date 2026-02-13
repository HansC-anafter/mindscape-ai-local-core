"""
Automatic SQLite to PostgreSQL data migration.

Detects legacy SQLite database on startup and migrates data to PostgreSQL
if the database is empty. This ensures a seamless upgrade experience for
users who had data in the SQLite era.

Safety guarantees:
- Only runs if SQLite file exists at known paths
- Only runs if marker file (.sqlite_migrated) does NOT exist
- Only runs if PostgreSQL core tables are empty
- Uses ON CONFLICT DO NOTHING for idempotent row insertion
- Never blocks startup on failure (errors are logged as warnings)
"""

import os
import sys
import json
import sqlite3
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Tables to migrate in dependency order (matches migrate_all_data_to_postgres.py)
PRIORITY_TABLES = [
    "profiles",
    "workspaces",
    "projects",
    "tasks",
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

# Tables whose data loss is catastrophic (settings/configuration)
CRITICAL_TABLES = [
    "profiles",
    "workspaces",
    "system_settings",
    "user_configs",
    "model_configs",
    "model_providers",
    "tool_registry",
    "tool_connections",
]

# Marker file placed after successful migration
MARKER_FILENAME = ".sqlite_migrated"


def detect_sqlite_database() -> Optional[Path]:
    """Scan known paths for an existing SQLite database file."""
    candidates = [
        Path("/app/data/mindscape.db"),
        Path(__file__).parent.parent.parent.parent / "data" / "mindscape.db",
        Path(__file__).parent.parent.parent / "data" / "mindscape.db",
        Path(__file__).parent.parent / "data" / "mindscape.db",
    ]
    for p in candidates:
        if p.exists() and p.stat().st_size > 0:
            return p.resolve()
    return None


def _marker_path(sqlite_path: Path) -> Path:
    """Return the marker file path next to the SQLite database."""
    return sqlite_path.parent / MARKER_FILENAME


def _marker_exists(sqlite_path: Path) -> bool:
    """Check if the migration marker file exists."""
    return _marker_path(sqlite_path).exists()


def _write_marker(sqlite_path: Path, result: Dict[str, Any]) -> None:
    """Write marker file after successful migration."""
    import json
    from datetime import datetime, timezone

    marker = _marker_path(sqlite_path)
    marker.write_text(
        json.dumps(
            {
                "migrated_at": datetime.now(timezone.utc).isoformat(),
                "source": str(sqlite_path),
                "total_rows": result.get("total_rows", 0),
                "tables_migrated": result.get("tables_migrated", 0),
                "critical_verified": result.get("critical_verified", False),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    logger.info(f"Migration marker written: {marker}")


def _get_pg_engine():
    """Get PostgreSQL engine from existing application config."""
    from sqlalchemy import create_engine

    db_url = os.environ.get("DATABASE_URL_CORE") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL_CORE not set")
    return create_engine(db_url)


def _pg_table_exists(pg_engine, table_name: str) -> bool:
    """Check if a table exists in PostgreSQL."""
    from sqlalchemy import text

    with pg_engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables"
                "  WHERE table_name = :t AND table_schema = 'public'"
                ")"
            ),
            {"t": table_name},
        )
        return result.scalar()


def _pg_row_count(pg_engine, table_name: str) -> int:
    """Get row count of a PostgreSQL table."""
    from sqlalchemy import text

    with pg_engine.connect() as conn:
        result = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
        return result.scalar() or 0


def _sqlite_row_count(sqlite_path: Path, table_name: str) -> int:
    """Get row count of a SQLite table (returns 0 if table missing)."""
    try:
        conn = sqlite3.connect(str(sqlite_path))
        cursor = conn.execute(f'SELECT COUNT(*) FROM "{table_name}"')
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0


def _is_postgres_empty(pg_engine) -> bool:
    """Check if PostgreSQL core tables are empty (migration has not run)."""
    for table in ("profiles", "workspaces", "system_settings"):
        if _pg_table_exists(pg_engine, table) and _pg_row_count(pg_engine, table) > 0:
            return False
    return True


def _get_sqlite_tables(sqlite_conn: sqlite3.Connection) -> set:
    """Get all user table names from SQLite."""
    cursor = sqlite_conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'alembic%'"
    )
    return {row[0] for row in cursor.fetchall()}


def _get_columns(sqlite_conn: sqlite3.Connection, table_name: str) -> List[str]:
    """Get column names for a SQLite table."""
    cursor = sqlite_conn.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def _get_pg_columns(pg_engine, table_name: str) -> List[str]:
    """Get column names for a PostgreSQL table."""
    from sqlalchemy import text

    with pg_engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = :t AND table_schema = 'public' "
                "ORDER BY ordinal_position"
            ),
            {"t": table_name},
        )
        return [row[0] for row in result.fetchall()]


def _sanitize_value(value: Any, col_name: str) -> Any:
    """Sanitize a value for PostgreSQL insertion."""
    if value is None:
        return None
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _migrate_table(
    sqlite_conn: sqlite3.Connection,
    pg_engine,
    table_name: str,
    batch_size: int = 500,
) -> Tuple[int, int, Optional[str]]:
    """Migrate a single table. Returns (migrated, skipped, error_msg)."""
    from sqlalchemy import text

    sqlite_cols = _get_columns(sqlite_conn, table_name)
    if not sqlite_cols:
        return 0, 0, f"not found in SQLite"

    if not _pg_table_exists(pg_engine, table_name):
        return 0, 0, f"not found in PostgreSQL"

    pg_cols = _get_pg_columns(pg_engine, table_name)
    common_cols = [c for c in sqlite_cols if c in pg_cols]
    if not common_cols:
        return 0, 0, f"no common columns"

    cols_str = ", ".join([f'"{c}"' for c in common_cols])
    cursor = sqlite_conn.execute(f'SELECT {cols_str} FROM "{table_name}"')
    rows = cursor.fetchall()

    if not rows:
        return 0, 0, None

    placeholders = ", ".join([f":{c}" for c in common_cols])
    insert_sql = (
        f'INSERT INTO "{table_name}" ({cols_str}) '
        f"VALUES ({placeholders}) "
        f"ON CONFLICT DO NOTHING"
    )

    migrated = 0
    skipped = 0

    with pg_engine.connect() as conn:
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            for row in batch:
                savepoint = conn.begin_nested()
                try:
                    row_dict = {
                        c: _sanitize_value(row[idx], c)
                        for idx, c in enumerate(common_cols)
                    }
                    conn.execute(text(insert_sql), row_dict)
                    savepoint.commit()
                    migrated += 1
                except Exception:
                    savepoint.rollback()
                    skipped += 1
            conn.commit()

    return migrated, skipped, None


def _verify_critical_tables(pg_engine, sqlite_path: Path) -> Tuple[bool, List[str]]:
    """Verify critical settings tables migrated correctly. Returns (ok, issues)."""
    issues = []
    for table in CRITICAL_TABLES:
        sqlite_count = _sqlite_row_count(sqlite_path, table)
        if sqlite_count == 0:
            continue
        if not _pg_table_exists(pg_engine, table):
            issues.append(
                f"{table}: missing in PostgreSQL (SQLite has {sqlite_count} rows)"
            )
            continue
        pg_count = _pg_row_count(pg_engine, table)
        if pg_count == 0:
            issues.append(
                f"{table}: 0 rows in PostgreSQL (SQLite has {sqlite_count} rows)"
            )
    return len(issues) == 0, issues


def run_auto_migration() -> Dict[str, Any]:
    """
    Main entry point: detect SQLite DB and auto-migrate if conditions are met.

    Returns a result dict:
        status: "migrated" | "skipped" | "error"
        reason: why skipped (if applicable)
        total_rows: total rows migrated
        tables_migrated: number of tables with data migrated
        critical_verified: whether critical tables passed verification
        error: error message (if applicable)
    """
    # Guard 1: detect SQLite database
    sqlite_path = detect_sqlite_database()
    if sqlite_path is None:
        return {"status": "skipped", "reason": "no SQLite database found"}

    logger.info(f"Legacy SQLite database detected: {sqlite_path}")

    # Guard 2: check marker file
    if _marker_exists(sqlite_path):
        return {
            "status": "skipped",
            "reason": "migration already completed (marker exists)",
        }

    # Get PostgreSQL engine
    try:
        pg_engine = _get_pg_engine()
    except Exception as e:
        return {"status": "error", "error": f"cannot connect to PostgreSQL: {e}"}

    # Guard 3: check if PostgreSQL already has data
    if not _is_postgres_empty(pg_engine):
        logger.info(
            "PostgreSQL already has data, skipping auto migration. "
            "Writing marker to prevent future checks."
        )
        _write_marker(
            sqlite_path,
            {"total_rows": 0, "tables_migrated": 0, "critical_verified": True},
        )
        return {"status": "skipped", "reason": "PostgreSQL already has data"}

    # All guards passed — run migration
    logger.info("=" * 60)
    logger.info("AUTO MIGRATION: SQLite -> PostgreSQL")
    logger.info(f"Source: {sqlite_path}")
    logger.info("=" * 60)

    sqlite_conn = sqlite3.connect(str(sqlite_path))
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_tables = _get_sqlite_tables(sqlite_conn)

    # Build ordered table list
    tables_to_migrate = [t for t in PRIORITY_TABLES if t in sqlite_tables]
    for t in sorted(sqlite_tables):
        if t not in tables_to_migrate:
            tables_to_migrate.append(t)

    total_rows = 0
    tables_migrated = 0
    errors = []

    for table in tables_to_migrate:
        try:
            migrated, skipped, error = _migrate_table(sqlite_conn, pg_engine, table)
            if error:
                logger.debug(f"  [SKIP] {table}: {error}")
            elif migrated > 0:
                logger.info(
                    f"  [OK] {table}: +{migrated} rows"
                    + (f", {skipped} skipped" if skipped else "")
                )
                total_rows += migrated
                tables_migrated += 1
            else:
                logger.debug(f"  [EMPTY] {table}")
        except Exception as e:
            logger.warning(f"  [ERROR] {table}: {e}")
            errors.append((table, str(e)))

    sqlite_conn.close()

    # Verify critical tables
    critical_ok, critical_issues = _verify_critical_tables(pg_engine, sqlite_path)
    if not critical_ok:
        logger.error("CRITICAL: Settings data migration issues detected!")
        for issue in critical_issues:
            logger.error(f"  {issue}")
        logger.error(
            "Manual migration available: docker compose exec backend "
            "python /app/backend/scripts/migrate_all_data_to_postgres.py"
        )

    result = {
        "status": "migrated",
        "total_rows": total_rows,
        "tables_migrated": tables_migrated,
        "errors": len(errors),
        "critical_verified": critical_ok,
    }

    logger.info("=" * 60)
    logger.info(
        f"Migration complete: {total_rows} rows across {tables_migrated} tables"
    )
    if errors:
        logger.warning(f"  Errors: {len(errors)}")
    logger.info(f"  Critical tables verified: {critical_ok}")
    logger.info("=" * 60)

    # Write marker to prevent re-execution
    _write_marker(sqlite_path, result)

    pg_engine.dispose()
    return result
