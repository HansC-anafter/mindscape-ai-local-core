#!/usr/bin/env python3
"""
nomic_embed_cleanup.py
======================
One-shot migration script: remove legacy nomic-embed-text rows from
tool_embeddings table so the index is 100% bge-m3 (or whichever model
the system currently uses).

Run once per environment after upgrading to Phase-2 embedding alignment.

Usage:
    python3 scripts/nomic_embed_cleanup.py [--dry-run] [--model nomic-embed-text]

Environment:
    DATABASE_URL  — PostgreSQL connection string (or falls back to default)
"""

import argparse
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up legacy embedding rows")
    parser.add_argument(
        "--model",
        default="nomic-embed-text",
        help="Embedding model name to remove (default: nomic-embed-text)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print count only, do not delete",
    )
    args = parser.parse_args()

    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://mindscape:mindscape@localhost:5432/mindscape",
    )

    try:
        conn = psycopg2.connect(database_url)
    except Exception as exc:
        print(f"ERROR: Cannot connect to database: {exc}")
        sys.exit(1)

    with conn:
        with conn.cursor() as cur:
            # Count first
            cur.execute(
                "SELECT COUNT(*) FROM tool_embeddings WHERE embedding_model = %s",
                (args.model,),
            )
            count = cur.fetchone()[0]
            print(f"Found {count} rows with embedding_model = '{args.model}'")

            if count == 0:
                print("Nothing to clean up. Exiting.")
                return

            if args.dry_run:
                print("[dry-run] No rows deleted.")
                return

            cur.execute(
                "DELETE FROM tool_embeddings WHERE embedding_model = %s",
                (args.model,),
            )
            deleted = cur.rowcount
            print(f"Deleted {deleted} rows. Done.")

    conn.close()


if __name__ == "__main__":
    main()
