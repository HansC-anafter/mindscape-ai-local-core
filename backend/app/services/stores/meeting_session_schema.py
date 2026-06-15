"""Schema constants for meeting session persistence."""

TABLE_DDL = """
CREATE TABLE IF NOT EXISTS meeting_sessions (
    id               TEXT PRIMARY KEY,
    workspace_id     TEXT NOT NULL,
    project_id       TEXT,
    thread_id        TEXT,
    lens_id          TEXT,
    started_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at         TIMESTAMPTZ,
    status           TEXT NOT NULL DEFAULT 'planned',
    meeting_type     TEXT NOT NULL DEFAULT 'general',
    agenda           JSONB DEFAULT '[]',
    success_criteria JSONB DEFAULT '[]',
    round_count      INTEGER DEFAULT 0,
    max_rounds       INTEGER DEFAULT 5,
    action_items     JSONB DEFAULT '[]',
    minutes_md       TEXT DEFAULT '',
    state_before     JSONB DEFAULT '{}',
    state_after      JSONB DEFAULT '{}',
    decisions        JSONB DEFAULT '[]',
    traces           JSONB DEFAULT '[]',
    intents_patched  JSONB DEFAULT '[]',
    metadata         JSONB DEFAULT '{}'
);
"""

DECISIONS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS meeting_decisions (
    id                  TEXT PRIMARY KEY,
    session_id          TEXT NOT NULL,
    workspace_id        TEXT NOT NULL,
    category            VARCHAR(32) NOT NULL DEFAULT 'action',
    content             TEXT NOT NULL,
    status              VARCHAR(32) DEFAULT 'pending',
    resolved_by_task_id TEXT,
    source_action_item  JSONB DEFAULT '{}',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);
"""

MEETING_SESSION_ALTER_DDL = [
    "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS project_id TEXT",
    "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS lens_id TEXT",
    "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'planned'",
    "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS meeting_type TEXT NOT NULL DEFAULT 'general'",
    "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS agenda JSONB DEFAULT '[]'::jsonb",
    "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS success_criteria JSONB DEFAULT '[]'::jsonb",
    "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS round_count INTEGER DEFAULT 0",
    "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS max_rounds INTEGER DEFAULT 5",
    "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS action_items JSONB DEFAULT '[]'::jsonb",
    "ALTER TABLE meeting_sessions ADD COLUMN IF NOT EXISTS minutes_md TEXT DEFAULT ''",
]

DECISIONS_INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_decisions_session ON meeting_decisions(session_id)",
    "CREATE INDEX IF NOT EXISTS idx_decisions_ws_status ON meeting_decisions(workspace_id, status)",
]

INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_meeting_sessions_ws_thread ON meeting_sessions(workspace_id, thread_id)",
    "CREATE INDEX IF NOT EXISTS idx_meeting_sessions_ws_project ON meeting_sessions(workspace_id, project_id)",
    "CREATE INDEX IF NOT EXISTS idx_meeting_sessions_active ON meeting_sessions(workspace_id, ended_at)",
]
