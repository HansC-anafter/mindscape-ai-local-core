"""
Mindscape data store service
Handles local data persistence for profiles, intents, and executions

This is a Facade that delegates to domain-specific stores.
"""

import os
import json
import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from contextlib import contextmanager
import logging

from backend.app.models.mindscape import (
    MindscapeProfile, IntentCard, AgentExecution,
    IntentStatus, PriorityLevel, MindEvent, EventType, EventActor, IntentLog,
    Entity, EntityType, Tag, TagCategory, EntityTag
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

logger = logging.getLogger(__name__)


class MindscapeStore:
    """
    Facade for all domain stores

    This class provides a unified interface to all domain-specific stores
    while maintaining backward compatibility with existing code.
    """

    def __init__(self, db_path: str = None):
        if db_path is None:
            if os.path.exists('/.dockerenv') or os.environ.get('PYTHONPATH') == '/app':
                db_path = '/app/data/mindscape.db'
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
                data_dir = os.path.join(base_dir, "data")
                os.makedirs(data_dir, exist_ok=True)
                db_path = os.path.join(data_dir, "mindscape.db")

        self.db_path = db_path

        # Initialize all domain stores
        self.profiles = ProfilesStore(db_path)
        self.intents = IntentsStore(db_path)
        self.agent_executions = AgentExecutionsStore(db_path)
        self.events = EventsStore(db_path)
        self.intent_logs = IntentLogsStore(db_path)
        self.entities = EntitiesStore(db_path)
        self.workspaces = WorkspacesStore(db_path)
        self.artifacts = ArtifactsStore(db_path)

        # Initialize database schema
        # Note: Database migrations are managed by Alembic (run: alembic upgrade head)
        self._init_db()
        self.ensure_default_profile()

    @contextmanager
    def get_connection(self):
        """Get database connection with proper cleanup"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database tables"""
        from backend.app.services.stores.schema import init_schema
        try:
            from backend.migrations.add_workspace_type_and_storyline_tags import run_sqlite_migration
        except Exception:
            run_sqlite_migration = None

        with self.get_connection() as conn:
            cursor = conn.cursor()
            init_schema(cursor)
            conn.commit()

        # Apply lightweight migration to ensure new columns exist even without Alembic runtime
        if 'sqlite' in self.db_path and run_sqlite_migration:
            try:
                run_sqlite_migration(self.db_path)
            except Exception as e:
                logger.warning(f"SQLite migration failed (non-blocking): {e}")

    def _migrate_db(self):
        """
        Database migrations are now managed by Alembic.

        Run migrations using: alembic upgrade head
        """
        # Migrations are handled by Alembic, not here
        pass

    def ensure_default_profile(self):
        """Ensure default-user profile exists for local development"""
        profile = self.get_profile('default-user')
        if not profile:
            from backend.app.models.mindscape import UserPreferences
            logger.info("Creating default-user profile...")
            default_profile = MindscapeProfile(
                id='default-user',
                name='Default User',
                email=None,
                roles=[],
                domains=[],
                preferences=UserPreferences(
                    language='zh-TW',
                    timezone='Asia/Taipei'
                ),
                onboarding_state=None,
                self_description=None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                version=1
            )
            self.create_profile(default_profile)
            logger.info("Default profile created successfully")

    # ==================== Profile Methods (Delegated) ====================

    def create_profile(self, profile: MindscapeProfile) -> MindscapeProfile:
        """Create a new profile"""
        return self.profiles.create_profile(profile)

    def get_profile(self, profile_id: str, apply_habits: bool = True) -> Optional[MindscapeProfile]:
        """
        Get profile by ID

        Args:
            profile_id: Profile ID
            apply_habits: If True, apply confirmed habits to preferences (default: True)
        """
        return self.profiles.get_profile(profile_id, apply_habits=apply_habits)

    def update_profile(self, profile_id: str, updates: Dict[str, Any]) -> Optional[MindscapeProfile]:
        """Update profile"""
        return self.profiles.update_profile(profile_id, updates)

    # ==================== Intent Methods (Delegated) ====================

    def create_intent(self, intent: IntentCard) -> IntentCard:
        """Create a new intent"""
        return self.intents.create_intent(intent)

    def get_intent(self, intent_id: str) -> Optional[IntentCard]:
        """Get intent by ID"""
        return self.intents.get_intent(intent_id)

    def list_intents(self, profile_id: str, status: Optional[IntentStatus] = None,
                    priority: Optional[PriorityLevel] = None) -> List[IntentCard]:
        """List intents for a profile with optional filters"""
        return self.intents.list_intents(profile_id, status=status, priority=priority)

    # ==================== Agent Execution Methods (Delegated) ====================

    def create_agent_execution(self, execution: AgentExecution) -> AgentExecution:
        """Create a new agent execution record"""
        return self.agent_executions.create_agent_execution(execution)

    def get_agent_execution(self, execution_id: str) -> Optional[AgentExecution]:
        """Get agent execution by ID"""
        return self.agent_executions.get_agent_execution(execution_id)

    def list_agent_executions(self, profile_id: str, limit: int = 50) -> List[AgentExecution]:
        """List recent agent executions for a profile"""
        return self.agent_executions.list_agent_executions(profile_id, limit=limit)


    # ==================== Event Methods (Delegated) ====================

    def create_event(self, event: MindEvent, generate_embedding: bool = False) -> MindEvent:
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
        metadata: Optional[Dict[str, Any]] = None
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
        limit: int = 100
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
            limit=limit
        )

    def get_events_by_project(
        self,
        project_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
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
        return self.events.get_events_by_project(project_id, start_time=start_time, end_time=end_time, limit=limit)

    def get_events_by_workspace(
        self,
        workspace_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        before_id: Optional[str] = None
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
        return self.events.get_events_by_workspace(workspace_id, start_time=start_time, end_time=end_time, limit=limit, before_id=before_id)

    def get_timeline(
        self,
        profile_id: str,
        project_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_types: Optional[List[EventType]] = None,
        limit: int = 200
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
            limit=limit
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
        limit: int = 100
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
            limit=limit
        )

    def update_intent_log_override(self, log_id: str, user_override: Dict[str, Any]) -> Optional[IntentLog]:
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
        limit: int = 100
    ) -> List[Entity]:
        """List entities with optional filters"""
        return self.entities.list_entities(profile_id=profile_id, entity_type=entity_type, limit=limit)

    def update_entity(self, entity_id: str, updates: Dict[str, Any]) -> Optional[Entity]:
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
        limit: int = 100
    ) -> List[Tag]:
        """List tags with optional filters"""
        return self.entities.list_tags(profile_id=profile_id, category=category, limit=limit)

    # ==================== Entity-Tag Association Methods (Delegated) ====================

    def tag_entity(self, entity_id: str, tag_id: str, value: Optional[str] = None) -> EntityTag:
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
        self,
        tag_ids: List[str],
        profile_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Entity]:
        """Get entities that have all specified tags (AND logic)"""
        return self.entities.get_entities_by_tags(tag_ids, profile_id=profile_id, limit=limit)

    # ==================== Workspace Methods (Delegated) ====================

    def create_workspace(self, workspace: Workspace) -> Workspace:
        """Create a new workspace"""
        return self.workspaces.create_workspace(workspace)

    def get_workspace(self, workspace_id: str) -> Optional[Workspace]:
        """Get workspace by ID"""
        return self.workspaces.get_workspace(workspace_id)

    def list_workspaces(
        self,
        owner_user_id: str,
        primary_project_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Workspace]:
        """List workspaces for a user"""
        return self.workspaces.list_workspaces(owner_user_id, primary_project_id=primary_project_id, limit=limit)

    def update_workspace(self, workspace: Workspace) -> Workspace:
        """Update an existing workspace"""
        return self.workspaces.update_workspace(workspace)

    def delete_workspace(self, workspace_id: str) -> bool:
        """Delete a workspace"""
        return self.workspaces.delete_workspace(workspace_id)
