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
        if event.metadata and isinstance(event.metadata, dict):
            if event.metadata.get("should_embed") is True:
                return True
            if event.metadata.get("is_final") is True:
                return True
            if event.metadata.get("is_artifact") is True:
                return True

        if event.event_type == EventType.INTENT_CREATED or event.event_type == EventType.INTENT_UPDATED:
            if event.payload and isinstance(event.payload, dict):
                status = event.payload.get("status")
                priority = event.payload.get("priority")
                if status == "completed" or priority in ["high", "critical"]:
                    return True

        if event.event_type == EventType.PLAYBOOK_STEP:
            if event.payload and isinstance(event.payload, dict):
                if event.payload.get("is_final_output") is True:
                    return True
                if event.payload.get("step_type") == "output" and event.payload.get("status") == "completed":
                    return True

        if event.event_type == EventType.MESSAGE:
            if event.metadata and isinstance(event.metadata, dict):
                if event.metadata.get("from_completed_playbook") is True:
                    return True
                if event.metadata.get("is_artifact_output") is True:
                    return True

        if event.event_type == EventType.OBSIDIAN_NOTE_UPDATED:
            if event.metadata and isinstance(event.metadata, dict):
                should_embed = event.metadata.get("should_embed", False)
                if should_embed:
                    return True

        if event.event_type == EventType.EXECUTION_PLAN:
            return True

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
            if not self.should_generate_embedding(event):
                logger.debug(f"Skipping embedding for event {event.id} (does not meet criteria)")
                return None

            text_content = self._extract_text_from_event(event)
            if not text_content:
                logger.debug(f"No text content in event {event.id}")
                return None

            existing = self._check_existing_embedding(event)
            if existing:
                logger.debug(f"Embedding already exists for event {event.id}")
                return existing

            embedding = await self._generate_embedding(text_content)
            if not embedding:
                logger.warning(f"Failed to generate embedding for event {event.id}")
                return None

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

        if event.event_type == EventType.MESSAGE:
            message = event.payload.get("message", "")

            if event.metadata and isinstance(event.metadata, dict):
                file_analysis = event.metadata.get("file_analysis", {})
                if file_analysis:
                    collaboration = file_analysis.get("collaboration_results", {})
                    file_info_data = file_analysis.get("file_info", {})

                    extracted_text = (
                        collaboration.get("extracted_text") or
                        collaboration.get("summary") or
                        collaboration.get("content") or
                        file_analysis.get("extracted_text") or
                        file_analysis.get("summary")
                    )

                    files = event.payload.get("files", [])
                    file_name = ""
                    if files and len(files) > 0:
                        file_name = files[0].get("name", "unknown")
                    elif file_info_data:
                        file_name = file_info_data.get("name", "unknown")

                    if extracted_text:
                        file_info = f"File: {file_name}\n" if file_name else ""
                        return f"{file_info}{extracted_text}"
                    elif file_name:
                        file_info_parts = [f"File: {file_name}"]
                        if file_info_data:
                            if file_info_data.get("type"):
                                file_info_parts.append(f"Type: {file_info_data['type']}")
                            if file_info_data.get("size"):
                                file_info_parts.append(f"Size: {file_info_data['size']}")
                            if file_info_data.get("pages"):
                                file_info_parts.append(f"Pages: {file_info_data['pages']}")

                        semantic_seeds = collaboration.get("semantic_seeds", {})
                        if semantic_seeds.get("intents"):
                            intents = semantic_seeds.get("intents", [])
                            if intents:
                                file_info_parts.append(f"Intents: {', '.join(intents[:5])}")

                        return "\n".join(file_info_parts)

            if message:
                return message

        elif event.event_type == EventType.INTENT_CREATED or event.event_type == EventType.INTENT_UPDATED:
            title = event.payload.get("title", "")
            description = event.payload.get("description", "")
            if title or description:
                return f"{title}\n{description}".strip()

        elif event.event_type == EventType.PROJECT_UPDATED:
            description = event.payload.get("description", "")
            if description:
                return description

        elif event.event_type == EventType.OBSIDIAN_NOTE_UPDATED:
            note_content = event.payload.get("content") or event.payload.get("body")
            note_title = event.payload.get("title", "")
            if note_content:
                return f"{note_title}\n\n{note_content}" if note_title else note_content

        elif event.event_type == EventType.EXECUTION_PLAN:
            summary = event.payload.get("summary", "")
            steps = event.payload.get("steps", [])

            text_parts = []
            if summary:
                text_parts.append(f"Plan Summary: {summary}")

            if steps and isinstance(steps, list):
                step_texts = []
                for i, step in enumerate(steps, 1):
                    step_name = step.get("name", "") if isinstance(step, dict) else str(step)
                    step_desc = step.get("description", "") if isinstance(step, dict) else ""
                    if step_name:
                        step_text = f"Step {i}: {step_name}"
                        if step_desc:
                            step_text += f" - {step_desc}"
                        step_texts.append(step_text)

                if step_texts:
                    text_parts.append("Steps:\n" + "\n".join(step_texts))

            if text_parts:
                return "\n\n".join(text_parts)

            import json
            return json.dumps(event.payload, indent=2)

        return None

    def _check_existing_embedding(self, event: MindEvent) -> Optional[str]:
        """Check if embedding already exists for this event or file (PostgreSQL)"""
        try:
            import os
            import psycopg2

            postgres_config = {
                "host": os.getenv("POSTGRES_HOST", "postgres"),
                "port": int(os.getenv("POSTGRES_PORT", "5432")),
                "database": os.getenv("POSTGRES_DB", "mindscape_vectors"),
                "user": os.getenv("POSTGRES_USER", "mindscape"),
                "password": os.getenv("POSTGRES_PASSWORD", "mindscape_password"),
            }

            conn = psycopg2.connect(**postgres_config)
            cursor = conn.cursor()

            # First check by event ID
            cursor.execute("""
                SELECT id FROM mindscape_personal
                WHERE source_type = 'mind_event' AND metadata->>'source_id' = %s
                LIMIT 1
            """, (event.id,))

            row = cursor.fetchone()
            if row:
                cursor.close()
                conn.close()
                return row[0]

            # If no embedding for this event, check by file_hash (for file uploads)
            if event.metadata and isinstance(event.metadata, dict):
                file_hash = event.metadata.get("file_hash")
                if file_hash:
                    cursor.execute("""
                        SELECT id FROM mindscape_personal
                        WHERE source_type = 'mind_event'
                          AND metadata->>'file_hash' = %s
                          AND metadata->>'embedding_model' IS NOT NULL
                        ORDER BY created_at DESC
                        LIMIT 1
                    """, (file_hash,))

                    row = cursor.fetchone()
                    if row:
                        logger.info(f"Found existing embedding for file_hash {file_hash[:8]}..., reusing seed {row[0]}")
                        cursor.close()
                        conn.close()
                        return row[0]

            cursor.close()
            conn.close()

            return None

        except Exception as e:
            logger.warning(f"Failed to check existing embedding in PostgreSQL: {e}, trying SQLite fallback")
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

            settings_store = SystemSettingsStore()
            embedding_setting = settings_store.get_setting("embedding_model")

            if not embedding_setting:
                logger.warning("No embedding model configured")
                return None

            model_name = str(embedding_setting.value)
            provider = embedding_setting.metadata.get("provider", "openai")

            if provider == "vertex-ai":
                return await self._generate_embedding_vertex_ai(model_name, text, settings_store)
            else:
                return await self._generate_embedding_openai(model_name, text)

        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}", exc_info=True)
            return None

    async def _generate_embedding_openai(self, model_name: str, text: str) -> Optional[List[float]]:
        """Generate embedding using OpenAI API"""
        try:
            from backend.app.services.config_store import ConfigStore
            import os
            import openai

            config_store = ConfigStore()
            config = config_store.get_or_create_config("default-user")

            api_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("OpenAI API key not configured for embedding generation")
                return None

            client = openai.OpenAI(api_key=api_key)
            response = client.embeddings.create(
                model=model_name,
                input=text
            )

            if response.data and len(response.data) > 0:
                return response.data[0].embedding

            return None
        except Exception as e:
            logger.error(f"Failed to generate OpenAI embedding: {e}", exc_info=True)
            return None

    async def _generate_embedding_vertex_ai(self, model_name: str, text: str, settings_store) -> Optional[List[float]]:
        """Generate embedding using Vertex AI"""
        try:
            import os
            import json
            from google.cloud import aiplatform
            from google.oauth2 import service_account
            from vertexai.language_models import TextEmbeddingModel
            import vertexai

            service_account_setting = settings_store.get_setting("vertex_ai_service_account_json")
            project_id_setting = settings_store.get_setting("vertex_ai_project_id")
            location_setting = settings_store.get_setting("vertex_ai_location")

            vertex_service_account_json = service_account_setting.value if service_account_setting and service_account_setting.value else os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            vertex_project_id = project_id_setting.value if project_id_setting and project_id_setting.value else os.getenv("GOOGLE_CLOUD_PROJECT")
            vertex_location = location_setting.value if location_setting and location_setting.value else os.getenv("VERTEX_LOCATION", "us-central1")

            if not vertex_service_account_json or not vertex_project_id:
                logger.warning("Vertex AI credentials not configured for embedding generation")
                return None

            credentials = None
            if vertex_service_account_json:
                try:
                    sa_info = json.loads(vertex_service_account_json)
                    credentials = service_account.Credentials.from_service_account_info(sa_info)
                    if not vertex_project_id and 'project_id' in sa_info:
                        vertex_project_id = sa_info['project_id']
                except (json.JSONDecodeError, ValueError):
                    credentials = service_account.Credentials.from_service_account_file(vertex_service_account_json)
                    if not vertex_project_id:
                        with open(vertex_service_account_json, 'r') as f:
                            sa_info = json.load(f)
                            if 'project_id' in sa_info:
                                vertex_project_id = sa_info['project_id']

            vertexai.init(project=vertex_project_id, location=vertex_location, credentials=credentials)

            model = TextEmbeddingModel.from_pretrained(model_name)
            embeddings = model.get_embeddings([text])

            if embeddings and len(embeddings) > 0:
                return embeddings[0].values

            return None
        except Exception as e:
            logger.error(f"Failed to generate Vertex AI embedding: {e}", exc_info=True)
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

            seed_type = self._map_event_type_to_seed_type(event.event_type)

            scope = "workspace"
            workspace_id = event.workspace_id
            intent_id = None
            importance = 0.5
            tags = []

            if event.event_type == EventType.PROJECT_UPDATED:
                scope = "global"
                importance = 0.8
            elif event.event_type == EventType.INTENT_CREATED or event.event_type == EventType.INTENT_UPDATED:
                scope = "intent"
                if event.payload and isinstance(event.payload, dict):
                    intent_id = event.payload.get("intent_id") or event.payload.get("id")
                    priority = event.payload.get("priority", "normal")
                    if priority in ["high", "critical"]:
                        importance = 0.9
                    elif priority == "normal":
                        importance = 0.7
                    else:
                        importance = 0.5
            elif workspace_id:
                scope = "workspace"
                if event.metadata and isinstance(event.metadata, dict):
                    if event.metadata.get("is_final") or event.metadata.get("is_artifact"):
                        importance = 0.8
                    elif event.metadata.get("should_embed"):
                        importance = 0.7
            else:
                scope = "global"
                importance = 0.6

            if event.metadata and isinstance(event.metadata, dict):
                metadata_tags = event.metadata.get("tags", [])
                if isinstance(metadata_tags, list):
                    tags = metadata_tags
                elif isinstance(metadata_tags, str):
                    tags = [metadata_tags]

            settings_store = SystemSettingsStore()
            embedding_setting = settings_store.get_setting("embedding_model")
            embedding_model_name = str(embedding_setting.value) if embedding_setting else "unknown"
            embedding_provider = embedding_setting.metadata.get("provider", "openai") if embedding_setting else "unknown"

            confidence = importance
            weight = importance

            # Build metadata JSON with hierarchical memory fields
            metadata_dict = {
                "event_type": event.event_type.value,
                "actor": event.actor.value,
                "channel": event.channel,
                "source_id": event.id,
                "embedding_model": embedding_model_name,
                "embedding_provider": embedding_provider,
                "embedding_dimension": len(embedding),
                "scope": scope,
                "workspace_id": workspace_id,
                "intent_id": intent_id,
                "importance": importance,
                "tags": tags,
                "seed_type": seed_type
            }

            # Add file_hash and file_name from event metadata if available
            if event.metadata and isinstance(event.metadata, dict):
                file_hash = event.metadata.get("file_hash")
                file_name = event.metadata.get("file_name")
                if file_hash:
                    metadata_dict["file_hash"] = file_hash
                if file_name:
                    metadata_dict["file_name"] = file_name

            # Build source_context from scope and related IDs
            source_context_parts = []
            if scope:
                source_context_parts.append(f"scope:{scope}")
            if workspace_id:
                source_context_parts.append(f"workspace:{workspace_id}")
            if intent_id:
                source_context_parts.append(f"intent:{intent_id}")
            source_context = "|".join(source_context_parts) if source_context_parts else None

            # Store embedding in PostgreSQL (using actual table structure)
            cursor.execute("""
                INSERT INTO mindscape_personal
                (id, user_id, source_type, content, metadata, source_id, source_context, confidence, weight, embedding, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s)
            """, (
                seed_id,
                event.profile_id,
                "mind_event",
                text,
                Json(metadata_dict),
                event.id,
                source_context,
                confidence,
                weight,
                embedding,
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

        seed_type = self._map_event_type_to_seed_type(event.event_type)

        from backend.app.services.system_settings_store import SystemSettingsStore
        settings_store = SystemSettingsStore()
        embedding_setting = settings_store.get_setting("embedding_model")
        embedding_model_name = str(embedding_setting.value) if embedding_setting else "unknown"
        embedding_provider = embedding_setting.metadata.get("provider", "openai") if embedding_setting else "unknown"

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
            EventType.PROJECT_UPDATED: "project",
            EventType.PLAYBOOK_STEP: "workflow",
            EventType.EXECUTION_PLAN: "plan",
        }
        return mapping.get(event_type, "general")
