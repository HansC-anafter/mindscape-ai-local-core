"""
DEPRECATED: This script uses legacy SQLite database access (sqlite3.connect).
PostgreSQL is now the primary database. This script is retained for historical reference only.
Last updated: 2026-01-27

Tool Connection Migration Script

Migrates tool connections from old system (ToolConnectionStore/SQLite - DEPRECATED)
to new system (ToolRegistryService/SQLite).

Note: The old system (ToolConnectionStore) has been fully deprecated and removed
from the active codebase. This script is kept for historical data migration purposes.

Usage:
    python -m backend.scripts.migrate_tool_connections [--db-path PATH] [--data-dir DIR] [--dry-run]
"""

import sqlite3
import json
import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.app.models.tool_connection import ToolConnection
from backend.app.models.tool_registry import ToolConnectionModel
from backend.app.services.tool_registry import ToolRegistryService


def load_old_connections(db_path: str) -> List[ToolConnection]:
    """
    Load connections from old SQLite database

    Args:
        db_path: Path to SQLite database

    Returns:
        List of ToolConnection objects
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM tool_connections")
    rows = cursor.fetchall()
    conn.close()

    connections = []
    for row in rows:
        try:
            # Parse JSON fields
            config = json.loads(row["config"]) if row["config"] else {}
            associated_roles = (
                json.loads(row["associated_roles"]) if row["associated_roles"] else []
            )
            x_platform = json.loads(row["x_platform"]) if row["x_platform"] else None

            # Parse datetime fields
            created_at = (
                datetime.fromisoformat(row["created_at"])
                if row["created_at"]
                else datetime.utcnow()
            )
            updated_at = (
                datetime.fromisoformat(row["updated_at"])
                if row["updated_at"]
                else datetime.utcnow()
            )
            last_validated_at = (
                datetime.fromisoformat(row["last_validated_at"])
                if row["last_validated_at"]
                else None
            )
            last_used_at = (
                datetime.fromisoformat(row["last_used_at"])
                if row["last_used_at"]
                else None
            )

            connection = ToolConnection(
                id=row["id"],
                profile_id=row["profile_id"],
                tool_type=row["tool_type"],
                connection_type=row["connection_type"],
                name=row["name"],
                description=row["description"],
                icon=row["icon"],
                api_key=row["api_key"],
                api_secret=row["api_secret"],
                oauth_token=row["oauth_token"],
                oauth_refresh_token=row["oauth_refresh_token"],
                base_url=row["base_url"],
                remote_cluster_url=row["remote_cluster_url"],
                remote_connection_id=row["remote_connection_id"],
                config=config,
                associated_roles=associated_roles,
                is_active=bool(row["is_active"]),
                is_validated=bool(row["is_validated"]),
                last_validated_at=last_validated_at,
                validation_error=row["validation_error"],
                usage_count=row["usage_count"],
                last_used_at=last_used_at,
                created_at=created_at,
                updated_at=updated_at,
                x_platform=x_platform,
            )
            connections.append(connection)
        except Exception as e:
            print(f"Error loading connection {row['id']}: {e}")
            continue

    return connections


def convert_to_new_model(old_conn: ToolConnection) -> ToolConnectionModel:
    """
    Convert old ToolConnection to new ToolConnectionModel

    Args:
        old_conn: Old ToolConnection object

    Returns:
        New ToolConnectionModel object
    """
    # Map tool_type to determine if WordPress-specific fields should be set
    is_wordpress = old_conn.tool_type == "wordpress"

    return ToolConnectionModel(
        id=old_conn.id,
        profile_id=old_conn.profile_id,
        tool_type=old_conn.tool_type,
        connection_type=old_conn.connection_type,
        name=old_conn.name,
        description=old_conn.description,
        icon=old_conn.icon,
        api_key=old_conn.api_key,
        api_secret=old_conn.api_secret,
        oauth_token=old_conn.oauth_token,
        oauth_refresh_token=old_conn.oauth_refresh_token,
        base_url=old_conn.base_url,
        # WordPress-specific fields (backward compatibility)
        wp_url=old_conn.base_url if is_wordpress else None,
        wp_username=old_conn.api_key if is_wordpress else None,
        wp_application_password=old_conn.api_secret if is_wordpress else None,
        # Remote connection fields
        remote_cluster_url=old_conn.remote_cluster_url,
        remote_connection_id=old_conn.remote_connection_id,
        # Configuration
        config=old_conn.config,
        associated_roles=old_conn.associated_roles,
        # Status
        enabled=old_conn.is_active,
        is_active=old_conn.is_active,
        is_validated=old_conn.is_validated,
        last_validated_at=old_conn.last_validated_at,
        validation_error=old_conn.validation_error,
        # Statistics
        usage_count=old_conn.usage_count,
        last_used_at=old_conn.last_used_at,
        # Discovery fields (not in old model, set to None)
        last_discovery=None,
        discovery_method=None,
        # Extension point
        x_platform=old_conn.x_platform,
        # Timestamps
        created_at=old_conn.created_at,
        updated_at=old_conn.updated_at,
    )


def migrate_connections(
    db_path: str, data_dir: str, dry_run: bool = False
) -> Dict[str, Any]:
    """
    Migrate connections from old system to new system

    Args:
        db_path: Path to old SQLite database
        data_dir: Data directory for new system
        dry_run: If True, don't actually migrate, just report

    Returns:
        Migration statistics
    """
    print(f"Loading connections from {db_path}...")
    old_connections = load_old_connections(db_path)
    print(f"Found {len(old_connections)} connections")

    if dry_run:
        print("\n=== DRY RUN MODE ===")
        print("Would migrate the following connections:")
        for conn in old_connections:
            print(f"  - {conn.id} ({conn.tool_type}) for profile {conn.profile_id}")
        return {
            "total": len(old_connections),
            "migrated": 0,
            "errors": 0,
            "dry_run": True,
        }

    # Initialize new system
    registry = ToolRegistryService(data_dir=data_dir)

    # Migrate each connection
    migrated = 0
    errors = 0

    for old_conn in old_connections:
        try:
            new_conn = convert_to_new_model(old_conn)
            registry.create_connection(new_conn)
            migrated += 1
            print(f"Migrated: {old_conn.id} ({old_conn.tool_type})")
        except Exception as e:
            errors += 1
            print(f"Error migrating {old_conn.id}: {e}")

    print(f"\nMigration complete: {migrated} migrated, {errors} errors")

    return {
        "total": len(old_connections),
        "migrated": migrated,
        "errors": errors,
        "dry_run": False,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Migrate tool connections from old to new system"
    )
    parser.add_argument(
        "--db-path",
        default="data/my_agent_console.db",
        help="Path to old SQLite database",
    )
    parser.add_argument(
        "--data-dir", default="./data", help="Data directory for new system"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without actually migrating",
    )

    args = parser.parse_args()

    # Check if database exists
    if not Path(args.db_path).exists():
        print(f"Error: Database not found at {args.db_path}")
        sys.exit(1)

    # Run migration
    stats = migrate_connections(
        db_path=args.db_path, data_dir=args.data_dir, dry_run=args.dry_run
    )

    if stats["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
