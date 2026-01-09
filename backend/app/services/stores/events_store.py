"""
Events store for Mindscape data persistence
Handles mind events (timeline) CRUD operations
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from backend.app.services.stores.base import StoreBase
from ...models.mindscape import MindEvent, EventType, EventActor
import logging

logger = logging.getLogger(__name__)


class EventsStore(StoreBase):
    """Store for managing mind events"""

    def create_event(self, event: MindEvent, generate_embedding: bool = False) -> MindEvent:
        """
        Create a new mindspace event

        Args:
            event: MindEvent to create
            generate_embedding: Whether to automatically generate embedding for this event

        Returns:
            Created MindEvent
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO mind_events (
                    id, timestamp, actor, channel, profile_id, project_id, workspace_id,
                    thread_id, event_type, payload, entity_ids, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                event.id,
                self.to_isoformat(event.timestamp),
                event.actor.value,
                event.channel,
                event.profile_id,
                event.project_id,
                event.workspace_id,
                event.thread_id,
                event.event_type.value,
                self.serialize_json(event.payload),
                self.serialize_json(event.entity_ids),
                self.serialize_json(event.metadata)
            ))
            conn.commit()

        # Generate embedding asynchronously (don't block event creation)
        if generate_embedding:
            try:
                from backend.app.services.event_embedding_generator import EventEmbeddingGenerator
                import asyncio

                generator = EventEmbeddingGenerator()
                # Run async in background (fire and forget)
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If already in async context, create task
                        asyncio.create_task(generator.generate_embedding_for_event(event))
                    else:
                        # Run in new event loop
                        asyncio.run(generator.generate_embedding_for_event(event))
                except RuntimeError:
                    # No event loop, create new one
                    asyncio.run(generator.generate_embedding_for_event(event))
            except Exception as e:
                # Don't fail event creation if embedding generation fails
                logger.warning(f"Failed to generate embedding for event {event.id}: {e}")

        return event

    def get_event(self, event_id: str) -> Optional[MindEvent]:
        """
        Get a single event by ID

        Args:
            event_id: Event ID

        Returns:
            MindEvent or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM mind_events WHERE id = ?', (event_id,))
            row = cursor.fetchone()
            if not row:
                return None
        return self._row_to_event(row)

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
            payload: New payload (if provided)
            metadata: New metadata (if provided)

        Returns:
            True if update succeeded
        """
        from typing import Dict, Any, Optional
        with self.transaction() as conn:
            cursor = conn.cursor()

            updates = []
            values = []

            if payload is not None:
                updates.append('payload = ?')
                values.append(self.serialize_json(payload))

            if metadata is not None:
                updates.append('metadata = ?')
                values.append(self.serialize_json(metadata))

            if not updates:
                return True  # Nothing to update

            values.append(event_id)

            cursor.execute(
                f'UPDATE mind_events SET {", ".join(updates)} WHERE id = ?',
                values
            )

            conn.commit()
            return cursor.rowcount > 0

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
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM mind_events WHERE profile_id = ?'
            params = [profile_id]

            if event_type:
                query += ' AND event_type = ?'
                params.append(event_type.value)

            if project_id:
                query += ' AND project_id = ?'
                params.append(project_id)

            if workspace_id:
                query += ' AND workspace_id = ?'
                params.append(workspace_id)

            if start_time:
                query += ' AND timestamp >= ?'
                params.append(self.to_isoformat(start_time))

            if end_time:
                query += ' AND timestamp <= ?'
                params.append(self.to_isoformat(end_time))

            query += ' ORDER BY timestamp DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            # Convert rows to events, with error handling
            events = []
            for i, row in enumerate(rows):
                try:
                    event = self._row_to_event(row)
                    events.append(event)
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error converting row {i} to event in get_events (base): {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    # Skip this row and continue
                    continue
            return events

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
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM mind_events WHERE project_id = ?'
            params = [project_id]

            if start_time:
                query += ' AND timestamp >= ?'
                params.append(self.to_isoformat(start_time))

            if end_time:
                query += ' AND timestamp <= ?'
                params.append(self.to_isoformat(end_time))

            query += ' ORDER BY timestamp DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            # Convert rows to events, with error handling
            events = []
            for i, row in enumerate(rows):
                try:
                    event = self._row_to_event(row)
                    events.append(event)
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error converting row {i} to event in get_events: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    # Skip this row and continue
                    continue
            return events

    def get_events_by_workspace(
        self,
        workspace_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        before_id: Optional[str] = None
    ) -> List[MindEvent]:
        """
        Get all events for a specific workspace with optional cursor-based pagination

        Args:
            workspace_id: Workspace ID
            start_time: Optional start time filter
            end_time: Optional end time filter
            limit: Maximum number of events to return
            before_id: Optional event ID for cursor-based pagination (load events before this ID)

        Returns:
            List of MindEvent objects for the workspace, ordered by timestamp DESC
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM mind_events WHERE workspace_id = ?'
            params = [workspace_id]

            if start_time:
                query += ' AND timestamp >= ?'
                params.append(self.to_isoformat(start_time))

            if end_time:
                query += ' AND timestamp <= ?'
                params.append(self.to_isoformat(end_time))

            if before_id:
                query += ' AND (timestamp < (SELECT timestamp FROM mind_events WHERE id = ?) OR (timestamp = (SELECT timestamp FROM mind_events WHERE id = ?) AND id < ?))'
                params.extend([before_id, before_id, before_id])

            query += ' ORDER BY timestamp DESC, id DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            # Convert rows to events, with error handling
            events = []
            for i, row in enumerate(rows):
                try:
                    event = self._row_to_event(row)
                    events.append(event)
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error converting row {i} to event in get_events_by_workspace: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    # Skip this row and continue
                    continue
            return events

    def get_events_by_thread(
        self,
        workspace_id: str,
        thread_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
        before_id: Optional[str] = None
    ) -> List[MindEvent]:
        """
        Get all events for a specific conversation thread with optional cursor-based pagination

        Args:
            workspace_id: Workspace ID
            thread_id: Thread ID
            start_time: Optional start time filter
            end_time: Optional end time filter
            limit: Maximum number of events to return
            before_id: Optional event ID for cursor-based pagination (load events before this ID)

        Returns:
            List of MindEvent objects for the thread, ordered by timestamp DESC
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM mind_events WHERE workspace_id = ? AND thread_id = ?'
            params = [workspace_id, thread_id]

            if start_time:
                query += ' AND timestamp >= ?'
                params.append(self.to_isoformat(start_time))

            if end_time:
                query += ' AND timestamp <= ?'
                params.append(self.to_isoformat(end_time))

            if before_id:
                query += ' AND (timestamp < (SELECT timestamp FROM mind_events WHERE id = ?) OR (timestamp = (SELECT timestamp FROM mind_events WHERE id = ?) AND id < ?))'
                params.extend([before_id, before_id, before_id])

            query += ' ORDER BY timestamp DESC, id DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            # Convert rows to events, with error handling
            events = []
            for i, row in enumerate(rows):
                try:
                    event = self._row_to_event(row)
                    events.append(event)
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error converting row {i} to event in get_events_by_thread: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    # Skip this row and continue
                    continue
            return events

    def count_messages_by_thread(
        self,
        workspace_id: str,
        thread_id: str,
        include_execution_chat: bool = False
    ) -> int:
        """
        Count MESSAGE events for a specific conversation thread
        
        Args:
            workspace_id: Workspace ID
            thread_id: Thread ID
            include_execution_chat: If True, also count EXECUTION_CHAT events (default: False)
            
        Returns:
            Count of MESSAGE events (and optionally EXECUTION_CHAT) in the thread
            
        Note:
            Currently only counts EventType.MESSAGE by default, as "message_count" semantically
            refers to user/assistant messages. TOOL_CALL and other event types are excluded
            as they are not user-visible conversation messages.
            
            If you need to count all conversation-related events, set include_execution_chat=True
            or consider using a different metric name (e.g., "conversation_count").
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            if include_execution_chat:
                query = '''
                    SELECT COUNT(*) 
                    FROM mind_events 
                    WHERE workspace_id = ? 
                      AND thread_id = ? 
                      AND (event_type = ? OR event_type = ?)
                '''
                cursor.execute(query, (
                    workspace_id, 
                    thread_id, 
                    EventType.MESSAGE.value,
                    EventType.EXECUTION_CHAT.value
                ))
            else:
                query = '''
                    SELECT COUNT(*) 
                    FROM mind_events 
                    WHERE workspace_id = ? 
                      AND thread_id = ? 
                      AND event_type = ?
                '''
                cursor.execute(query, (workspace_id, thread_id, EventType.MESSAGE.value))
            result = cursor.fetchone()
            return result[0] if result else 0

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
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM mind_events WHERE profile_id = ?'
            params = [profile_id]

            if project_id:
                query += ' AND project_id = ?'
                params.append(project_id)

            if workspace_id:
                query += ' AND workspace_id = ?'
                params.append(workspace_id)

            if start_time:
                query += ' AND timestamp >= ?'
                params.append(self.to_isoformat(start_time))

            if end_time:
                query += ' AND timestamp <= ?'
                params.append(self.to_isoformat(end_time))

            if event_types:
                placeholders = ','.join(['?'] * len(event_types))
                query += f' AND event_type IN ({placeholders})'
                params.extend([et.value for et in event_types])

            # Use DESC to get most recent events first (for chat display)
            # If timeline viewer needs ASC, it can reverse the array
            query += ' ORDER BY timestamp DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            # Convert rows to events, with error handling
            events = []
            for i, row in enumerate(rows):
                try:
                    event = self._row_to_event(row)
                    events.append(event)
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Error converting row {i} to event in get_timeline: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    # Skip this row and continue
                    continue
            return events

    def _row_to_event(self, row) -> MindEvent:
        """Convert database row to MindEvent"""
        # sqlite3.Row doesn't support .get(), use direct access with None check
        # Ensure we extract string values from sqlite3.Row before deserializing
        # sqlite3.Row returns None for NULL values, so we can safely check

        # Extract values from sqlite3.Row - these should be Python native types
        # For TEXT columns, sqlite3.Row returns str or None
        # For JSON columns stored as TEXT, we get the JSON string
        try:
            payload_val = row['payload']
            entity_ids_val = row['entity_ids']
            metadata_val = row['metadata']
        except KeyError as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Missing column in row: {e}, available columns: {row.keys() if hasattr(row, 'keys') else 'unknown'}")
            raise

        # Check if values are sqlite3.Row objects (shouldn't happen, but handle it)
        if hasattr(payload_val, '__class__') and payload_val.__class__.__name__ == 'Row':
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"payload_val is sqlite3.Row object! This shouldn't happen. Row keys: {payload_val.keys() if hasattr(payload_val, 'keys') else 'unknown'}")
            payload_val = None

        if hasattr(entity_ids_val, '__class__') and entity_ids_val.__class__.__name__ == 'Row':
            entity_ids_val = None

        if hasattr(metadata_val, '__class__') and metadata_val.__class__.__name__ == 'Row':
            metadata_val = None

        # Convert to string if not None, otherwise use None
        # sqlite3.Row should return str for TEXT columns, but ensure it's a string
        payload_str = str(payload_val) if payload_val is not None else None
        entity_ids_str = str(entity_ids_val) if entity_ids_val is not None else None
        metadata_str = str(metadata_val) if metadata_val is not None else None

        # Deserialize JSON fields
        payload = self.deserialize_json(payload_str, {})
        entity_ids = self.deserialize_json(entity_ids_str, [])
        metadata = self.deserialize_json(metadata_str, {})

        # Deep clean: Recursively remove any sqlite3.Row objects
        def clean_dict(d):
            """Recursively clean dict to remove sqlite3.Row objects"""
            if not isinstance(d, dict):
                return {}
            cleaned = {}
            for key, value in d.items():
                # Check if value is sqlite3.Row
                if hasattr(value, '__class__'):
                    class_name = value.__class__.__name__
                    module_name = getattr(value.__class__, '__module__', '')
                    if class_name == 'Row' or 'sqlite3' in module_name:
                        # Skip sqlite3.Row values
                        continue
                    # If value is a dict, recursively clean it
                    if isinstance(value, dict):
                        value = clean_dict(value)
                cleaned[key] = value
            return cleaned

        # Ensure payload is a dict and clean it
        if not isinstance(payload, dict):
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"deserialize_json returned non-dict payload: type={type(payload)}, value={payload}")
            payload = {}
        else:
            payload = clean_dict(payload)

        # Ensure entity_ids is a list
        if not isinstance(entity_ids, list):
            entity_ids = []

        # Ensure metadata is a dict and clean it
        if not isinstance(metadata, dict):
            metadata = {}
        else:
            metadata = clean_dict(metadata)

        try:
            return MindEvent(
                id=str(row['id']),
                timestamp=self.from_isoformat(row['timestamp']),
                actor=EventActor(row['actor']),
                channel=str(row['channel']),
                profile_id=str(row['profile_id']),
                project_id=str(row['project_id']) if row['project_id'] else None,
                workspace_id=str(row['workspace_id']) if row['workspace_id'] else None,
                thread_id=str(row['thread_id']) if row.get('thread_id') else None,
                event_type=EventType(row['event_type']),
                payload=payload,
                entity_ids=entity_ids,
                metadata=metadata
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Error creating MindEvent: {e}")
            logger.error(f"Payload type: {type(payload)}, Payload: {payload}")
            logger.error(f"Entity IDs type: {type(entity_ids)}, Entity IDs: {entity_ids}")
            logger.error(f"Metadata type: {type(metadata)}, Metadata: {metadata}")
            import traceback
            logger.error(traceback.format_exc())
            raise
