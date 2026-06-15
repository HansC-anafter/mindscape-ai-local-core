"""Create run harness episode ledger tables.

Revision ID: 20260614230000
Revises: 20260614015500
Create Date: 2026-06-14 23:00:00.000000
"""

from alembic import op


revision = "20260614230000"
down_revision = "20260614015500"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS run_harness_episodes (
            episode_id              TEXT PRIMARY KEY,
            run_id                  TEXT NOT NULL,
            intent_envelope_ref     TEXT NOT NULL,
            selection_ref           TEXT NOT NULL,
            harness_kind            TEXT NOT NULL,
            status                  TEXT NOT NULL,
            workspace_id            TEXT NOT NULL,
            project_id              TEXT,
            profile_id              TEXT,
            source_execution_id     TEXT,
            selection_snapshot      JSONB NOT NULL DEFAULT '{}'::jsonb,
            capability_snapshot_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            terminal_at             TIMESTAMPTZ
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS run_harness_episode_events (
            event_id                TEXT PRIMARY KEY,
            episode_id              TEXT NOT NULL REFERENCES run_harness_episodes(episode_id) ON DELETE CASCADE,
            run_id                  TEXT NOT NULL,
            attempt_id              TEXT,
            attempt_number          INTEGER,
            sequence_no             INTEGER NOT NULL,
            event_type              TEXT NOT NULL,
            status                  TEXT NOT NULL,
            payload_ref             TEXT,
            policy_eval             JSONB NOT NULL DEFAULT '{}'::jsonb,
            trace_refs              JSONB NOT NULL DEFAULT '[]'::jsonb,
            artifact_lineage        JSONB NOT NULL DEFAULT '[]'::jsonb,
            metadata                JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_run_harness_episode_events_sequence UNIQUE (episode_id, sequence_no),
            CONSTRAINT uq_run_harness_episode_events_episode_event UNIQUE (episode_id, event_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS run_harness_episode_results (
            episode_id              TEXT PRIMARY KEY REFERENCES run_harness_episodes(episode_id) ON DELETE CASCADE,
            run_id                  TEXT NOT NULL,
            harness_kind            TEXT NOT NULL,
            status                  TEXT NOT NULL,
            failure_code            TEXT,
            failure_message         TEXT,
            failure_details         JSONB NOT NULL DEFAULT '{}'::jsonb,
            wait_state              JSONB,
            score                   JSONB,
            next_action             JSONB,
            trace_refs              JSONB NOT NULL DEFAULT '[]'::jsonb,
            output_artifact_refs    JSONB NOT NULL DEFAULT '[]'::jsonb,
            result_metadata         JSONB NOT NULL DEFAULT '{}'::jsonb,
            updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_run_harness_episodes_run_id
        ON run_harness_episodes(run_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_run_harness_episodes_workspace_created
        ON run_harness_episodes(workspace_id, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_run_harness_episode_events_sequence
        ON run_harness_episode_events(episode_id, sequence_no)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_run_harness_episode_results_status_updated
        ON run_harness_episode_results(status, updated_at DESC)
        """
    )


def downgrade():
    op.execute(
        "DROP INDEX IF EXISTS idx_run_harness_episode_results_status_updated"
    )
    op.execute("DROP INDEX IF EXISTS idx_run_harness_episode_events_sequence")
    op.execute("DROP INDEX IF EXISTS idx_run_harness_episodes_workspace_created")
    op.execute("DROP INDEX IF EXISTS idx_run_harness_episodes_run_id")
    op.execute("DROP TABLE IF EXISTS run_harness_episode_results")
    op.execute("DROP TABLE IF EXISTS run_harness_episode_events")
    op.execute("DROP TABLE IF EXISTS run_harness_episodes")
