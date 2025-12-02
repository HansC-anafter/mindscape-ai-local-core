"""
Event Embedding Generator Service

Automatically generates embeddings for mind events with text content.
Stores embeddings in mindscape_personal table for semantic search.
"""

import logging
from typing import Optional, List
from datetime import datetime
import uuid

from backend.app.models.mindscape import MindEvent, EventType, EventActor

logger = logging.getLogger(__name__)


class EventEmbeddingGenerator:
    """Generate embeddings for mind events"""

    def __init__(self, store=None):
        """
        Initialize event embedding generator

        Args:
            store: MindscapeStore instance (optional, will create if not provided)
        """
        if store is None:
            from backend.app.services.mindscape_store import MindscapeStore
            self.store = MindscapeStore()
        else:
            self.store = store

    def should_generate_embedding(self, event: MindEvent) -> bool:
        """
        Determine if an event should generate embedding

        Only generates embeddings for:
        - Stable artifacts (finished products, completed intents)
        - User-explicit saves (metadata flag)
        - Deep discussions on specific topics (playbook outputs)

        Does NOT generate for:
        - Every chat message
        - Minor edits/cursor movements
        - All request/response pairs
        - UI actions/settings changes
        """
        # Check metadata flags
        if event.metadata and isinstance(event.metadata, dict):
            if event.metadata.get("should_embed") is True:
                return True
            if event.metadata.get("is_final") is True:
                return True
            if event.metadata.get("is_artifact") is True:
                return True

        # Check event type and status
        if event.event_type == EventType.INTENT_CREATED or event.event_type == EventType.INTENT_UPDATED:
            # Only embed completed or high-priority intents
            if event.payload and isinstance(event.payload, dict):
                status = event.payload.get("status")
                priority = event.payload.get("priority")
                if status == "completed" or priority in ["high", "critical"]:
                    return True

        if event.event_type == EventType.PLAYBOOK_STEP:
            # Only embed final outputs, not intermediate steps
            if event.payload and isinstance(event.payload, dict):
                if event.payload.get("is_final_output") is True:
                    return True
                if event.payload.get("step_type") == "output" and event.payload.get("status") == "completed":
                    return True

        if event.event_type == EventType.MESSAGE:
            # Only embed if explicitly marked or from completed playbook
            if event.metadata and isinstance(event.metadata, dict):
                if event.metadata.get("from_completed_playbook") is True:
                    return True
                if event.metadata.get("is_artifact_output") is True:
                    return True

        if event.event_type == EventType.OBSIDIAN_NOTE_UPDATED:
            # Only embed research-related notes based on metadata filters
            if event.metadata and isinstance(event.metadata, dict):
                should_embed = event.metadata.get("should_embed", False)
                if should_embed:
                    return True

        # Default: don't generate embedding
        return False

    async def generate_embedding_for_event(self, event: MindEvent) -> Optional[str]:
        """
        Generate embedding for an event if it meets criteria

        Args:
            event: MindEvent to process

        Returns:
            Seed ID if embedding was created, None otherwise
        """
        try:
            # Check if this event should generate embedding
            if not self.should_generate_embedding(event):
                logger.debug(f"Skipping embedding for event {event.id} (does not meet criteria)")
                return None

            # Extract text content from event
            text_content = self._extract_text_from_event(event)
            if not text_content:
                logger.debug(f"No text content in event {event.id}")
                return None

            # Check if embedding already exists
            existing = self._check_existing_embedding(event)
            if existing:
                logger.debug(f"Embedding already exists for event {event.id}")
                return existing

            # Generate embedding
            embedding = await self._generate_embedding(text_content)
            if not embedding:
                logger.warning(f"Failed to generate embedding for event {event.id}")
                return None

            # Store in mindscape_personal
            seed_id = self._store_embedding(event, text_content, embedding)

            logger.info(f"Generated embedding for event {event.id} -> seed {seed_id}")
            return seed_id

        except Exception as e:
            logger.error(f"Failed to generate embedding for event {event.id}: {e}", exc_info=True)
            return None

    def _extract_text_from_event(self, event: MindEvent) -> Optional[str]:
        """Extract text content from event payload"""
        if not event.payload or not isinstance(event.payload, dict):
            return None

        # Extract text based on event type
        if event.event_type == EventType.MESSAGE:
            # User or assistant messages
            message = event.payload.get("message", "")
            if message:
                return message

        elif event.event_type == EventType.INTENT_CREATED or event.event_type == EventType.INTENT_UPDATED:
            # Intent card content
            title = event.payload.get("title", "")
            description = event.payload.get("description", "")
            if title or description:
                return f"{title}\n{description}".strip()

        elif event.event_type == EventType.PROFILE_UPDATED:
            # Profile changes
            self_description = event.payload.get("self_description", "")
            if self_description:
                return self_description

        elif event.event_type == EventType.FILE_UPLOADED:
            # File content (if extracted)
            content = event.payload.get("extracted_text", "")
            if content:
                return content

        elif event.event_type == EventType.OBSIDIAN_NOTE_UPDATED:
            # Obsidian note content
            note_content = event.payload.get("content") or event.payload.get("body")
            note_title = event.payload.get("title", "")
            if note_content:
                return f"{note_title}\n\n{note_content}" if note_title else note_content

        return None

    def _check_existing_embedding(self, event: MindEvent) -> Optional[str]:
        """Check if embedding already exists for this event (PostgreSQL)"""
        try:
            import os
            import psycopg2

            # Get PostgreSQL config from environment
            postgres_config = {
                "host": os.getenv("POSTGRES_HOST", "postgres"),
                "port": int(os.getenv("POSTGRES_PORT", "5432")),
                "database": os.getenv("POSTGRES_DB", "mindscape_vectors"),
                "user": os.getenv("POSTGRES_USER", "mindscape"),
                "password": os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
            }

            conn = psycopg2.connect(**postgres_config)
            cursor = conn.cursor()

            # Check mindscape_personal for existing embedding
            cursor.execute("""
                SELECT id FROM mindscape_personal
                WHERE source_type = 'mind_event' AND metadata->>'source_id' = %s
                LIMIT 1
            """, (event.id,))

            row = cursor.fetchone()
            cursor.close()
            conn.close()

            return row[0] if row else None

        except Exception as e:
            logger.warning(f"Failed to check existing embedding in PostgreSQL: {e}, trying SQLite fallback")
            # Fallback to SQLite check
            try:
                import sqlite3
                from pathlib import Path

                db_path = Path("./data/mindscape.db")
                if not db_path.exists():
                    return None

                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id FROM mindscape_personal
                    WHERE source_type = 'mind_event' AND source_id = ?
                    LIMIT 1
                """, (event.id,))

                row = cursor.fetchone()
                conn.close()

                return row["id"] if row else None
            except Exception as fallback_error:
                logger.warning(f"SQLite fallback also failed: {fallback_error}")
                return None

    async def _generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text"""
        try:
            from backend.app.services.system_settings_store import SystemSettingsStore
            from backend.app.services.config_store import ConfigStore
            import os

            # Get embedding model from system settings
            settings_store = SystemSettingsStore()
            embedding_setting = settings_store.get_setting("embedding_model")

            if not embedding_setting:
                logger.warning("No embedding model configured")
                return None

            model_name = str(embedding_setting.value)
            provider = embedding_setting.metadata.get("provider", "openai")

            # Get API key
            config_store = ConfigStore()
            config = config_store.get_or_create_config("default-user")

            api_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("OpenAI API key not configured for embedding generation")
                return None

            # Generate embedding
            import openai
            client = openai.OpenAI(api_key=api_key)
            response = client.embeddings.create(
                model=model_name,
                input=text
            )

            if response.data and len(response.data) > 0:
                return response.data[0].embedding

            return None

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}", exc_info=True)
            return None

    def _store_embedding(self, event: MindEvent, text: str, embedding: List[float]) -> str:
        """Store embedding in mindscape_personal table (PostgreSQL with hierarchical memory support)"""
        try:
            from backend.app.services.system_settings_store import SystemSettingsStore
            import os
            import psycopg2
            from psycopg2.extras import Json

            # Get PostgreSQL config from environment
            postgres_config = {
                "host": os.getenv("POSTGRES_HOST", "postgres"),
                "port": int(os.getenv("POSTGRES_PORT", "5432")),
                "database": os.getenv("POSTGRES_DB", "mindscape_vectors"),
                "user": os.getenv("POSTGRES_USER", "mindscape"),
                "password": os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
            }

            conn = psycopg2.connect(**postgres_config)
            cursor = conn.cursor()

            seed_id = str(uuid.uuid4())
            now = datetime.utcnow()

            # Determine seed type from event type
            seed_type = self._map_event_type_to_seed_type(event.event_type)

            # Determine scope based on event context
            scope = "workspace"  # default
            workspace_id = event.workspace_id
            intent_id = None
            importance = 0.5  # default
            tags = []

            # Determine scope and importance based on event type
            if event.event_type == EventType.PROFILE_UPDATED:
                scope = "global"
                importance = 0.8  # Profile updates are important global context
            elif event.event_type == EventType.INTENT_CREATED or event.event_type == EventType.INTENT_UPDATED:
                scope = "intent"
                # Extract intent_id from payload if available
                if event.payload and isinstance(event.payload, dict):
                    intent_id = event.payload.get("intent_id") or event.payload.get("id")
                    # High priority intents are more important
                    priority = event.payload.get("priority", "normal")
                    if priority in ["high", "critical"]:
                        importance = 0.9
                    elif priority == "normal":
                        importance = 0.7
                    else:
                        importance = 0.5
            elif workspace_id:
                scope = "workspace"
                # Completed tasks/artifacts are more important
                if event.metadata and isinstance(event.metadata, dict):
                    if event.metadata.get("is_final") or event.metadata.get("is_artifact"):
                        importance = 0.8
                    elif event.metadata.get("should_embed"):
                        importance = 0.7
            else:
                scope = "global"
                importance = 0.6

            # Extract tags from metadata if available
            if event.metadata and isinstance(event.metadata, dict):
                metadata_tags = event.metadata.get("tags", [])
                if isinstance(metadata_tags, list):
                    tags = metadata_tags
                elif isinstance(metadata_tags, str):
                    tags = [metadata_tags]

            # Get embedding model info for metadata
            settings_store = SystemSettingsStore()
            embedding_setting = settings_store.get_setting("embedding_model")
            embedding_model_name = str(embedding_setting.value) if embedding_setting else "unknown"
            embedding_provider = embedding_setting.metadata.get("provider", "openai") if embedding_setting else "unknown"

            # Build metadata JSON
            metadata_dict = {
                "event_type": event.event_type.value,
                "actor": event.actor.value,
                "channel": event.channel,
                "source_type": "mind_event",
                "source_id": event.id,
                "embedding_model": embedding_model_name,
                "embedding_provider": embedding_provider,
                "embedding_dimension": len(embedding)
            }

            # Store embedding in PostgreSQL
            cursor.execute("""
                INSERT INTO mindscape_personal
                (id, user_id, source_type, content, metadata, confidence, weight, embedding,
                 scope, workspace_id, intent_id, importance, tags, created_at, updated_at, last_used_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                seed_id,
                event.profile_id,
                "mind_event",
                text,
                Json(metadata_dict),
                1.0,
                1.0,
                embedding,
                scope,
                workspace_id,
                intent_id,
                importance,
                tags,
                now,
                now,
                now
            ))

            conn.commit()
            cursor.close()
            conn.close()

            logger.info(f"Stored embedding with scope={scope}, workspace_id={workspace_id}, intent_id={intent_id}, importance={importance}")
            return seed_id

        except Exception as e:
            logger.error(f"Failed to store embedding: {e}", exc_info=True)
            # Fallback to SQLite if PostgreSQL fails (for backward compatibility)
            try:
                return self._store_embedding_sqlite_fallback(event, text, embedding)
            except Exception as fallback_error:
                logger.error(f"Fallback to SQLite also failed: {fallback_error}", exc_info=True)
                raise

    def _store_embedding_sqlite_fallback(self, event: MindEvent, text: str, embedding: List[float]) -> str:
        """Fallback method to store embedding in SQLite (for backward compatibility)"""
        import sqlite3
        import json
        from pathlib import Path

        db_path = Path("./data/mindscape.db")
        db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Ensure mindscape_personal table exists (legacy SQLite schema)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS mindscape_personal (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                seed_type TEXT NOT NULL,
                seed_text TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_id TEXT,
                confidence REAL DEFAULT 1.0,
                weight REAL DEFAULT 1.0,
                embedding TEXT,
                metadata TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        seed_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()

        # Determine seed type from event type
        seed_type = self._map_event_type_to_seed_type(event.event_type)

        # Get embedding model info for metadata
        from backend.app.services.system_settings_store import SystemSettingsStore
        settings_store = SystemSettingsStore()
        embedding_setting = settings_store.get_setting("embedding_model")
        embedding_model_name = str(embedding_setting.value) if embedding_setting else "unknown"
        embedding_provider = embedding_setting.metadata.get("provider", "openai") if embedding_setting else "unknown"

        # Store embedding
        cursor.execute("""
            INSERT INTO mindscape_personal
            (id, user_id, seed_type, seed_text, source_type, source_id, confidence, weight, embedding, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            seed_id,
            event.profile_id,
            seed_type,
            text,
            "mind_event",
            event.id,
            1.0,
            1.0,
            json.dumps(embedding),
            json.dumps({
                "event_type": event.event_type.value,
                "actor": event.actor.value,
                "channel": event.channel,
                "embedding_model": embedding_model_name,
                "embedding_provider": embedding_provider,
                "embedding_dimension": len(embedding)
            }),
            now,
            now
        ))

        conn.commit()
        conn.close()

        return seed_id

    def _map_event_type_to_seed_type(self, event_type: EventType) -> str:
        """Map event type to seed type for mindscape_personal"""
        mapping = {
            EventType.MESSAGE: "conversation",
            EventType.INTENT_CREATED: "intent",
            EventType.INTENT_UPDATED: "intent",
            EventType.PROFILE_UPDATED: "profile",
            EventType.FILE_UPLOADED: "document",
            EventType.PLAYBOOK_STARTED: "workflow",
            EventType.PLAYBOOK_COMPLETED: "workflow",
        }
        return mapping.get(event_type, "general")
