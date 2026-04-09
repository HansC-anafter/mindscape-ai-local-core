#!/usr/bin/env python3
"""
One-time schema backfill for the local PD scene-package chain.

Use this only when the runtime DB is behind the repo code and the global
Alembic head set is blocked by unrelated branch overlap.
"""

from __future__ import annotations

import json
import os

from sqlalchemy import create_engine, text


DDL_STATEMENTS = [
    "ALTER TYPE direction_artifact_type ADD VALUE IF NOT EXISTS 'scene_package'",
    "ALTER TABLE direction_artifacts ADD COLUMN IF NOT EXISTS package_id VARCHAR(64)",
    "ALTER TABLE direction_artifacts ADD COLUMN IF NOT EXISTS scene_scope VARCHAR(64)",
    "ALTER TABLE direction_artifacts ADD COLUMN IF NOT EXISTS variant_id VARCHAR(64)",
    "ALTER TABLE direction_artifacts ADD COLUMN IF NOT EXISTS provider_code VARCHAR(64)",
    "ALTER TABLE direction_artifacts ADD COLUMN IF NOT EXISTS artifact_state VARCHAR(32)",
    "ALTER TABLE direction_artifacts ADD COLUMN IF NOT EXISTS generation_mode VARCHAR(32)",
    "ALTER TABLE direction_artifacts ADD COLUMN IF NOT EXISTS supersedes_artifact_id VARCHAR(64)",
    (
        "CREATE INDEX IF NOT EXISTS "
        "ix_direction_artifacts_session_artifact_scope_variant_state "
        "ON direction_artifacts "
        "(session_id, artifact_type, scene_scope, variant_id, artifact_state)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS "
        "ix_direction_artifacts_session_artifact_package "
        "ON direction_artifacts (session_id, artifact_type, package_id)"
    ),
    """
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1 FROM pg_type WHERE typname = 'scene_generation_job_status'
      ) THEN
        CREATE TYPE scene_generation_job_status AS ENUM (
          'queued',
          'uploading',
          'submitted',
          'polling',
          'completed',
          'failed',
          'cancelled'
        );
      END IF;
    END
    $$;
    """,
    """
    CREATE TABLE IF NOT EXISTS scene_generation_jobs (
      job_id VARCHAR(64) PRIMARY KEY,
      session_id VARCHAR(64) NOT NULL
        REFERENCES direction_sessions(session_id) ON DELETE CASCADE,
      provider_code VARCHAR(64),
      generation_mode VARCHAR(32) NOT NULL,
      status scene_generation_job_status NOT NULL DEFAULT 'queued',
      scene_scope VARCHAR(64),
      variant_id VARCHAR(64),
      capture_bundle_id VARCHAR(64),
      workspace_artifact_id VARCHAR(64),
      provider_operation_id VARCHAR(128),
      result_artifact_id VARCHAR(64),
      retry_count INTEGER NOT NULL DEFAULT 0,
      last_error TEXT,
      input_payload JSONB,
      temp_asset_refs JSONB,
      created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
      started_at TIMESTAMPTZ,
      completed_at TIMESTAMPTZ
    )
    """,
    (
        "CREATE INDEX IF NOT EXISTS ix_scene_generation_jobs_session_status "
        "ON scene_generation_jobs (session_id, status)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_scene_generation_jobs_provider_operation "
        "ON scene_generation_jobs (provider_code, provider_operation_id)"
    ),
    (
        "ALTER TABLE scene_generation_jobs "
        "ADD COLUMN IF NOT EXISTS last_attempted_at TIMESTAMPTZ"
    ),
    (
        "ALTER TABLE scene_generation_jobs "
        "ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_scene_generation_jobs_last_attempted_at "
        "ON scene_generation_jobs (last_attempted_at)"
    ),
    (
        "CREATE INDEX IF NOT EXISTS ix_scene_generation_jobs_next_attempt_at "
        "ON scene_generation_jobs (next_attempt_at)"
    ),
]


def main() -> int:
    database_url = os.environ["DATABASE_URL"]
    engine = create_engine(database_url)
    with engine.begin() as conn:
        for statement in DDL_STATEMENTS:
            conn.execute(text(statement))
        conn.execute(
            text(
                "UPDATE alembic_version "
                "SET version_num = '20260330000003' "
                "WHERE version_num = '20260322000001'"
            )
        )
        conn.execute(
            text(
                "INSERT INTO alembic_version (version_num) "
                "SELECT '20260330000003' "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM alembic_version "
                "  WHERE version_num = '20260330000003'"
                ")"
            )
        )
        selector_columns = conn.execute(
            text(
                "SELECT column_name "
                "FROM information_schema.columns "
                "WHERE table_name = 'direction_artifacts' "
                "  AND column_name IN ("
                "    'package_id',"
                "    'scene_scope',"
                "    'variant_id',"
                "    'provider_code',"
                "    'artifact_state',"
                "    'generation_mode',"
                "    'supersedes_artifact_id'"
                "  ) "
                "ORDER BY column_name"
            )
        ).fetchall()
        job_columns = conn.execute(
            text(
                "SELECT column_name "
                "FROM information_schema.columns "
                "WHERE table_name = 'scene_generation_jobs' "
                "ORDER BY ordinal_position"
            )
        ).fetchall()
        versions = conn.execute(
            text("SELECT version_num FROM alembic_version ORDER BY version_num")
        ).fetchall()

    print(
        json.dumps(
            {
                "direction_artifact_selector_columns": [row[0] for row in selector_columns],
                "scene_generation_jobs_columns": [row[0] for row in job_columns],
                "alembic_versions": [row[0] for row in versions],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
