"""Commands store for data persistence."""
import logging
from datetime import datetime
from typing import List, Optional

from .base import StoreBase
from ...models.surface import Command, CommandStatus

logger = logging.getLogger(__name__)


class CommandsStore(StoreBase):
    """Store for managing Commands."""

    def create_command(self, command: Command) -> Command:
        """
        Create a new command.

        Args:
            command: Command to create

        Returns:
            Created command
        """
        with self.transaction() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO commands (
                    command_id, workspace_id, actor_id, source_surface, intent_code,
                    parameters, requires_approval, status, execution_id,
                    thread_id, correlation_id, parent_command_id, metadata,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                command.command_id,
                command.workspace_id,
                command.actor_id,
                command.source_surface,
                command.intent_code,
                self.serialize_json(command.parameters),
                1 if command.requires_approval else 0,
                command.status.value,
                command.execution_id,
                command.thread_id,
                command.correlation_id,
                command.parent_command_id,
                self.serialize_json(command.metadata),
                self.to_isoformat(command.created_at or datetime.utcnow()),
                self.to_isoformat(command.updated_at or datetime.utcnow())
            ))
            logger.info(f"Created Command: {command.command_id}")
            return command

    def get_command(self, command_id: str) -> Optional[Command]:
        """
        Get command by ID.

        Args:
            command_id: Command ID

        Returns:
            Command or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM commands WHERE command_id = ?', (command_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_command(row)

    def update_command(
        self,
        command_id: str,
        updates: dict
    ) -> Optional[Command]:
        """
        Update command.

        Args:
            command_id: Command ID
            updates: Update fields

        Returns:
            Updated command or None if not found
        """
        with self.transaction() as conn:
            cursor = conn.cursor()

            set_clauses = []
            params = []

            if 'status' in updates:
                set_clauses.append('status = ?')
                status = updates['status']
                params.append(status.value if hasattr(status, 'value') else status)

            if 'execution_id' in updates:
                set_clauses.append('execution_id = ?')
                params.append(updates['execution_id'])

            if 'parameters' in updates:
                set_clauses.append('parameters = ?')
                params.append(self.serialize_json(updates['parameters']))

            if 'metadata' in updates:
                set_clauses.append('metadata = ?')
                params.append(self.serialize_json(updates['metadata']))

            if not set_clauses:
                return self.get_command(command_id)

            set_clauses.append('updated_at = ?')
            params.append(self.to_isoformat(datetime.utcnow()))
            params.append(command_id)

            cursor.execute(
                f'UPDATE commands SET {", ".join(set_clauses)} WHERE command_id = ?',
                params
            )

            if cursor.rowcount == 0:
                return None

            logger.info(f"Updated Command: {command_id}")
            return self.get_command(command_id)

    def list_commands(
        self,
        workspace_id: Optional[str] = None,
        status: Optional[CommandStatus] = None,
        limit: int = 50
    ) -> List[Command]:
        """
        List commands with filters.

        Args:
            workspace_id: Optional workspace filter
            status: Optional status filter
            limit: Maximum number of results

        Returns:
            List of commands
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            query = 'SELECT * FROM commands WHERE 1=1'
            params = []

            if workspace_id:
                query += ' AND workspace_id = ?'
                params.append(workspace_id)

            if status:
                query += ' AND status = ?'
                params.append(status.value)

            query += ' ORDER BY created_at DESC LIMIT ?'
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._row_to_command(row) for row in rows]

    def _row_to_command(self, row) -> Command:
        """Convert database row to Command."""
        return Command(
            command_id=row['command_id'],
            workspace_id=row['workspace_id'],
            actor_id=row['actor_id'],
            source_surface=row['source_surface'],
            intent_code=row['intent_code'],
            parameters=self.deserialize_json(row['parameters'], default={}),
            requires_approval=bool(row['requires_approval']),
            status=CommandStatus(row['status']),
            execution_id=row['execution_id'],
            thread_id=row['thread_id'],
            correlation_id=row['correlation_id'],
            parent_command_id=row['parent_command_id'],
            metadata=self.deserialize_json(row['metadata'], default={}),
            created_at=self.from_isoformat(row['created_at']),
            updated_at=self.from_isoformat(row['updated_at'])
        )


