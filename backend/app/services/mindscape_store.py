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
from datetime import datetime


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


from typing import List, Optional, Dict, Any
from contextlib import contextmanager
import logging

from sqlalchemy import text

from app.database.connection_factory import ConnectionFactory
from app.models.mindscape import (
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
from app.models.workspace import Workspace

# Import domain stores
from app.services.stores.profiles_store import ProfilesStore
from app.services.stores.intents_store import IntentsStore
from app.services.stores.agent_executions_store import AgentExecutionsStore
from app.services.stores.events_store import EventsStore
from app.services.stores.intent_logs_store import IntentLogsStore
from app.services.stores.entities_store import EntitiesStore
from app.services.stores.workspaces_store import WorkspacesStore
from app.services.stores.artifacts_store import ArtifactsStore
from app.services.stores.mind_lens_store import MindLensStore
from app.services.stores.lens_composition_store import LensCompositionStore
from app.services.stores.commands_store import CommandsStore
from app.services.stores.surface_events_store import SurfaceEventsStore
from app.services.stores.user_playbook_meta_store import UserPlaybookMetaStore
from app.services.stores.conversation_threads_store import ConversationThreadsStore
from app.services.stores.thread_references_store import ThreadReferencesStore
from app.services.stores.playbook_executions_store import PlaybookExecutionsStore
from app.services.stores.postgres.mind_lens_store import PostgresMindLensStore
from app.services.stores.postgres.artifacts_store import PostgresArtifactsStore
from app.services.stores.postgres.profiles_store import PostgresProfilesStore
from app.services.stores.postgres.workspaces_store import PostgresWorkspacesStore
from app.services.stores.postgres.projects_store import PostgresProjectsStore
from app.services.stores.postgres.events_store import PostgresEventsStore
from app.services.stores.postgres.agent_executions_store import (
    PostgresAgentExecutionsStore,
)
from app.services.stores.postgres.intents_store import PostgresIntentsStore
from app.services.stores.postgres.remaining_stores import (
    PostgresCommandsStore,
    PostgresConversationThreadsStore,
    PostgresPlaybookExecutionsStore,
    PostgresLensCompositionStore,
    PostgresSurfaceEventsStore,
    PostgresUserPlaybookMetaStore,
    PostgresThreadReferencesStore,
)
from app.services.stores.projects_store import ProjectsStore

logger = logging.getLogger(__name__)


class MindscapeStore:
    """
    Facade for all domain stores

    This class provides a unified interface to all domain-specific stores
    while maintaining backward compatibility with existing code.
    """

    _schema_initialized = False

    def __init__(self, db_path: str = None):
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
        else:
            raise RuntimeError(
                "SQLite is no longer supported for new deployments. Please configure PostgreSQL."
            )

        # Initialize database schema
        # Note: Database migrations are managed by Alembic (run: alembic upgrade head)
        self._init_db()
        self.ensure_default_profile()

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
            raise RuntimeError(
                "Missing PostgreSQL tables: "
                f"{missing_str}. Run: alembic -c backend/alembic.ini upgrade head"
            )

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

    # ==================== Profile Methods (Delegated) ====================

    def create_profile(self, profile: MindscapeProfile) -> MindscapeProfile:
        """Create a new profile"""
        return self.profiles.create_profile(profile)

    def get_profile(
        self, profile_id: str, apply_habits: bool = True
    ) -> Optional[MindscapeProfile]:
        """
        Get profile by ID

        Args:
            profile_id: Profile ID
            apply_habits: If True, apply confirmed habits to preferences (default: True)
        """
        return self.profiles.get_profile(profile_id, apply_habits=apply_habits)

    def update_profile(
        self, profile_id: str, updates: Dict[str, Any]
    ) -> Optional[MindscapeProfile]:
        """Update profile"""
        return self.profiles.update_profile(profile_id, updates)

    # ==================== Intent Methods (Delegated) ====================

    def create_intent(self, intent: IntentCard) -> IntentCard:
        """Create a new intent"""
        return self.intents.create_intent(intent)

    def get_intent(self, intent_id: str) -> Optional[IntentCard]:
        """Get intent by ID"""
        return self.intents.get_intent(intent_id)

    def list_intents(
        self,
        profile_id: str,
        status: Optional[IntentStatus] = None,
        priority: Optional[PriorityLevel] = None,
    ) -> List[IntentCard]:
        """List intents for a profile with optional filters"""
        return self.intents.list_intents(profile_id, status=status, priority=priority)

    def update_intent(self, intent: IntentCard) -> Optional[IntentCard]:
        """Update an existing intent"""
        return self.intents.update_intent(intent)

    def delete_intent(self, intent_id: str) -> bool:
        """Delete an intent by ID"""
        return self.intents.delete_intent(intent_id)

    # ==================== Agent Execution Methods (Delegated) ====================

    def create_agent_execution(self, execution: AgentExecution) -> AgentExecution:
        """Create a new agent execution record"""
        return self.agent_executions.create_agent_execution(execution)

    def get_agent_execution(self, execution_id: str) -> Optional[AgentExecution]:
        """Get agent execution by ID"""
        return self.agent_executions.get_agent_execution(execution_id)

    def list_agent_executions(
        self, profile_id: str, limit: int = 50
    ) -> List[AgentExecution]:
        """List recent agent executions for a profile"""
        return self.agent_executions.list_agent_executions(profile_id, limit=limit)

    # ==================== Event Methods (Delegated) ====================

    def create_event(
        self, event: MindEvent, generate_embedding: bool = False
    ) -> MindEvent:
        """
        Create a new mindspace event

        Args:
            event: MindEvent to create
            generate_embedding: Whether to generate embedding for this event

        Returns:
            Created MindEvent
        """
        return self.events.create_event(event, generate_embedding=generate_embedding)

    def get_event(self, event_id: str) -> Optional[MindEvent]:
        """
        Get a single event by ID

        Args:
            event_id: Event ID

        Returns:
            MindEvent or None if not found
        """
        return self.events.get_event(event_id)

    def update_event(
        self,
        event_id: str,
        payload: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Update event payload and/or metadata

        Args:
            event_id: Event ID
            payload: New payload (optional)
            metadata: New metadata (optional)

        Returns:
            True if update succeeded
        """
        return self.events.update_event(event_id, payload=payload, metadata=metadata)

    def get_events(
        self,
        profile_id: str,
        event_type: Optional[EventType] = None,
        project_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[MindEvent]:
        """
        Get events for a profile with optional filters

        Args:
            profile_id: Profile ID
            event_type: Optional event type filter
            project_id: Optional project ID filter
            workspace_id: Optional workspace ID filter
            start_time: Optional start time filter
            end_time: Optional end time filter
            limit: Maximum number of events to return

        Returns:
            List of MindEvent objects, ordered by timestamp DESC
        """
        return self.events.get_events(
            profile_id=profile_id,
            event_type=event_type,
            project_id=project_id,
            workspace_id=workspace_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
        )

    def get_events_by_project(
        self,
        project_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[MindEvent]:
        """
        Get all events for a specific project

        Args:
            project_id: Project ID
            start_time: Optional start time filter
            end_time: Optional end time filter
            limit: Maximum number of events to return

        Returns:
            List of MindEvent objects for the project, ordered by timestamp DESC
        """
        return self.events.get_events_by_project(
            project_id, start_time=start_time, end_time=end_time, limit=limit
        )

    def get_events_by_workspace(
        self,
        workspace_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        before_id: Optional[str] = None,
    ) -> List[MindEvent]:
        """
        Get all events for a specific workspace

        Args:
            workspace_id: Workspace ID
            start_time: Optional start time filter
            end_time: Optional end time filter
            limit: Maximum number of events to return
            before_id: Optional event ID for cursor-based pagination

        Returns:
            List of MindEvent objects for the workspace, ordered by timestamp DESC
        """
        return self.events.get_events_by_workspace(
            workspace_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            before_id=before_id,
        )

    def get_timeline(
        self,
        profile_id: str,
        project_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[EventType]] = None,
        limit: int = 200,
    ) -> List[MindEvent]:
        """
        Get timeline events (for A.3: Mindspace viewer)

        This method supports the timeline viewer by providing flexible filtering
        and ordering. Events are returned in chronological order (oldest first).

        Args:
            profile_id: Profile ID
            project_id: Optional project filter
            workspace_id: Optional workspace filter
            start_time: Optional start time filter
            end_time: Optional end time filter
            event_types: Optional list of event types to include
            limit: Maximum number of events

        Returns:
            List of MindEvent objects, ordered by timestamp ASC (for timeline display)
        """
        return self.events.get_timeline(
            profile_id=profile_id,
            project_id=project_id,
            workspace_id=workspace_id,
            start_time=start_time,
            end_time=end_time,
            event_types=event_types,
            limit=limit,
        )

    # ==================== Intent Log Methods (Delegated) ====================

    def create_intent_log(self, intent_log: IntentLog) -> IntentLog:
        """
        Create a new intent log entry

        Args:
            intent_log: IntentLog to create

        Returns:
            Created IntentLog
        """
        return self.intent_logs.create_intent_log(intent_log)

    def get_intent_log(self, log_id: str) -> Optional[IntentLog]:
        """Get intent log by ID"""
        return self.intent_logs.get_intent_log(log_id)

    def list_intent_logs(
        self,
        profile_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        has_override: Optional[bool] = None,
        limit: int = 100,
    ) -> List[IntentLog]:
        """
        List intent logs with optional filters

        Args:
            profile_id: Optional profile filter
            start_time: Optional start time filter
            end_time: Optional end time filter
            has_override: Optional filter for logs with user override
            limit: Maximum number of logs to return

        Returns:
            List of IntentLog objects, ordered by timestamp DESC
        """
        return self.intent_logs.list_intent_logs(
            profile_id=profile_id,
            start_time=start_time,
            end_time=end_time,
            has_override=has_override,
            limit=limit,
        )

    def update_intent_log_override(
        self, log_id: str, user_override: Dict[str, Any]
    ) -> Optional[IntentLog]:
        """
        Update user override for an intent log

        Args:
            log_id: Log ID
            user_override: User override data

        Returns:
            Updated IntentLog or None if not found
        """
        return self.intent_logs.update_intent_log_override(log_id, user_override)

    # ==================== Entity Methods (Delegated) ====================

    def create_entity(self, entity: Entity) -> Entity:
        """Create a new entity"""
        return self.entities.create_entity(entity)

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        """Get entity by ID"""
        return self.entities.get_entity(entity_id)

    def list_entities(
        self,
        profile_id: Optional[str] = None,
        entity_type: Optional[EntityType] = None,
        limit: int = 100,
    ) -> List[Entity]:
        """List entities with optional filters"""
        return self.entities.list_entities(
            profile_id=profile_id, entity_type=entity_type, limit=limit
        )

    def update_entity(
        self, entity_id: str, updates: Dict[str, Any]
    ) -> Optional[Entity]:
        """Update entity fields"""
        return self.entities.update_entity(entity_id, updates)

    # ==================== Tag Methods (Delegated) ====================

    def create_tag(self, tag: Tag) -> Tag:
        """Create a new tag"""
        return self.entities.create_tag(tag)

    def get_tag(self, tag_id: str) -> Optional[Tag]:
        """Get tag by ID"""
        return self.entities.get_tag(tag_id)

    def list_tags(
        self,
        profile_id: Optional[str] = None,
        category: Optional[TagCategory] = None,
        limit: int = 100,
    ) -> List[Tag]:
        """List tags with optional filters"""
        return self.entities.list_tags(
            profile_id=profile_id, category=category, limit=limit
        )

    # ==================== Entity-Tag Association Methods (Delegated) ====================

    def tag_entity(
        self, entity_id: str, tag_id: str, value: Optional[str] = None
    ) -> EntityTag:
        """Tag an entity with a tag"""
        return self.entities.tag_entity(entity_id, tag_id, value)

    def untag_entity(self, entity_id: str, tag_id: str) -> bool:
        """Remove a tag from an entity"""
        return self.entities.untag_entity(entity_id, tag_id)

    def get_tags_by_entity(self, entity_id: str) -> List[Tag]:
        """Get all tags associated with an entity"""
        return self.entities.get_tags_by_entity(entity_id)

    def get_entities_by_tag(self, tag_id: str, limit: int = 100) -> List[Entity]:
        """Get all entities tagged with a specific tag"""
        return self.entities.get_entities_by_tag(tag_id, limit=limit)

    def get_entities_by_tags(
        self, tag_ids: List[str], profile_id: Optional[str] = None, limit: int = 100
    ) -> List[Entity]:
        """Get entities that have all specified tags (AND logic)"""
        return self.entities.get_entities_by_tags(
            tag_ids, profile_id=profile_id, limit=limit
        )

    # ==================== Workspace Methods (Delegated) ====================

    def create_workspace(self, workspace: Workspace) -> Workspace:
        """Create a new workspace"""
        return self.workspaces.create_workspace(workspace)

    async def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """Get workspace by ID"""
        return await self.workspaces.get_workspace(workspace_id)

    def list_workspaces(
        self,
        owner_user_id: str,
        primary_project_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Workspace]:
        """List workspaces for a user"""
        return self.workspaces.list_workspaces(
            owner_user_id, primary_project_id=primary_project_id, limit=limit
        )

    async def update_workspace(self, workspace: Workspace) -> Workspace:
        """Update an existing workspace"""
        return await self.workspaces.update_workspace(workspace)

    def delete_workspace(self, workspace_id: str) -> bool:
        """Delete a workspace"""
        return self.workspaces.delete_workspace(workspace_id)

    # ==================== Project Methods (Delegated) ====================

    def create_project(self, project: Any) -> Any:
        """Create a new project"""
        return self.projects.create_project(project)

    def get_project(self, project_id: str) -> Optional[Any]:
        """Get project by ID"""
        return self.projects.get_project(project_id)

    def list_projects(
        self,
        workspace_id: Optional[str] = None,
        state: Optional[str] = None,
        project_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Any]:
        """List projects with optional filters"""
        return self.projects.list_projects(
            workspace_id=workspace_id,
            state=state,
            project_type=project_type,
            limit=limit,
        )

    def update_project(self, project: Any) -> Any:
        """Update an existing project"""
        return self.projects.update_project(project)

    def delete_project(self, project_id: str) -> bool:
        """Delete a project"""
        return self.projects.delete_project(project_id)
