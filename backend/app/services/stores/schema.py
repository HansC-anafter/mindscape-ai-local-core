"""
Database schema definitions for Mindscape stores
Contains all table creation and index definitions organized by domain
"""

import sqlite3
import logging
import json

logger = logging.getLogger(__name__)


def _apply_migrations(cursor):
    """
    Apply database migrations idempotently.

    This function is called during schema initialization to ensure
    all required columns and tables exist. All migrations must be
    idempotent (safe to run multiple times).

    Migration order:
    1. workspace_type and storyline_tags columns (Brand OS v0)
    """
    logger.info("Applying database migrations...")

    try:
        cursor.execute("ALTER TABLE workspaces ADD COLUMN workspace_type TEXT DEFAULT 'personal'")
        logger.info("Migration: Added workspace_type column to workspaces table")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
            logger.debug("workspace_type column already exists, skipping")
        else:
            raise

    try:
        cursor.execute("ALTER TABLE intents ADD COLUMN storyline_tags TEXT")
        logger.info("Migration: Added storyline_tags column to intents table")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
            logger.debug("storyline_tags column already exists in intents table, skipping")
        else:
            raise

    # Check if tasks table exists before trying to alter it
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
    if cursor.fetchone():
        try:
            cursor.execute("ALTER TABLE tasks ADD COLUMN storyline_tags TEXT")
            logger.info("Migration: Added storyline_tags column to tasks table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                logger.debug("storyline_tags column already exists in tasks table, skipping")
            else:
                raise
    else:
        logger.debug("tasks table does not exist yet, skipping storyline_tags migration (will be handled when table is created)")

    # Migration: Add project_id column to tasks table (2025-12-16)
    # Check if tasks table exists before trying to alter it
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
    if cursor.fetchone():
        column_exists = False
        try:
            cursor.execute("ALTER TABLE tasks ADD COLUMN project_id TEXT")
            logger.info("Migration: Added project_id column to tasks table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                logger.debug("project_id column already exists, skipping column creation")
                column_exists = True
            else:
                raise

        # Create index for project_id (always try, idempotent)
        try:
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)")
            logger.info("Migration: Created index on tasks.project_id")
        except sqlite3.OperationalError as e:
            logger.debug(f"Index creation skipped: {e}")

        # Data migration: Extract project_id from execution_context for existing tasks
        # This should run even if column already exists (for data migration)
        try:
            cursor.execute("""
                UPDATE tasks
                SET project_id = json_extract(execution_context, '$.project_id')
                WHERE execution_context IS NOT NULL
                AND json_extract(execution_context, '$.project_id') IS NOT NULL
                AND project_id IS NULL
            """)
            updated_count = cursor.rowcount
            if updated_count > 0:
                logger.info(f"Migration: Updated {updated_count} existing tasks with project_id from execution_context")
            elif column_exists:
                logger.debug("Migration: No tasks to update from execution_context (all already migrated or no project_id in data)")
        except sqlite3.OperationalError as e:
            logger.warning(f"Data migration from execution_context failed: {e}")

        # Also try extracting from params
        try:
            cursor.execute("""
                UPDATE tasks
                SET project_id = json_extract(params, '$.project_id')
                WHERE params IS NOT NULL
                AND json_extract(params, '$.project_id') IS NOT NULL
                AND project_id IS NULL
            """)
            updated_count = cursor.rowcount
            if updated_count > 0:
                logger.info(f"Migration: Updated {updated_count} existing tasks with project_id from params")
            elif column_exists:
                logger.debug("Migration: No tasks to update from params (all already migrated or no project_id in data)")
        except sqlite3.OperationalError as e:
            logger.warning(f"Data migration from params failed: {e}")
    else:
        logger.debug("tasks table does not exist yet, skipping project_id migration (will be handled when table is created)")

    logger.info("Database migrations completed")


def init_profiles_schema(cursor):
    """Initialize profiles table and indexes"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS profiles (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            roles TEXT,
            domains TEXT,
            preferences TEXT,
            onboarding_state TEXT,
            self_description TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            version INTEGER DEFAULT 1
        )
    ''')


def init_intents_schema(cursor):
    """Initialize intents table and indexes"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS intents (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL,
            priority TEXT NOT NULL,
            tags TEXT,
            storyline_tags TEXT,
            category TEXT,
            progress_percentage INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            due_date TEXT,
            parent_intent_id TEXT,
            child_intent_ids TEXT,
            metadata TEXT,
            FOREIGN KEY (profile_id) REFERENCES profiles (id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_intents_profile ON intents(profile_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_intents_status ON intents(status)')

    # storyline_tags column is now added via _apply_migrations()
    # This ensures consistent migration execution


def init_intent_tags_schema(cursor):
    """Initialize intent_tags table and indexes"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS intent_tags (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            label TEXT NOT NULL,
            confidence REAL,
            status TEXT NOT NULL DEFAULT 'candidate',
            source TEXT NOT NULL,
            execution_id TEXT,
            playbook_code TEXT,
            message_id TEXT,
            metadata TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            confirmed_at TEXT,
            rejected_at TEXT,
            FOREIGN KEY (workspace_id) REFERENCES workspaces (id),
            FOREIGN KEY (profile_id) REFERENCES profiles (id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_intent_tags_workspace ON intent_tags(workspace_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_intent_tags_profile ON intent_tags(profile_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_intent_tags_status ON intent_tags(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_intent_tags_execution ON intent_tags(execution_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_intent_tags_workspace_status ON intent_tags(workspace_id, status)')


def init_agent_executions_schema(cursor):
    """Initialize agent_executions table and indexes"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS agent_executions (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            agent_type TEXT NOT NULL,
            task TEXT NOT NULL,
            intent_ids TEXT,
            status TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            duration_seconds REAL,
            output TEXT,
            error_message TEXT,
            used_profile TEXT,
            used_intents TEXT,
            metadata TEXT,
            FOREIGN KEY (profile_id) REFERENCES profiles (id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_agent_executions_profile ON agent_executions(profile_id)')


def init_habit_schema(cursor):
    """Initialize habit-related tables and indexes"""
    # Habit observations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS habit_observations (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            habit_key TEXT NOT NULL,
            habit_value TEXT NOT NULL,
            habit_category TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT,
            source_context TEXT,
            observed_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (profile_id) REFERENCES profiles (id)
        )
    ''')

    # Habit candidates table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS habit_candidates (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            habit_key TEXT NOT NULL,
            habit_value TEXT NOT NULL,
            habit_category TEXT NOT NULL,
            evidence_count INTEGER DEFAULT 0,
            confidence REAL DEFAULT 0.0,
            first_seen_at TEXT,
            last_seen_at TEXT,
            evidence_refs TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (profile_id) REFERENCES profiles (id),
            UNIQUE(profile_id, habit_key, habit_value)
        )
    ''')

    # Habit audit logs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS habit_audit_logs (
            id TEXT PRIMARY KEY,
            profile_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            action TEXT NOT NULL,
            previous_status TEXT,
            new_status TEXT,
            actor_type TEXT DEFAULT 'system',
            actor_id TEXT,
            reason TEXT,
            metadata TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (profile_id) REFERENCES profiles (id),
            FOREIGN KEY (candidate_id) REFERENCES habit_candidates (id)
        )
    ''')

    # Habit indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_habit_observations_profile ON habit_observations(profile_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_habit_observations_key ON habit_observations(habit_key)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_habit_observations_observed_at ON habit_observations(observed_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_habit_candidates_profile ON habit_candidates(profile_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_habit_candidates_status ON habit_candidates(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_habit_candidates_key ON habit_candidates(habit_key)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_habit_audit_logs_profile ON habit_audit_logs(profile_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_habit_audit_logs_candidate ON habit_audit_logs(candidate_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_habit_audit_logs_created_at ON habit_audit_logs(created_at DESC)')


def init_workspaces_schema(cursor):
    """Initialize workspaces table and indexes"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS workspaces (
            id TEXT PRIMARY KEY,
            owner_user_id TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            primary_project_id TEXT,
            default_playbook_id TEXT,
            default_locale TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (owner_user_id) REFERENCES profiles (id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_workspaces_owner ON workspaces(owner_user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_workspaces_project ON workspaces(primary_project_id)')

    # Migration: Add execution mode columns if they don't exist
    # See: docs-internal/architecture/workspace-llm-agent-execution-mode.md
    for column_def in [
        ('execution_mode', "TEXT DEFAULT 'qa'"),
        ('expected_artifacts', 'TEXT'),
        ('execution_priority', "TEXT DEFAULT 'medium'"),
        ('project_assignment_mode', "TEXT DEFAULT 'auto_silent'"),  # Project assignment automation level
        ('metadata', 'TEXT'),  # Extensible metadata for workspace features (core_memory, etc.)
    ]:
        column_name, column_type = column_def
        try:
            cursor.execute(f'ALTER TABLE workspaces ADD COLUMN {column_name} {column_type}')
        except sqlite3.OperationalError:
            pass  # Column already exists

    # Schema changes: Apply migrations idempotently
    # Note: This is the actual migration execution point (not Alembic)
    # All migrations should be idempotent and safe to run multiple times
    # workspace_type is now handled in _apply_migrations()
    _apply_migrations(cursor)


def init_events_schema(cursor):
    """Initialize mind_events table and indexes"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mind_events (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            actor TEXT NOT NULL,
            channel TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            project_id TEXT,
            workspace_id TEXT,
            event_type TEXT NOT NULL,
            payload TEXT NOT NULL,
            entity_ids TEXT,
            metadata TEXT,
            FOREIGN KEY (profile_id) REFERENCES profiles (id),
            FOREIGN KEY (workspace_id) REFERENCES workspaces (id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mind_events_profile ON mind_events(profile_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mind_events_project ON mind_events(project_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mind_events_type ON mind_events(event_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mind_events_timestamp ON mind_events(timestamp DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mind_events_profile_timestamp ON mind_events(profile_id, timestamp DESC)')

    # Check if workspace_id column exists before creating workspace-related indexes
    # This handles existing databases that don't have workspace_id yet (migration will add it)
    cursor.execute("PRAGMA table_info(mind_events)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'workspace_id' in columns:
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_mind_events_workspace ON mind_events(workspace_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_mind_events_workspace_timestamp ON mind_events(workspace_id, timestamp DESC)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_mind_events_workspace_timestamp_id ON mind_events(workspace_id, timestamp DESC, id DESC)')


def init_intent_logs_schema(cursor):
    """Initialize intent_logs table and indexes"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS intent_logs (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            raw_input TEXT NOT NULL,
            channel TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            project_id TEXT,
            workspace_id TEXT,
            pipeline_steps TEXT NOT NULL,
            final_decision TEXT NOT NULL,
            user_override TEXT,
            metadata TEXT,
            FOREIGN KEY (profile_id) REFERENCES profiles (id),
            FOREIGN KEY (workspace_id) REFERENCES workspaces (id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_intent_logs_profile ON intent_logs(profile_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_intent_logs_timestamp ON intent_logs(timestamp DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_intent_logs_profile_timestamp ON intent_logs(profile_id, timestamp DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_intent_logs_has_override ON intent_logs(user_override) WHERE user_override IS NOT NULL')

    # Check if workspace_id column exists before creating workspace-related indexes
    # This handles existing databases that don't have workspace_id yet (migration will add it)
    cursor.execute("PRAGMA table_info(intent_logs)")
    intent_logs_columns = [row[1] for row in cursor.fetchall()]
    if 'workspace_id' in intent_logs_columns:
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_intent_logs_workspace ON intent_logs(workspace_id)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_intent_logs_workspace_timestamp ON intent_logs(workspace_id, timestamp DESC)')


def init_entities_schema(cursor):
    """Initialize entities, tags, and entity_tags tables and indexes"""
    # Entities table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS entities (
            id TEXT PRIMARY KEY,
            entity_type TEXT NOT NULL,
            name TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            description TEXT,
            metadata TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (profile_id) REFERENCES profiles (id)
        )
    ''')

    # Tags table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tags (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            description TEXT,
            color TEXT,
            metadata TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (profile_id) REFERENCES profiles (id)
        )
    ''')

    # Entity-Tag associations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS entity_tags (
            entity_id TEXT NOT NULL,
            tag_id TEXT NOT NULL,
            value TEXT,
            created_at TEXT NOT NULL,
            PRIMARY KEY (entity_id, tag_id),
            FOREIGN KEY (entity_id) REFERENCES entities (id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags (id) ON DELETE CASCADE
        )
    ''')

    # Entities indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_entities_profile ON entities(profile_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_entities_profile_type ON entities(profile_id, entity_type)')

    # Tags indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags_profile ON tags(profile_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags_category ON tags(category)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags_profile_category ON tags(profile_id, category)')

    # Entity-Tag indexes
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_entity_tags_entity ON entity_tags(entity_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_entity_tags_tag ON entity_tags(tag_id)')


def init_tasks_schema(cursor):
    """Initialize tasks table and indexes"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            execution_id TEXT,
            pack_id TEXT NOT NULL,
            task_type TEXT NOT NULL,
            status TEXT NOT NULL,
            params TEXT NOT NULL,
            result TEXT,
            execution_context TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            error TEXT,
            notification_sent_at TEXT,
            displayed_at TEXT,
            FOREIGN KEY (workspace_id) REFERENCES workspaces (id)
        )
    ''')

    # Migration: Add notification_sent_at and displayed_at columns if they don't exist
    try:
        cursor.execute('ALTER TABLE tasks ADD COLUMN notification_sent_at TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    try:
        cursor.execute('ALTER TABLE tasks ADD COLUMN displayed_at TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Migration: Add execution_context column if it doesn't exist
    try:
        cursor.execute('ALTER TABLE tasks ADD COLUMN execution_context TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    # storyline_tags column is now added via _apply_migrations()
    # This ensures consistent migration execution

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_workspace ON tasks(workspace_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_message ON tasks(message_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_workspace_status ON tasks(workspace_id, status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_execution_id ON tasks(execution_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id)')


def init_playbook_executions_schema(cursor):
    """Initialize playbook_executions table and indexes"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS playbook_executions (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            playbook_code TEXT NOT NULL,
            intent_instance_id TEXT,
            status TEXT NOT NULL,
            phase TEXT,
            last_checkpoint TEXT,
            progress_log_path TEXT,
            feature_list_path TEXT,
            metadata TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (workspace_id) REFERENCES workspaces (id)
        )
    ''')

    # Add metadata column if it doesn't exist (migration support)
    try:
        cursor.execute('ALTER TABLE playbook_executions ADD COLUMN metadata TEXT')
    except Exception:
        # Column already exists, ignore
        pass

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_playbook_executions_workspace ON playbook_executions(workspace_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_playbook_executions_status ON playbook_executions(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_playbook_executions_intent ON playbook_executions(intent_instance_id)')


def init_task_feedback_schema(cursor):
    """Initialize task_feedback table and indexes"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS task_feedback (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            reason_code TEXT,
            comment TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks (id),
            FOREIGN KEY (workspace_id) REFERENCES workspaces (id)
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_feedback_task ON task_feedback(task_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_feedback_workspace ON task_feedback(workspace_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_feedback_user ON task_feedback(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_feedback_action ON task_feedback(action)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_feedback_created_at ON task_feedback(created_at DESC)')


def init_task_preference_schema(cursor):
    """Initialize task_preference table and indexes"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS task_preference (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            pack_id TEXT,
            task_type TEXT,
            action TEXT NOT NULL,
            auto_suggest INTEGER NOT NULL DEFAULT 1,
            last_feedback TEXT,
            reject_count_30d INTEGER NOT NULL DEFAULT 0,
            accept_count_30d INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (workspace_id) REFERENCES workspaces (id),
            UNIQUE(workspace_id, user_id, pack_id, task_type)
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_preference_workspace ON task_preference(workspace_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_preference_user ON task_preference(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_preference_pack ON task_preference(pack_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_preference_task_type ON task_preference(task_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_preference_auto_suggest ON task_preference(auto_suggest)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_preference_workspace_user ON task_preference(workspace_id, user_id)')


def init_timeline_items_schema(cursor):
    """Initialize timeline_items table and indexes"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS timeline_items (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            task_id TEXT,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT NOT NULL,
            data TEXT NOT NULL,
            cta TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (workspace_id) REFERENCES workspaces (id),
            FOREIGN KEY (task_id) REFERENCES tasks (id)
        )
    ''')

    # Migration: Make task_id nullable if it was previously NOT NULL
    try:
        # SQLite doesn't support MODIFY COLUMN, so we need to recreate the table
        # Check if task_id is currently NOT NULL by examining pragma
        cursor.execute("PRAGMA table_info(timeline_items)")
        columns = cursor.fetchall()
        task_id_col = next((col for col in columns if col[1] == 'task_id'), None)

        if task_id_col and task_id_col[3] == 1:  # NOT NULL constraint exists
            # Recreate table with nullable task_id
            logger.info("Migrating timeline_items table: making task_id nullable")
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS timeline_items_new (
                    id TEXT PRIMARY KEY,
                    workspace_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    task_id TEXT,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    data TEXT NOT NULL,
                    cta TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (workspace_id) REFERENCES workspaces (id),
                    FOREIGN KEY (task_id) REFERENCES tasks (id)
                )
            ''')
            cursor.execute('INSERT INTO timeline_items_new SELECT * FROM timeline_items')
            cursor.execute('DROP TABLE timeline_items')
            cursor.execute('ALTER TABLE timeline_items_new RENAME TO timeline_items')
    except Exception as e:
        logger.warning(f"Migration for timeline_items.task_id nullable failed (may already be migrated): {e}")
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timeline_items_workspace ON timeline_items(workspace_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timeline_items_message ON timeline_items(message_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timeline_items_task ON timeline_items(task_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timeline_items_type ON timeline_items(type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timeline_items_created_at ON timeline_items(created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timeline_items_workspace_created_at ON timeline_items(workspace_id, created_at DESC)')


def init_artifacts_schema(cursor):
    """Initialize artifacts table and indexes"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS artifacts (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            intent_id TEXT,
            task_id TEXT,
            execution_id TEXT,
            playbook_code TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            title TEXT NOT NULL,
            summary TEXT,
            content TEXT NOT NULL,
            storage_ref TEXT,
            sync_state TEXT,
            primary_action_type TEXT NOT NULL,
            metadata TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (workspace_id) REFERENCES workspaces (id),
            FOREIGN KEY (task_id) REFERENCES tasks (id)
        )
    ''')

    # Migration: Add source_execution_id and source_step_id columns if they don't exist
    try:
        cursor.execute('ALTER TABLE artifacts ADD COLUMN source_execution_id TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    try:
        cursor.execute('ALTER TABLE artifacts ADD COLUMN source_step_id TEXT')
    except sqlite3.OperationalError:
        pass  # Column already exists

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_artifacts_workspace ON artifacts(workspace_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_artifacts_intent ON artifacts(intent_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_artifacts_task ON artifacts(task_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_artifacts_playbook ON artifacts(playbook_code)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_artifacts_created_at ON artifacts(created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_artifacts_workspace_created_at ON artifacts(workspace_id, created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_artifacts_workspace_intent ON artifacts(workspace_id, intent_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_artifacts_execution ON artifacts(source_execution_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_artifacts_step ON artifacts(source_step_id)')


def init_tool_calls_schema(cursor):
    """Initialize tool_calls table and indexes"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tool_calls (
            id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            step_id TEXT,
            tool_name TEXT NOT NULL,
            tool_id TEXT,
            parameters TEXT NOT NULL,
            response TEXT,
            status TEXT NOT NULL,
            error TEXT,
            duration_ms INTEGER,
            factory_cluster TEXT,
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tool_calls_execution ON tool_calls(execution_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tool_calls_step ON tool_calls(step_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tool_calls_tool ON tool_calls(tool_name)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_tool_calls_cluster ON tool_calls(factory_cluster)')


def init_stage_results_schema(cursor):
    """Initialize stage_results table and indexes"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stage_results (
            id TEXT PRIMARY KEY,
            execution_id TEXT NOT NULL,
            step_id TEXT,
            stage_name TEXT NOT NULL,
            result_type TEXT NOT NULL,
            content TEXT NOT NULL,
            preview TEXT,
            requires_review INTEGER NOT NULL DEFAULT 0,
            review_status TEXT,
            artifact_id TEXT,
            created_at TEXT NOT NULL
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_stage_results_execution ON stage_results(execution_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_stage_results_step ON stage_results(step_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_stage_results_review ON stage_results(requires_review, review_status)')


def init_background_routines_schema(cursor):
    """Initialize background_routines table and indexes"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS background_routines (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            playbook_code TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            config TEXT NOT NULL,
            last_run_at TEXT,
            next_run_at TEXT,
            last_status TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
        )
    ''')

    # Migration: Add readiness status fields if they don't exist
    for column_def in [
        ('readiness_status', 'TEXT'),
        ('tool_statuses', 'TEXT'),
        ('error_count', 'INTEGER DEFAULT 0'),
        ('auto_paused', 'INTEGER DEFAULT 0')
    ]:
        column_name, column_type = column_def
        try:
            cursor.execute(f'ALTER TABLE background_routines ADD COLUMN {column_name} {column_type}')
        except sqlite3.OperationalError:
            # Column already exists, ignore
            pass

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_background_routines_workspace ON background_routines(workspace_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_background_routines_playbook ON background_routines(playbook_code)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_background_routines_enabled ON background_routines(enabled)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_stage_results_artifact ON stage_results(artifact_id)')


def init_mind_lens_schema(cursor):
    """Initialize mind_lens_schemas, mind_lens_instances, and lens_specs tables"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mind_lens_schemas (
            schema_id TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            label TEXT,
            dimensions TEXT NOT NULL,
            version TEXT DEFAULT '0.1',
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mind_lens_schemas_role ON mind_lens_schemas(role)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lens_specs (
            lens_id TEXT PRIMARY KEY,
            version TEXT NOT NULL,
            category TEXT NOT NULL,
            applies_to TEXT NOT NULL,
            inject TEXT NOT NULL,
            params_schema TEXT,
            transformers TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_lens_specs_category ON lens_specs(category)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS mind_lens_instances (
            mind_lens_id TEXT PRIMARY KEY,
            schema_id TEXT NOT NULL,
            owner_user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            label TEXT,
            description TEXT,
            "values" TEXT NOT NULL,
            source TEXT,
            version TEXT DEFAULT '0.1',
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mind_lens_instances_owner ON mind_lens_instances(owner_user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mind_lens_instances_role ON mind_lens_instances(role)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_mind_lens_instances_schema ON mind_lens_instances(schema_id)')


def init_lens_composition_schema(cursor):
    """Initialize lens_compositions table"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lens_compositions (
            composition_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            lens_stack TEXT NOT NULL,
            fusion_strategy TEXT DEFAULT 'priority_then_weighted',
            metadata TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_lens_compositions_workspace ON lens_compositions(workspace_id)')


def init_commands_schema(cursor):
    """Initialize commands table"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS commands (
            command_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            actor_id TEXT NOT NULL,
            source_surface TEXT NOT NULL,
            intent_code TEXT NOT NULL,
            parameters TEXT,
            requires_approval INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            execution_id TEXT,
            thread_id TEXT,
            correlation_id TEXT,
            parent_command_id TEXT,
            metadata TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_commands_workspace ON commands(workspace_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_commands_thread ON commands(thread_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_commands_correlation ON commands(correlation_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_commands_status ON commands(status)')


def init_surface_events_schema(cursor):
    """Initialize surface_events table"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS surface_events (
            event_id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            source_surface TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor_id TEXT,
            payload TEXT,
            command_id TEXT,
            thread_id TEXT,
            correlation_id TEXT,
            parent_event_id TEXT,
            execution_id TEXT,
            pack_id TEXT,
            card_id TEXT,
            scope TEXT,
            playbook_version TEXT,
            timestamp TEXT,
            created_at TEXT
        )
    ''')

    # Add BYOP columns if they don't exist (migration support)
    # Must be done BEFORE creating indexes on these columns
    for column in ['pack_id', 'card_id', 'scope', 'playbook_version']:
        try:
            cursor.execute(f'ALTER TABLE surface_events ADD COLUMN {column} TEXT')
        except Exception:
            # Column already exists, ignore
            pass

    # Create indexes AFTER ensuring columns exist
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_surface_events_workspace ON surface_events(workspace_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_surface_events_thread ON surface_events(thread_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_surface_events_correlation ON surface_events(correlation_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_surface_events_command ON surface_events(command_id)')

    # Only create indexes on pack_id and card_id if columns exist
    # Check if pack_id column exists before creating index
    cursor.execute("PRAGMA table_info(surface_events)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'pack_id' in columns:
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_surface_events_pack_id ON surface_events(pack_id)')
    if 'card_id' in columns:
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_surface_events_card_id ON surface_events(card_id)')


def init_project_phases_schema(cursor):
    """Initialize project_phases table and indexes"""
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS project_phases (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            created_by_message_id TEXT NOT NULL,
            execution_plan_id TEXT,
            kind TEXT NOT NULL DEFAULT 'unknown',
            summary TEXT NOT NULL,
            tags TEXT NOT NULL DEFAULT '[]',
            metadata TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (workspace_id) REFERENCES workspaces (id)
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_project_phases_project_created_at ON project_phases(project_id, created_at DESC)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_project_phases_workspace ON project_phases(workspace_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_project_phases_execution_plan ON project_phases(execution_plan_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_project_phases_message ON project_phases(created_by_message_id)')


def init_schema(cursor):
    """
    Initialize all database tables and indexes

    This function should be called in the correct order to respect foreign key dependencies:
    1. Profiles (no dependencies)
    2. Intents, AgentExecutions, Habit tables (depend on Profiles)
    3. Workspaces (depends on Profiles)
    4. Events, IntentLogs (depend on Profiles and Workspaces)
    5. Entities, Tags (depend on Profiles)
    6. Projects and Project Phases (depend on Workspaces)
    """
    # Core tables (no dependencies)
    init_profiles_schema(cursor)

    # Tables that depend on Profiles
    init_intents_schema(cursor)
    init_agent_executions_schema(cursor)
    init_habit_schema(cursor)
    init_workspaces_schema(cursor)

    # Tables that depend on Profiles and Workspaces
    init_intent_tags_schema(cursor)

    # Tables that depend on Profiles and Workspaces
    init_events_schema(cursor)
    init_intent_logs_schema(cursor)

    # Tables that depend on Profiles
    init_entities_schema(cursor)

    # Tables that depend on Workspaces
    init_tasks_schema(cursor)
    init_task_feedback_schema(cursor)
    init_task_preference_schema(cursor)
    init_timeline_items_schema(cursor)
    init_artifacts_schema(cursor)
    init_tool_calls_schema(cursor)
    init_stage_results_schema(cursor)
    init_background_routines_schema(cursor)
    init_playbook_executions_schema(cursor)

    # Project-related tables (depend on Workspaces)
    init_project_phases_schema(cursor)

    # Lens and Composition tables (depend on Workspaces)
    init_mind_lens_schema(cursor)
    init_lens_composition_schema(cursor)
    init_commands_schema(cursor)
    init_surface_events_schema(cursor)
