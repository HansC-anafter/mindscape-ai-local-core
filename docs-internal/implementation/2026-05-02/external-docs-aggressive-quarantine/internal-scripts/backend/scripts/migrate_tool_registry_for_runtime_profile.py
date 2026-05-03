"""
Tool Registry Migration Script for Runtime Profile

Adds capability_code and risk_class fields to existing RegisteredTool records.

Usage:
    python -m backend.scripts.migrate_tool_registry_for_runtime_profile [--db-path PATH] [--dry-run]
"""

import sqlite3
import json
import argparse
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.app.models.tool_registry import RegisteredTool


def get_db_path(db_path: Optional[str] = None) -> str:
    """Get database path"""
    if db_path:
        return db_path

    # Default: use data directory
    data_dir = Path("./data")
    return str(data_dir / "tool_registry.db")


def migrate_tool_registry(db_path: str, dry_run: bool = False) -> Dict[str, Any]:
    """
    Migrate tool registry to add capability_code and risk_class

    Args:
        db_path: Path to tool_registry database
        dry_run: If True, only report changes without applying them

    Returns:
        Migration statistics
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Check if columns exist
    cursor.execute("PRAGMA table_info(tool_registry)")
    columns = [row[1] for row in cursor.fetchall()]

    needs_capability_code = "capability_code" not in columns
    needs_risk_class = "risk_class" not in columns

    stats = {
        "total_tools": 0,
        "updated_tools": 0,
        "errors": 0,
        "added_capability_code": 0,
        "added_risk_class": 0,
        "mapped_risk_class": 0,
    }

    # Add columns if needed
    if needs_capability_code:
        if not dry_run:
            cursor.execute("ALTER TABLE tool_registry ADD COLUMN capability_code TEXT DEFAULT ''")
            conn.commit()
        print("✓ Added capability_code column")

    if needs_risk_class:
        if not dry_run:
            cursor.execute("ALTER TABLE tool_registry ADD COLUMN risk_class TEXT DEFAULT 'readonly'")
            conn.commit()
        print("✓ Added risk_class column")

    # Load all tools
    cursor.execute("SELECT * FROM tool_registry")
    rows = cursor.fetchall()
    stats["total_tools"] = len(rows)

    # Migration logic
    for row in rows:
        try:
            # Parse existing data
            tool_id = row["tool_id"]
            origin_capability_id = row.get("origin_capability_id", "")
            side_effect_level = row.get("side_effect_level")
            danger_level = row.get("danger_level", "low")

            # Get current values (may be None for new columns)
            current_capability_code = row.get("capability_code") or ""
            current_risk_class = row.get("risk_class") or ""

            updates = {}

            # 1. Set capability_code (default to origin_capability_id if empty)
            if not current_capability_code and origin_capability_id:
                updates["capability_code"] = origin_capability_id
                stats["added_capability_code"] += 1

            # 2. Set risk_class (map from side_effect_level or danger_level)
            if not current_risk_class or current_risk_class == "readonly":
                # Map from side_effect_level (preferred)
                if side_effect_level:
                    mapping = {
                        "readonly": "readonly",
                        "soft_write": "soft_write",
                        "external_write": "external_write"
                    }
                    risk_class = mapping.get(side_effect_level, "readonly")
                    if risk_class != current_risk_class:
                        updates["risk_class"] = risk_class
                        stats["mapped_risk_class"] += 1
                # Fallback to danger_level
                elif danger_level == "high":
                    updates["risk_class"] = "external_write"
                    stats["added_risk_class"] += 1
                elif danger_level == "medium":
                    updates["risk_class"] = "soft_write"
                    stats["added_risk_class"] += 1
                # Default is already "readonly"

            # Apply updates
            if updates:
                if not dry_run:
                    set_clauses = []
                    values = []
                    for key, value in updates.items():
                        set_clauses.append(f"{key} = ?")
                        values.append(value)
                    values.append(tool_id)

                    cursor.execute(
                        f"UPDATE tool_registry SET {', '.join(set_clauses)}, updated_at = ? WHERE tool_id = ?",
                        values + [datetime.utcnow().isoformat(), tool_id]
                    )
                stats["updated_tools"] += 1
                print(f"  ✓ Updated {tool_id}: {updates}")

        except Exception as e:
            print(f"  ✗ Error processing {row.get('tool_id', 'unknown')}: {e}")
            stats["errors"] += 1

    if not dry_run:
        conn.commit()
    conn.close()

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Migrate tool registry for Runtime Profile support"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        help="Path to tool_registry database (default: ./data/tool_registry.db)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report changes without applying them"
    )

    args = parser.parse_args()

    db_path = get_db_path(args.db_path)

    if not Path(db_path).exists():
        print(f"Error: Database not found at {db_path}")
        sys.exit(1)

    print(f"Migrating tool registry: {db_path}")
    if args.dry_run:
        print("DRY RUN MODE - No changes will be applied")
    print()

    stats = migrate_tool_registry(db_path, dry_run=args.dry_run)

    print()
    print("Migration Summary:")
    print(f"  Total tools: {stats['total_tools']}")
    print(f"  Updated tools: {stats['updated_tools']}")
    print(f"  Added capability_code: {stats['added_capability_code']}")
    print(f"  Added/mapped risk_class: {stats['added_risk_class'] + stats['mapped_risk_class']}")
    print(f"  Errors: {stats['errors']}")

    if args.dry_run:
        print()
        print("This was a dry run. Use without --dry-run to apply changes.")


if __name__ == "__main__":
    main()

