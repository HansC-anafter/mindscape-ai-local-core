"""
Mindscape data store service
Handles local data persistence for profiles, intents, and executions

This is a Facade that delegates to domain-specific stores.

NOTE: As of 2026-01-27, this service uses PostgreSQL exclusively.
SQLite support has been deprecated and removed.
"""

import os
import json
import time
import uuid
from datetime import datetime, timezone

from backend.app.services.mindscape_store_utils import _utc_now

from typing import List, Optional, Dict, Any
from contextlib import contextmanager
import logging

from sqlalchemy import text

from backend.app.database.connection_factory import ConnectionFactory
from backend.app.models.mindscape import (
    MindscapeProfile,
    IntentCard,
    AgentExecution,
    IntentStatus,
    PriorityLevel,
    MindEvent,
    EventType,
    EventActor,
    IntentLog,
    Entity,
    EntityType,
    Tag,
    TagCategory,
    EntityTag,
)
from backend.app.models.workspace import Workspace

# Import domain stores
from backend.app.services.stores.profiles_store import ProfilesStore
from backend.app.services.stores.intents_store import IntentsStore
from backend.app.services.stores.agent_executions_store import AgentExecutionsStore
from backend.app.services.stores.events_store import EventsStore
from backend.app.services.stores.intent_logs_store import IntentLogsStore
from backend.app.services.stores.entities_store import EntitiesStore
from backend.app.services.stores.workspaces_store import WorkspacesStore
from backend.app.services.stores.artifacts_store import ArtifactsStore
from backend.app.services.stores.mind_lens_store import MindLensStore
from backend.app.services.stores.lens_composition_store import LensCompositionStore
from backend.app.services.stores.commands_store import CommandsStore
from backend.app.services.stores.surface_events_store import SurfaceEventsStore
from backend.app.services.stores.user_playbook_meta_store import UserPlaybookMetaStore
from backend.app.services.stores.conversation_threads_store import (
    ConversationThreadsStore,
)
from backend.app.services.stores.thread_references_store import ThreadReferencesStore
from backend.app.services.stores.playbook_executions_store import (
    PlaybookExecutionsStore,
)
from backend.app.services.stores.postgres.mind_lens_store import PostgresMindLensStore
from backend.app.services.stores.postgres.artifacts_store import PostgresArtifactsStore
from backend.app.services.stores.postgres.profiles_store import PostgresProfilesStore
from backend.app.services.stores.postgres.workspaces_store import (
    PostgresWorkspacesStore,
)
from backend.app.services.stores.postgres.projects_store import PostgresProjectsStore
from backend.app.services.stores.postgres.events_store import PostgresEventsStore
from backend.app.services.stores.postgres.agent_executions_store import (
    PostgresAgentExecutionsStore,
)
from backend.app.services.stores.postgres.intents_store import PostgresIntentsStore
from backend.app.services.stores.postgres.remaining_stores import (
    PostgresCommandsStore,
    PostgresConversationThreadsStore,
    PostgresPlaybookExecutionsStore,
    PostgresLensCompositionStore,
    PostgresSurfaceEventsStore,
    PostgresUserPlaybookMetaStore,
    PostgresThreadReferencesStore,
)
from backend.app.services.stores.postgres.intent_logs_store import (
    PostgresIntentLogsStore,
)
from backend.app.services.stores.postgres.entities_store import PostgresEntitiesStore
from backend.app.services.stores.projects_store import ProjectsStore

logger = logging.getLogger(__name__)

from backend.app.services.mindscape_store_profile_methods import MindscapeStoreProfileMixin
from backend.app.services.mindscape_store_intent_methods import MindscapeStoreIntentMixin
from backend.app.services.mindscape_store_execution_methods import MindscapeStoreAgentExecutionMixin
from backend.app.services.mindscape_store_event_methods import MindscapeStoreEventMixin
from backend.app.services.mindscape_store_intent_log_methods import MindscapeStoreIntentLogMixin
from backend.app.services.mindscape_store_entity_tag_methods import MindscapeStoreEntityTagMixin
from backend.app.services.mindscape_store_workspace_project_methods import (
    MindscapeStoreWorkspaceProjectMixin,
)

class MindscapeStore(
    MindscapeStoreProfileMixin,
    MindscapeStoreIntentMixin,
    MindscapeStoreAgentExecutionMixin,
    MindscapeStoreEventMixin,
    MindscapeStoreIntentLogMixin,
    MindscapeStoreEntityTagMixin,
    MindscapeStoreWorkspaceProjectMixin,
):
    """
    Facade for all domain stores

    This class provides a unified interface to all domain-specific stores
    while maintaining backward compatibility with existing code.

    Uses singleton pattern to avoid redundant initialization (50+ call sites).
    """

    _schema_initialized = False
    _instance = None

    def __new__(cls, db_path: str = None):
        if cls._instance is not None:
            return cls._instance
        cls._instance = super().__new__(cls)
        cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str = None):
        if self._initialized:
            return
        if db_path is None:
            if os.path.exists("/.dockerenv") or os.environ.get("PYTHONPATH") == "/app":
                db_path = "/app/data/mindscape.db"
            else:
                base_dir = os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                )
                data_dir = os.path.join(base_dir, "data")
                os.makedirs(data_dir, exist_ok=True)
                db_path = os.path.join(data_dir, "mindscape.db")

        self.db_path = db_path
        self.connection_factory = ConnectionFactory()

        # Initialize all domain stores
        self.agent_executions = AgentExecutionsStore(db_path)
        self.events = EventsStore(db_path)
        self.intent_logs = IntentLogsStore(db_path)
        self.entities = EntitiesStore(db_path)

        # Hybrid Migration: Group C (Core Identity) & Group A (Lens & Artifacts)
        # If we are in Postgres mode, use the new Postgres implementations for these specific stores.
        # Other stores remain on legacy SQLite for now.
        if self.connection_factory.get_db_type() == "postgres":
            logger.info("Initializing Stores with Postgres adapters where available")
            self.profiles = PostgresProfilesStore(db_path)
            self.workspaces = PostgresWorkspacesStore()
            self.projects = PostgresProjectsStore()
            self.events = PostgresEventsStore()
            self.agent_executions = PostgresAgentExecutionsStore()
            self.intents = PostgresIntentsStore()
            self.artifacts = PostgresArtifactsStore()
            self.mind_lens = PostgresMindLensStore()
            self.lens_compositions = PostgresLensCompositionStore()
            self.commands = PostgresCommandsStore()
            self.surface_events = PostgresSurfaceEventsStore()
            self.user_playbook_meta = PostgresUserPlaybookMetaStore()
            self.conversation_threads = PostgresConversationThreadsStore()
            self.thread_references = PostgresThreadReferencesStore()
            self.playbook_executions = PostgresPlaybookExecutionsStore()
            self.intent_logs = PostgresIntentLogsStore()
            self.entities = PostgresEntitiesStore()
        else:
            raise RuntimeError(
                "SQLite is no longer supported for new deployments. Please configure PostgreSQL."
            )

        # Initialize database schema
        # Note: Database migrations are managed by Alembic (run: alembic upgrade head)
        # _init_db validates tables exist but must not crash, because this
        # constructor runs at module-import time (before startup_event can
        # execute migrations).  Migrations are applied by MigrationOrchestrator
        # in startup_event; _init_db only logs a warning here.
        self._init_db()
        try:
            self.ensure_default_profile()
        except Exception as e:
            # Tables may not exist yet during first startup; startup_event
            # will run migrations then re-initialize.
            logger.warning(
                "ensure_default_profile deferred (tables may not exist yet): %s", e
            )
            
        self._initialized = True

    def get_user_meta(
        self, profile_id: str, playbook_code: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get user meta for a playbook (delegates to UserPlaybookMetaStore)

        Args:
            profile_id: User profile ID
            playbook_code: Playbook code

        Returns:
            User meta dict or None if not found
        """
        return self.user_playbook_meta.get_user_meta(profile_id, playbook_code)

    def update_user_meta(
        self, profile_id: str, playbook_code: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update user meta for a playbook (delegates to UserPlaybookMetaStore)

        Args:
            profile_id: User profile ID
            playbook_code: Playbook code
            updates: Dict with fields to update

        Returns:
            Updated user meta dict
        """
        return self.user_playbook_meta.update_user_meta(
            profile_id, playbook_code, updates
        )

    @contextmanager
    def get_connection(self):
        """Get database connection with proper cleanup"""
        # Use ConnectionFactory to support both SQLite and Postgres
        conn = self.connection_factory.get_connection()
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database tables with retry logic for startup resilience.

        PostgreSQL may still be performing WAL recovery after an unclean shutdown.
        We retry with exponential backoff to avoid crashing the entire backend
        during the brief window where postgres rejects connections.
        """
        # Skip if already initialized in this process
        if MindscapeStore._schema_initialized:
            return
        if self.connection_factory.get_db_type() != "postgres":
            raise RuntimeError(
                "SQLite is no longer supported for core storage. Configure PostgreSQL."
            )

        required_tables = {
            "alembic_version",
            "profiles",
            "workspaces",
            "projects",
            "commands",
            "playbook_executions",
        }

        max_retries = 5
        base_delay = 1  # seconds
        last_exc = None

        for attempt in range(1, max_retries + 1):
            try:
                with self.connection_factory.get_connection() as conn:
                    result = conn.execute(
                        text(
                            "SELECT table_name FROM information_schema.tables "
                            "WHERE table_schema = 'public'"
                        )
                    )
                    existing_tables = {row[0] for row in result.fetchall()}
                # Connection succeeded, break out of retry loop
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries:
                    delay = base_delay * (2 ** (attempt - 1))  # 1, 2, 4, 8, 16
                    logger.warning(
                        "PostgreSQL not ready (attempt %d/%d): %s. "
                        "Retrying in %ds...",
                        attempt,
                        max_retries,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "PostgreSQL schema validation failed after %d attempts: %s",
                        max_retries,
                        exc,
                    )
                    raise

        if last_exc is not None:
            raise last_exc

        missing_tables = sorted(required_tables - existing_tables)
        if missing_tables:
            missing_str = ", ".join(missing_tables)
            logger.warning(
                "Missing PostgreSQL tables: %s. "
                "They will be created by the migration orchestrator in startup_event. "
                "If this persists, run: alembic -c backend/alembic.ini upgrade head",
                missing_str,
            )
            return

        MindscapeStore._schema_initialized = True

    def _migrate_db(self):
        """
        Database migrations are now managed by Alembic.

        Run migrations using: alembic upgrade head
        """
        # Migrations are handled by Alembic, not here
        pass

    def ensure_default_profile(self):
        """Ensure default-user profile exists for local development"""
        profile = self.get_profile("default-user")
        if not profile:
            from backend.app.models.mindscape import UserPreferences

            logger.info("Creating default-user profile...")
            # Create UserPreferences as dict for Pydantic validation
            # Pydantic v2 requires dict or properly validated instance
            default_profile = MindscapeProfile(
                id="default-user",
                name="Default User",
                email=None,
                roles=[],
                domains=[],
                preferences={
                    "preferred_ui_language": "zh-TW",
                    "preferred_content_language": "zh-TW",
                    "timezone": "Asia/Taipei",
                },
                onboarding_state=None,
                self_description=None,
                created_at=_utc_now(),
                updated_at=_utc_now(),
                version=1,
            )
            self.create_profile(default_profile)
            logger.info("Default profile created successfully")
