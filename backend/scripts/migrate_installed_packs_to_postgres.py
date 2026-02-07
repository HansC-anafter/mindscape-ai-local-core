#!/usr/bin/env python3
"""
Migrate installed_packs data from SQLite to PostgreSQL

This script reads installed packs from the SQLite database and
inserts them into the PostgreSQL database.

Usage:
    python scripts/migrate_installed_packs_to_postgres.py

Requirements:
    - SQLite database at data/mindscape.db
    - PostgreSQL database configured via DATABASE_URL_CORE
"""

import os
import sys
import json
import sqlite3
from datetime import datetime
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv

load_dotenv()


def get_sqlite_packs(sqlite_path: str) -> list:
    """Read installed_packs from SQLite database"""
    conn = sqlite3.connect(sqlite_path)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT pack_id, installed_at, enabled, metadata FROM installed_packs"
    )
    rows = cursor.fetchall()

    packs = []
    for row in rows:
        packs.append(
            {
                "pack_id": row[0],
                "installed_at": row[1],
                "enabled": bool(row[2]),
                "metadata": row[3],
            }
        )

    conn.close()
    return packs


def migrate_to_postgres(packs: list):
    """Insert packs into PostgreSQL database"""
    from app.services.stores.installed_packs_store import InstalledPacksStore

    store = InstalledPacksStore()

    migrated = 0
    skipped = 0

    for pack in packs:
        pack_id = pack["pack_id"]

        # Check if already exists
        existing = store.get_pack(pack_id)
        if existing:
            print(f"  [SKIP] {pack_id} - already exists in PostgreSQL")
            skipped += 1
            continue

        # Parse installed_at
        installed_at = pack["installed_at"]
        if isinstance(installed_at, str):
            try:
                installed_at = datetime.fromisoformat(installed_at)
            except ValueError:
                installed_at = datetime.utcnow()

        # Parse metadata
        metadata = pack["metadata"]
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except json.JSONDecodeError:
                metadata = {}

        # Insert into PostgreSQL
        store.upsert_pack(
            pack_id=pack_id,
            installed_at=installed_at,
            enabled=pack["enabled"],
            metadata=metadata,
        )
        print(f"  [OK] {pack_id}")
        migrated += 1

    return migrated, skipped


def main():
    print("=" * 60)
    print("Migrate installed_packs: SQLite -> PostgreSQL")
    print("=" * 60)

    # Find SQLite database
    sqlite_paths = [
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
    print(f"Target: PostgreSQL (via DATABASE_URL_CORE)")

    # Read from SQLite
    print(f"\n[1/2] Reading from SQLite...")
    packs = get_sqlite_packs(str(sqlite_path))
    print(f"  Found {len(packs)} packs")

    # Migrate to PostgreSQL
    print(f"\n[2/2] Migrating to PostgreSQL...")
    migrated, skipped = migrate_to_postgres(packs)

    print(f"\n" + "=" * 60)
    print(f"Migration complete!")
    print(f"  Migrated: {migrated}")
    print(f"  Skipped:  {skipped}")
    print("=" * 60)


if __name__ == "__main__":
    main()
