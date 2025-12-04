#!/usr/bin/env python3
"""
Check and fix artifacts table migration

This script checks if the artifacts table exists and creates it if missing.
"""

import sys
import sqlite3
from pathlib import Path

# Add parent directory to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))


def check_artifacts_table(db_path: str) -> bool:
    """Check if artifacts table exists"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='artifacts'
        """)
        result = cursor.fetchone()

        conn.close()
        return result is not None
    except Exception as e:
        print(f"Error checking table: {e}")
        return False


def create_artifacts_table(db_path: str) -> bool:
    """Create artifacts table if it doesn't exist"""
    try:
        from app.services.stores.schema import init_artifacts_schema

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Initialize artifacts schema
        init_artifacts_schema(cursor)
        conn.commit()
        conn.close()

        print("✅ Artifacts table created successfully")
        return True
    except Exception as e:
        print(f"❌ Failed to create artifacts table: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main function"""
    import os

    # Find database path (same logic as MindscapeStore)
    base_dir = Path(__file__).parent.parent
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(data_dir / "mindscape.db")

    print("=" * 80)
    print("Artifacts Table Migration Check")
    print("=" * 80)
    print(f"Database path: {db_path}")

    if not Path(db_path).exists():
        print(f"⚠️  Database file does not exist: {db_path}")
        print("   It will be created when MindscapeStore is initialized")
        return 0

    # Check if table exists
    print(f"\n1. Checking if artifacts table exists...")
    exists = check_artifacts_table(db_path)

    if exists:
        print("   ✅ Artifacts table exists")

        # Check table structure
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(artifacts)")
        columns = cursor.fetchall()
        print(f"\n2. Table structure ({len(columns)} columns):")
        for col in columns:
            print(f"   - {col[1]} ({col[2]})")
        conn.close()

        return 0
    else:
        print("   ❌ Artifacts table does NOT exist")
        print(f"\n2. Creating artifacts table...")

        if create_artifacts_table(db_path):
            # Verify creation
            if check_artifacts_table(db_path):
                print("\n3. ✅ Verification: Table created successfully")
                return 0
            else:
                print("\n3. ❌ Verification failed: Table still missing")
                return 1
        else:
            return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)

