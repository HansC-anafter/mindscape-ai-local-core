"""Repair a populated live DB whose alembic_version table is empty.

This stamps current Alembic heads only when the database already looks populated,
so future startup runs stop trying to replay the full migration chain from base.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text


HEAD_SENTINEL_TABLES = {
    "20260321083000": "tasks",
    "001_create_direction_tables": "direction_sessions",
    "20260322000001": "direction_sessions",
    "20251227170000": "sonic_segments",
    "20260114000002": "mindscape_personal",
    "20260118000000": "ws_connections",
    "20260221220000": "yogacoach_courses",
    "20260228080000": "tasks",
    "20260310183000": "meta_meeting_sessions",
    "20260311000000": "ig_generated_personas",
    "20260319000000": "expert_profiles",
    "20260325093000": "memory_items",
    "20260327235959": "character_packages",
    "pc_001_initial": "pc_sessions",
    "20260528120000": "runner_queue_capacity_snapshots",
    "20260715023000": "task_summary_projection",
    "20260622193000": "host_resource_allocation_blueprints",
    "20260716020000": "pack_install_commit_receipts",
    "20260726110000": "durable_workflow_release_policies",
    "20260727120000": "host_runtime_bindings",
    "20260728020000": "durable_workflow_events",
    "20260729120000": "access_principals",
    "20260802100000": "meeting_commands",
}


def _backend_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def _get_db_url() -> str:
    db_url = os.environ.get("DATABASE_URL_CORE") or os.environ.get("DATABASE_URL")
    if not db_url:
        raise RuntimeError("DATABASE_URL_CORE or DATABASE_URL is required")
    return db_url


def _build_alembic_config() -> Config:
    backend_dir = _backend_dir()
    config = Config(str(backend_dir / "alembic.postgres.ini"))

    common_versions = backend_dir / "alembic_migrations" / "versions"
    postgres_versions = backend_dir / "alembic_migrations" / "postgres" / "versions"
    version_locations = [str(common_versions), str(postgres_versions)]

    config.set_main_option("version_locations", os.pathsep.join(version_locations))
    config.set_main_option("sqlalchemy.url", _get_db_url())
    return config


def _fetch_current_versions(conn) -> list[str]:
    rows = conn.execute(
        text("SELECT version_num FROM alembic_version ORDER BY version_num")
    ).fetchall()
    return [str(row[0]) for row in rows]


def _fetch_public_tables(conn) -> set[str]:
    rows = conn.execute(
        text(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            ORDER BY tablename
            """
        )
    ).fetchall()
    return {str(row[0]) for row in rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Stamp current heads into alembic_version after validation.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow stamping even if sentinel table checks are incomplete.",
    )
    args = parser.parse_args()

    config = _build_alembic_config()
    backend_dir = _backend_dir()
    script = ScriptDirectory.from_config(config)
    expected_heads = sorted(script.get_heads())

    engine = create_engine(_get_db_url())
    with engine.begin() as conn:
        current_versions = _fetch_current_versions(conn)
        public_tables = _fetch_public_tables(conn)

    missing_sentinels = {
        head: table
        for head, table in HEAD_SENTINEL_TABLES.items()
        if head in expected_heads and table not in public_tables
    }
    unmapped_heads = [
        head for head in expected_heads if head not in HEAD_SENTINEL_TABLES
    ]

    print("ALEMBIC_REPAIR_EXPECTED_HEADS", expected_heads)
    print("ALEMBIC_REPAIR_CURRENT_VERSIONS", current_versions)
    print("ALEMBIC_REPAIR_PUBLIC_TABLE_COUNT", len(public_tables))
    if missing_sentinels:
        print("ALEMBIC_REPAIR_MISSING_SENTINELS", missing_sentinels)

    if current_versions:
        print("ALEMBIC_REPAIR_NOOP_ALREADY_STAMPED")
        return

    if len(public_tables - {"alembic_version"}) == 0:
        raise SystemExit(
            "Refusing to stamp an empty database. Run Alembic upgrade instead."
        )

    if (missing_sentinels or unmapped_heads) and not args.force:
        if unmapped_heads:
            print("ALEMBIC_REPAIR_UNMAPPED_HEADS", unmapped_heads)
        raise SystemExit(
            "Refusing to stamp because migration sentinel contract is incomplete. "
            "Use --force to override."
        )

    if not args.apply:
        print("ALEMBIC_REPAIR_DRY_RUN_OK")
        return

    old_cwd = os.getcwd()
    os.chdir(str(backend_dir))
    try:
        command.stamp(config, "heads")
    finally:
        os.chdir(old_cwd)

    with engine.begin() as conn:
        current_versions = _fetch_current_versions(conn)
    print("ALEMBIC_REPAIR_STAMPED_VERSIONS", current_versions)


if __name__ == "__main__":
    main()
