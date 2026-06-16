"""
Read operations for the legacy SQLite EventsStore.
"""

from datetime import datetime
from typing import List, Optional

from ...models.mindscape import MindEvent, EventType


class EventsStoreQueryMixin:
    """Query methods for EventsStore."""

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
            return self._rows_to_events(rows, "to event in get_events (base)")

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
            return self._rows_to_events(rows, "to event in get_events")

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
            return self._rows_to_events(rows, "to event in get_events_by_workspace")

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
            return self._rows_to_events(rows, "to event in get_events_by_thread")

    def get_events_by_meeting_session(
        self,
        meeting_session_id: str,
        workspace_id: Optional[str] = None,
        limit: int = 500,
    ) -> List[MindEvent]:
        """
        Get all events for a specific meeting session.

        Accepts metadata.meeting_session_id, payload.meeting_session_id, or
        thread_id for meeting graph turns created before explicit stamping.
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = "SELECT * FROM mind_events WHERE thread_id = ?"
            params = [meeting_session_id]

            if workspace_id:
                query += " AND workspace_id = ?"
                params.append(workspace_id)

            query += " ORDER BY timestamp ASC, id ASC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            if not rows:
                query = (
                    "SELECT * FROM mind_events "
                    "WHERE ("
                    "json_extract(metadata, '$.meeting_session_id') = ? "
                    "OR json_extract(payload, '$.meeting_session_id') = ?"
                    ")"
                )
                params = [meeting_session_id, meeting_session_id]

                if workspace_id:
                    query += " AND workspace_id = ?"
                    params.append(workspace_id)

                query += " ORDER BY timestamp ASC, id ASC LIMIT ?"
                params.append(limit)

                cursor.execute(query, params)
                rows = cursor.fetchall()

            return self._rows_to_events(rows, "in get_events_by_meeting_session")

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

            query += ' ORDER BY timestamp DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return self._rows_to_events(rows, "to event in get_timeline")
