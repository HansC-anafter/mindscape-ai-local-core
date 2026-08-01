import logging
import uuid
from typing import Any, Dict, List, Optional

from backend.app.models.mindscape import EventType, MindEvent
from backend.app.services.event_embedding_generator_core.clock import _utc_now
from backend.app.services.event_embedding_generator_core.eligibility import (
    map_event_type_to_seed_type,
)

logger = logging.getLogger("backend.app.services.event_embedding_generator")


def check_existing_embedding(event: MindEvent) -> Optional[str]:
    """Check if embedding already exists for this event or file."""
    conn = None
    cursor = None
    try:
        from backend.app.database.vector_connection import (
            get_vector_dbapi_connection,
        )

        conn = get_vector_dbapi_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id FROM mindscape_personal
            WHERE source_type = 'mind_event' AND metadata->>'source_id' = %s
            LIMIT 1
        """,
            (event.id,),
        )

        row = cursor.fetchone()
        if row:
            return row[0]

        if event.metadata and isinstance(event.metadata, dict):
            file_hash = event.metadata.get("file_hash")
            if file_hash:
                cursor.execute(
                    """
                    SELECT id FROM mindscape_personal
                    WHERE source_type = 'mind_event'
                      AND metadata->>'file_hash' = %s
                      AND metadata->>'embedding_model' IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT 1
                """,
                    (file_hash,),
                )

                row = cursor.fetchone()
                if row:
                    logger.info(
                        "Found existing embedding for file_hash %s..., reusing seed %s",
                        file_hash[:8],
                        row[0],
                    )
                    return row[0]

        return None

    except Exception as exc:
        logger.warning("Failed to check existing embedding in PostgreSQL: %s", exc)
        return None
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            if conn is not None:
                conn.close()


def build_embedding_storage_payload(
    event: MindEvent,
    embedding: List[float],
    *,
    embedding_model_name: str,
    embedding_provider: str,
) -> Dict[str, Any]:
    """Build storage metadata without opening a DB connection."""
    seed_id = str(uuid.uuid4())
    now = _utc_now()
    seed_type = map_event_type_to_seed_type(event.event_type)

    scope = "workspace"
    workspace_id = event.workspace_id
    intent_id = None
    importance = 0.5
    tags = []

    if event.event_type == EventType.PROJECT_UPDATED:
        scope = "global"
        importance = 0.8
    elif (
        event.event_type == EventType.INTENT_CREATED
        or event.event_type == EventType.INTENT_UPDATED
    ):
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
        "seed_type": seed_type,
    }

    if event.metadata and isinstance(event.metadata, dict):
        file_hash = event.metadata.get("file_hash")
        file_name = event.metadata.get("file_name")
        if file_hash:
            metadata_dict["file_hash"] = file_hash
        if file_name:
            metadata_dict["file_name"] = file_name

    source_context_parts = []
    if scope:
        source_context_parts.append(f"scope:{scope}")
    if workspace_id:
        source_context_parts.append(f"workspace:{workspace_id}")
    if intent_id:
        source_context_parts.append(f"intent:{intent_id}")
    source_context = "|".join(source_context_parts) if source_context_parts else None

    return {
        "seed_id": seed_id,
        "now": now,
        "scope": scope,
        "workspace_id": workspace_id,
        "intent_id": intent_id,
        "importance": importance,
        "metadata": metadata_dict,
        "source_context": source_context,
    }


def store_embedding(event: MindEvent, text: str, embedding: List[float]) -> str:
    """Store embedding in memory_embeddings table."""
    conn = None
    cursor = None
    try:
        from psycopg2.extras import Json
        from backend.app.database.vector_connection import (
            get_vector_dbapi_connection,
        )
        from backend.app.services.system_settings_store import SystemSettingsStore

        conn = get_vector_dbapi_connection()
        cursor = conn.cursor()

        settings_store = SystemSettingsStore()
        embedding_setting = settings_store.get_setting("embedding_model")
        embedding_model_name = (
            str(embedding_setting.value) if embedding_setting else "unknown"
        )
        embedding_provider = (
            embedding_setting.metadata.get("provider", "openai")
            if embedding_setting
            else "unknown"
        )
        payload = build_embedding_storage_payload(
            event,
            embedding,
            embedding_model_name=embedding_model_name,
            embedding_provider=embedding_provider,
        )

        confidence = payload["importance"]
        weight = payload["importance"]

        cursor.execute(
            """
            INSERT INTO memory_embeddings
            (id, user_id, source_type, content, metadata, source_id, source_context, confidence, weight, embedding, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s)
        """,
            (
                payload["seed_id"],
                event.profile_id,
                "mind_event",
                text,
                Json(payload["metadata"]),
                event.id,
                payload["source_context"],
                confidence,
                weight,
                embedding,
                payload["now"],
                payload["now"],
            ),
        )

        conn.commit()

        logger.info(
            "Stored embedding with scope=%s, workspace_id=%s, intent_id=%s, importance=%s",
            payload["scope"],
            payload["workspace_id"],
            payload["intent_id"],
            payload["importance"],
        )
        return payload["seed_id"]

    except Exception as exc:
        logger.error("Failed to store embedding: %s", exc, exc_info=True)
        raise
    finally:
        try:
            if cursor is not None:
                cursor.close()
        finally:
            if conn is not None:
                conn.close()
