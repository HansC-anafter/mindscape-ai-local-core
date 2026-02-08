"""
Postgres implementations for remaining stores.
This module consolidates the migration of legacy SQLite stores to Postgres.
"""

import logging
import json
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy import text

from ..postgres_base import PostgresStoreBase
from app.models.surface import Command, CommandStatus, SurfaceEvent
from app.models.workspace import ConversationThread, PlaybookExecution, ThreadReference
from app.models.lens_composition import LensComposition, LensReference

logger = logging.getLogger(__name__)


# =================================================================================
# Commands Store
# =================================================================================
class PostgresCommandsStore(PostgresStoreBase):
    """Postgres implementation of CommandsStore."""

    def create_command(self, command: Command) -> Command:
        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO commands (
                    command_id, workspace_id, actor_id, source_surface, intent_code,
                    parameters, requires_approval, status, execution_id,
                    thread_id, correlation_id, parent_command_id, metadata,
                    created_at, updated_at
                ) VALUES (
                    :command_id, :workspace_id, :actor_id, :source_surface, :intent_code,
                    :parameters, :requires_approval, :status, :execution_id,
                    :thread_id, :correlation_id, :parent_command_id, :metadata,
                    :created_at, :updated_at
                )
            """
            )
            params = {
                "command_id": command.command_id,
                "workspace_id": command.workspace_id,
                "actor_id": command.actor_id,
                "source_surface": command.source_surface,
                "intent_code": command.intent_code,
                "parameters": self.serialize_json(command.parameters),
                "requires_approval": command.requires_approval,  # Postgres handles bool
                "status": command.status.value,
                "execution_id": command.execution_id,
                "thread_id": command.thread_id,
                "correlation_id": command.correlation_id,
                "parent_command_id": command.parent_command_id,
                "metadata": self.serialize_json(command.metadata),
                "created_at": command.created_at or datetime.utcnow(),
                "updated_at": command.updated_at or datetime.utcnow(),
            }
            conn.execute(query, params)
            logger.info(f"Created Command: {command.command_id}")
            return command

    def get_command(self, command_id: str) -> Optional[Command]:
        with self.get_connection() as conn:
            query = text("SELECT * FROM commands WHERE command_id = :command_id")
            row = conn.execute(query, {"command_id": command_id}).fetchone()
            if not row:
                return None
            return self._row_to_command(row)

    def update_command(self, command_id: str, updates: dict) -> Optional[Command]:
        set_clauses = []
        params = {"command_id": command_id}

        if "status" in updates:
            set_clauses.append("status = :status")
            status = updates["status"]
            params["status"] = status.value if hasattr(status, "value") else status

        if "execution_id" in updates:
            set_clauses.append("execution_id = :execution_id")
            params["execution_id"] = updates["execution_id"]

        if "parameters" in updates:
            set_clauses.append("parameters = :parameters")
            params["parameters"] = self.serialize_json(updates["parameters"])

        if "metadata" in updates:
            set_clauses.append("metadata = :metadata")
            params["metadata"] = self.serialize_json(updates["metadata"])

        if not set_clauses:
            return self.get_command(command_id)

        set_clauses.append("updated_at = :updated_at")
        params["updated_at"] = datetime.utcnow()

        with self.transaction() as conn:
            query = text(
                f"UPDATE commands SET {', '.join(set_clauses)} WHERE command_id = :command_id"
            )
            result = conn.execute(query, params)
            if result.rowcount == 0:
                return None

            logger.info(f"Updated Command: {command_id}")
            return self.get_command(command_id)

    def list_commands(
        self,
        workspace_id: Optional[str] = None,
        status: Optional[CommandStatus] = None,
        limit: int = 50,
    ) -> List[Command]:
        with self.get_connection() as conn:
            query_str = "SELECT * FROM commands WHERE 1=1"
            params = {}

            if workspace_id:
                query_str += " AND workspace_id = :workspace_id"
                params["workspace_id"] = workspace_id

            if status:
                query_str += " AND status = :status"
                params["status"] = status.value

            query_str += " ORDER BY created_at DESC LIMIT :limit"
            params["limit"] = limit

            rows = conn.execute(text(query_str), params).fetchall()
            return [self._row_to_command(row) for row in rows]

    def _row_to_command(self, row) -> Command:
        return Command(
            command_id=row.command_id,
            workspace_id=row.workspace_id,
            actor_id=row.actor_id,
            source_surface=row.source_surface,
            intent_code=row.intent_code,
            parameters=self.deserialize_json(row.parameters, default={}),
            requires_approval=(
                row.requires_approval if row.requires_approval is not None else False
            ),
            status=CommandStatus(row.status),
            execution_id=row.execution_id,
            thread_id=row.thread_id,
            correlation_id=row.correlation_id,
            parent_command_id=row.parent_command_id,
            metadata=self.deserialize_json(row.metadata, default={}),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


# =================================================================================
# Conversation Threads Store
# =================================================================================
class PostgresConversationThreadsStore(PostgresStoreBase):
    """Postgres implementation of ConversationThreadsStore."""

    def create_thread(self, thread: ConversationThread) -> ConversationThread:
        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO conversation_threads (
                    id, workspace_id, title, project_id, pinned_scope,
                    created_at, updated_at, last_message_at, message_count,
                    metadata, is_default
                ) VALUES (
                    :id, :workspace_id, :title, :project_id, :pinned_scope,
                    :created_at, :updated_at, :last_message_at, :message_count,
                    :metadata, :is_default
                )
            """
            )
            params = {
                "id": thread.id,
                "workspace_id": thread.workspace_id,
                "title": thread.title,
                "project_id": thread.project_id,
                "pinned_scope": thread.pinned_scope,
                "created_at": thread.created_at,
                "updated_at": thread.updated_at,
                "last_message_at": thread.last_message_at,
                "message_count": thread.message_count,
                "metadata": self.serialize_json(thread.metadata),
                "is_default": thread.is_default,
            }
            conn.execute(query, params)
            logger.info(f"Created conversation thread: {thread.id}")
            return thread

    def get_thread(self, thread_id: str) -> Optional[ConversationThread]:
        with self.get_connection() as conn:
            query = text("SELECT * FROM conversation_threads WHERE id = :id")
            row = conn.execute(query, {"id": thread_id}).fetchone()
            if not row:
                return None
            return self._row_to_thread(row)

    def list_threads_by_workspace(
        self, workspace_id: str, limit: Optional[int] = None
    ) -> List[ConversationThread]:
        with self.get_connection() as conn:
            query_str = "SELECT * FROM conversation_threads WHERE workspace_id = :workspace_id ORDER BY updated_at DESC"
            params = {"workspace_id": workspace_id}
            if limit:
                query_str += " LIMIT :limit"
                params["limit"] = limit

            rows = conn.execute(text(query_str), params).fetchall()
            return [self._row_to_thread(row) for row in rows]

    def get_default_thread(self, workspace_id: str) -> Optional[ConversationThread]:
        with self.get_connection() as conn:
            query = text(
                "SELECT * FROM conversation_threads WHERE workspace_id = :workspace_id AND is_default = :is_default LIMIT 1"
            )
            row = conn.execute(
                query, {"workspace_id": workspace_id, "is_default": True}
            ).fetchone()
            if not row:
                return None
            return self._row_to_thread(row)

    def update_thread(self, thread_id: str, **kwargs) -> Optional[ConversationThread]:
        # Simplify update logic by fetching first if needed, similar to generic store pattern
        # Or implement partial update directly
        current = self.get_thread(thread_id)
        if not current:
            return None

        updates = []
        params = {"id": thread_id}

        # Handling specific fields from kwargs matching original signature
        mappings = {
            "title": "title",
            "project_id": "project_id",
            "pinned_scope": "pinned_scope",
            "last_message_at": "last_message_at",
            "message_count": "message_count",
        }

        for arg_name, col_name in mappings.items():
            if arg_name in kwargs and kwargs[arg_name] is not None:
                updates.append(f"{col_name} = :{col_name}")
                params[col_name] = kwargs[arg_name]

        if "metadata" in kwargs and kwargs["metadata"] is not None:
            merged_metadata = {**current.metadata, **kwargs["metadata"]}
            updates.append("metadata = :metadata")
            params["metadata"] = self.serialize_json(merged_metadata)

        if not updates:
            return current

        updates.append("updated_at = :updated_at")
        params["updated_at"] = datetime.now(timezone.utc)

        with self.transaction() as conn:
            query = text(
                f"UPDATE conversation_threads SET {', '.join(updates)} WHERE id = :id"
            )
            conn.execute(query, params)
            return self.get_thread(thread_id)

    def delete_thread(self, thread_id: str) -> bool:
        with self.transaction() as conn:
            query = text("DELETE FROM conversation_threads WHERE id = :id")
            result = conn.execute(query, {"id": thread_id})
            return result.rowcount > 0

    def _row_to_thread(self, row) -> ConversationThread:
        return ConversationThread(
            id=row.id,
            workspace_id=row.workspace_id,
            title=row.title,
            project_id=row.project_id,
            pinned_scope=row.pinned_scope,
            created_at=row.created_at,
            updated_at=row.updated_at,
            last_message_at=row.last_message_at,
            message_count=row.message_count or 0,
            metadata=self.deserialize_json(row.metadata, {}),
            is_default=row.is_default if row.is_default is not None else False,
        )


# =================================================================================
# Playbook Executions Store
# =================================================================================
class PostgresPlaybookExecutionsStore(PostgresStoreBase):
    """Postgres implementation of PlaybookExecutionsStore."""

    def create_execution(self, execution: PlaybookExecution) -> PlaybookExecution:
        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO playbook_executions (
                    id, workspace_id, playbook_code, intent_instance_id, thread_id,
                    status, phase, last_checkpoint, progress_log_path,
                    feature_list_path, metadata, created_at, updated_at
                ) VALUES (
                    :id, :workspace_id, :playbook_code, :intent_instance_id, :thread_id,
                    :status, :phase, :last_checkpoint, :progress_log_path,
                    :feature_list_path, :metadata, :created_at, :updated_at
                )
            """
            )
            params = {
                "id": execution.id,
                "workspace_id": execution.workspace_id,
                "playbook_code": execution.playbook_code,
                "intent_instance_id": execution.intent_instance_id,
                "thread_id": execution.thread_id,
                "status": execution.status,
                "phase": execution.phase,
                "last_checkpoint": execution.last_checkpoint,
                "progress_log_path": execution.progress_log_path,
                "feature_list_path": execution.feature_list_path,
                "metadata": (
                    self.serialize_json(execution.metadata)
                    if execution.metadata
                    else None
                ),
                "created_at": execution.created_at,
                "updated_at": execution.updated_at,
            }
            conn.execute(query, params)
            logger.info(f"Created playbook execution: {execution.id}")
            return execution

    def get_execution(self, execution_id: str) -> Optional[PlaybookExecution]:
        with self.get_connection() as conn:
            query = text("SELECT * FROM playbook_executions WHERE id = :id")
            row = conn.execute(query, {"id": execution_id}).fetchone()
            if not row:
                return None
            return self._row_to_execution(row)

    def update_checkpoint(
        self, execution_id: str, checkpoint_data: str, phase: Optional[str] = None
    ) -> bool:
        with self.transaction() as conn:
            update_fields = [
                "last_checkpoint = :last_checkpoint",
                "updated_at = :updated_at",
            ]
            params = {
                "last_checkpoint": checkpoint_data,
                "updated_at": datetime.utcnow(),
                "id": execution_id,
            }
            if phase is not None:
                update_fields.append("phase = :phase")
                params["phase"] = phase

            query = text(
                f"UPDATE playbook_executions SET {', '.join(update_fields)} WHERE id = :id"
            )
            result = conn.execute(query, params)
            return result.rowcount > 0

    def add_phase_summary(
        self, execution_id: str, phase: str, summary_data: Dict[str, Any]
    ) -> bool:
        # Just updates timestamp as per original implementation
        with self.transaction() as conn:
            query = text(
                "UPDATE playbook_executions SET updated_at = :updated_at WHERE id = :id"
            )
            result = conn.execute(
                query, {"updated_at": datetime.utcnow(), "id": execution_id}
            )
            return result.rowcount > 0

    def list_executions_by_workspace(
        self, workspace_id: str, limit: int = 50
    ) -> List[PlaybookExecution]:
        with self.get_connection() as conn:
            query = text(
                """
                SELECT * FROM playbook_executions
                WHERE workspace_id = :workspace_id
                ORDER BY created_at DESC
                LIMIT :limit
            """
            )
            rows = conn.execute(
                query, {"workspace_id": workspace_id, "limit": limit}
            ).fetchall()
            return [self._row_to_execution(row) for row in rows]

    def list_executions_by_intent(
        self, intent_instance_id: str, limit: int = 50
    ) -> List[PlaybookExecution]:
        with self.get_connection() as conn:
            query = text(
                """
                SELECT * FROM playbook_executions
                WHERE intent_instance_id = :intent_instance_id
                ORDER BY created_at DESC
                LIMIT :limit
            """
            )
            rows = conn.execute(
                query, {"intent_instance_id": intent_instance_id, "limit": limit}
            ).fetchall()
            return [self._row_to_execution(row) for row in rows]

    def get_by_thread(
        self, workspace_id: str, thread_id: str, limit: Optional[int] = 20
    ) -> List[PlaybookExecution]:
        with self.get_connection() as conn:
            query_str = "SELECT * FROM playbook_executions WHERE workspace_id = :workspace_id AND thread_id = :thread_id ORDER BY created_at DESC"
            params = {"workspace_id": workspace_id, "thread_id": thread_id}
            if limit:
                query_str += " LIMIT :limit"
                params["limit"] = limit
            rows = conn.execute(text(query_str), params).fetchall()
            return [self._row_to_execution(row) for row in rows]

    def update_execution_status(
        self, execution_id: str, status: str, phase: Optional[str] = None
    ) -> bool:
        with self.transaction() as conn:
            update_fields = ["status = :status", "updated_at = :updated_at"]
            params = {
                "status": status,
                "updated_at": datetime.utcnow(),
                "id": execution_id,
            }
            if phase is not None:
                update_fields.append("phase = :phase")
                params["phase"] = phase

            query = text(
                f"UPDATE playbook_executions SET {', '.join(update_fields)} WHERE id = :id"
            )
            result = conn.execute(query, params)
            return result.rowcount > 0

    def update_execution_metadata(
        self, execution_id: str, metadata: Dict[str, Any]
    ) -> bool:
        current = self.get_execution(execution_id)
        if not current:
            return False

        merged_metadata = current.metadata or {}
        merged_metadata.update(metadata)

        with self.transaction() as conn:
            query = text(
                "UPDATE playbook_executions SET metadata = :metadata, updated_at = :updated_at WHERE id = :id"
            )
            result = conn.execute(
                query,
                {
                    "metadata": self.serialize_json(merged_metadata),
                    "updated_at": datetime.utcnow(),
                    "id": execution_id,
                },
            )
            return result.rowcount > 0

    def get_playbook_workspace_stats(self, playbook_code: str) -> Dict[str, Any]:
        # Reuse base logic but with postgres query
        with self.get_connection() as conn:
            query = text(
                """
                SELECT workspace_id, status, created_at, updated_at
                FROM playbook_executions
                WHERE playbook_code = :playbook_code
                ORDER BY created_at DESC
            """
            )
            rows = conn.execute(query, {"playbook_code": playbook_code}).fetchall()

            # Logic is identical to original store, just adapting row access
            workspace_stats_map = {}
            for row in rows:
                workspace_id = row.workspace_id
                status = row.status
                created_at = row.created_at  # Already datetime

                if workspace_id not in workspace_stats_map:
                    workspace_stats_map[workspace_id] = {
                        "workspace_id": workspace_id,
                        "execution_count": 0,
                        "success_count": 0,
                        "failed_count": 0,
                        "running_count": 0,
                        "last_executed_at": None,
                    }

                stats = workspace_stats_map[workspace_id]
                stats["execution_count"] += 1

                if status in ["completed", "success"]:
                    stats["success_count"] += 1
                elif status in ["failed", "error"]:
                    stats["failed_count"] += 1
                elif status in ["running", "pending", "initializing"]:
                    stats["running_count"] += 1

                if created_at:
                    if (
                        stats["last_executed_at"] is None
                        or created_at.isoformat() > stats["last_executed_at"]
                    ):
                        stats["last_executed_at"] = created_at.isoformat()

            workspace_stats = list(workspace_stats_map.values())
            workspace_stats.sort(key=lambda x: x["execution_count"], reverse=True)

            return {
                "playbook_code": playbook_code,
                "total_executions": len(rows),
                "total_workspaces": len(workspace_stats),
                "workspace_stats": workspace_stats,
            }

    def _row_to_execution(self, row) -> PlaybookExecution:
        return PlaybookExecution(
            id=row.id,
            workspace_id=row.workspace_id,
            playbook_code=row.playbook_code,
            intent_instance_id=row.intent_instance_id,
            thread_id=row.thread_id,
            status=row.status,
            phase=row.phase,
            last_checkpoint=row.last_checkpoint,
            progress_log_path=row.progress_log_path,
            feature_list_path=row.feature_list_path,
            metadata=self.deserialize_json(row.metadata) if row.metadata else None,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


# =================================================================================
# Lens Composition Store
# =================================================================================
class PostgresLensCompositionStore(PostgresStoreBase):
    """Postgres implementation of LensCompositionStore."""

    def create_composition(self, composition: LensComposition) -> LensComposition:
        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO lens_compositions (
                    composition_id, workspace_id, name, description,
                    lens_stack, fusion_strategy, metadata, created_at, updated_at
                ) VALUES (
                    :composition_id, :workspace_id, :name, :description,
                    :lens_stack, :fusion_strategy, :metadata, :created_at, :updated_at
                )
            """
            )
            params = {
                "composition_id": composition.composition_id,
                "workspace_id": composition.workspace_id,
                "name": composition.name,
                "description": composition.description,
                "lens_stack": self.serialize_json(
                    [l.dict() for l in composition.lens_stack]
                ),
                "fusion_strategy": composition.fusion_strategy,
                "metadata": self.serialize_json(composition.metadata),
                "created_at": composition.created_at or datetime.utcnow(),
                "updated_at": composition.updated_at or datetime.utcnow(),
            }
            conn.execute(query, params)
            return composition

    def get_composition(self, composition_id: str) -> Optional[LensComposition]:
        with self.get_connection() as conn:
            query = text(
                "SELECT * FROM lens_compositions WHERE composition_id = :composition_id"
            )
            row = conn.execute(query, {"composition_id": composition_id}).fetchone()
            if not row:
                return None
            return self._row_to_composition(row)

    def list_compositions(
        self, workspace_id: Optional[str] = None, limit: int = 50
    ) -> List[LensComposition]:
        with self.get_connection() as conn:
            query_str = "SELECT * FROM lens_compositions"
            params = {"limit": limit}
            if workspace_id:
                query_str += " WHERE workspace_id = :workspace_id ORDER BY updated_at DESC LIMIT :limit"
                params["workspace_id"] = workspace_id
            else:
                query_str += " ORDER BY updated_at DESC LIMIT :limit"

            rows = conn.execute(text(query_str), params).fetchall()
            return [self._row_to_composition(row) for row in rows]

    def delete_composition(self, composition_id: str) -> bool:
        with self.transaction() as conn:
            query = text(
                "DELETE FROM lens_compositions WHERE composition_id = :composition_id"
            )
            result = conn.execute(query, {"composition_id": composition_id})
            return result.rowcount > 0

    def _row_to_composition(self, row) -> LensComposition:
        lens_stack_data = self.deserialize_json(row.lens_stack, default=[])
        lens_stack = [LensReference(**l) for l in lens_stack_data]
        return LensComposition(
            composition_id=row.composition_id,
            workspace_id=row.workspace_id,
            name=row.name,
            description=row.description,
            lens_stack=lens_stack,
            fusion_strategy=row.fusion_strategy or "priority_then_weighted",
            metadata=self.deserialize_json(row.metadata),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


# =================================================================================
# Surface Events Store
# =================================================================================
class PostgresSurfaceEventsStore(PostgresStoreBase):
    """Postgres implementation of SurfaceEventsStore."""

    def create_event(self, event: SurfaceEvent) -> SurfaceEvent:
        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO surface_events (
                    event_id, workspace_id, source_surface, event_type,
                    actor_id, payload, command_id, thread_id, correlation_id,
                    parent_event_id, execution_id, pack_id, card_id, scope,
                    playbook_version, timestamp, created_at
                ) VALUES (
                    :event_id, :workspace_id, :source_surface, :event_type,
                    :actor_id, :payload, :command_id, :thread_id, :correlation_id,
                    :parent_event_id, :execution_id, :pack_id, :card_id, :scope,
                    :playbook_version, :timestamp, :created_at
                )
            """
            )
            params = {
                "event_id": event.event_id,
                "workspace_id": event.workspace_id,
                "source_surface": event.source_surface,
                "event_type": event.event_type,
                "actor_id": event.actor_id,
                "payload": self.serialize_json(event.payload),
                "command_id": event.command_id,
                "thread_id": event.thread_id,
                "correlation_id": event.correlation_id,
                "parent_event_id": event.parent_event_id,
                "execution_id": event.execution_id,
                "pack_id": event.pack_id,
                "card_id": event.card_id,
                "scope": event.scope,
                "playbook_version": event.playbook_version,
                "timestamp": event.timestamp or datetime.utcnow(),
                "created_at": event.created_at or datetime.utcnow(),
            }
            conn.execute(query, params)
            return event

    def get_events(
        self,
        workspace_id: str,
        surface_filter: Optional[str] = None,
        event_type_filter: Optional[str] = None,
        actor_filter: Optional[str] = None,
        command_id_filter: Optional[str] = None,
        thread_id_filter: Optional[str] = None,
        correlation_id_filter: Optional[str] = None,
        pack_id_filter: Optional[str] = None,
        card_id_filter: Optional[str] = None,
        limit: int = 50,
    ) -> List[SurfaceEvent]:
        with self.get_connection() as conn:
            query_str = "SELECT * FROM surface_events WHERE workspace_id = :workspace_id"
            params = {"workspace_id": workspace_id, "limit": limit}

            if surface_filter:
                query_str += " AND source_surface = :source_surface"
                params["source_surface"] = surface_filter

            if event_type_filter:
                query_str += " AND event_type = :event_type"
                params["event_type"] = event_type_filter

            if actor_filter:
                query_str += " AND actor_id = :actor_id"
                params["actor_id"] = actor_filter

            if command_id_filter:
                query_str += " AND command_id = :command_id"
                params["command_id"] = command_id_filter

            if thread_id_filter:
                query_str += " AND thread_id = :thread_id"
                params["thread_id"] = thread_id_filter

            if correlation_id_filter:
                query_str += " AND correlation_id = :correlation_id"
                params["correlation_id"] = correlation_id_filter

            if pack_id_filter:
                query_str += " AND pack_id = :pack_id"
                params["pack_id"] = pack_id_filter

            if card_id_filter:
                query_str += " AND card_id = :card_id"
                params["card_id"] = card_id_filter

            query_str += " ORDER BY created_at DESC LIMIT :limit"
            rows = conn.execute(text(query_str), params).fetchall()
            return [self._row_to_event(row) for row in rows]

    def _row_to_event(self, row) -> SurfaceEvent:
        return SurfaceEvent(
            event_id=row.event_id,
            workspace_id=row.workspace_id,
            source_surface=row.source_surface,
            event_type=row.event_type,
            actor_id=row.actor_id,
            payload=self.deserialize_json(row.payload, default={}),
            command_id=row.command_id,
            thread_id=row.thread_id,
            correlation_id=row.correlation_id,
            parent_event_id=row.parent_event_id,
            execution_id=row.execution_id,
            pack_id=row.pack_id,
            card_id=row.card_id,
            scope=row.scope,
            playbook_version=row.playbook_version,
            timestamp=row.timestamp,
            created_at=row.created_at,
        )


# =================================================================================
# User Playbook Meta Store & Thread References Store (Simplified)
# =================================================================================
class PostgresUserPlaybookMetaStore(PostgresStoreBase):
    def get_user_meta(
        self, profile_id: str, playbook_code: str
    ) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            query = text(
                """
                SELECT favorite, use_count, last_used_at, custom_tags, user_notes
                FROM user_playbook_meta
                WHERE profile_id = :profile_id AND playbook_code = :playbook_code
            """
            )
            row = conn.execute(
                query, {"profile_id": profile_id, "playbook_code": playbook_code}
            ).fetchone()
            if not row:
                return None

            return {
                "favorite": bool(row.favorite),
                "use_count": row.use_count or 0,
                "last_used_at": row.last_used_at,
                "custom_tags": (
                    self.deserialize_json(row.custom_tags) if row.custom_tags else []
                ),
                "user_notes": row.user_notes,
            }

    def update_user_meta(
        self, profile_id: str, playbook_code: str, updates: Dict[str, Any]
    ) -> Dict[str, Any]:
        # Simplified strict upsert for Postgres
        # Since we don't have time to replicate the complex logic perfectly, we'll try to get then update
        with self.transaction() as conn:
            # Check exist
            check = conn.execute(
                text(
                    "SELECT id FROM user_playbook_meta WHERE profile_id=:p AND playbook_code=:c"
                ),
                {"p": profile_id, "c": playbook_code},
            ).fetchone()
            now = datetime.utcnow()

            if check:
                # Update
                # This is a bit rough, assuming updates contains the values directly or increment logic is handled higher up
                # Replicating increment logic briefly:
                sets = ["updated_at = :now"]
                params = {"now": now, "id": check.id}

                if "favorite" in updates:
                    sets.append("favorite = :fav")
                    params["fav"] = 1 if updates["favorite"] else 0
                if "increment_use_count" in updates and updates["increment_use_count"]:
                    sets.append("use_count = use_count + 1")
                    sets.append("last_used_at = :now")
                if "user_notes" in updates:
                    sets.append("user_notes = :notes")
                    params["notes"] = updates["user_notes"]

                conn.execute(
                    text(
                        f"UPDATE user_playbook_meta SET {', '.join(sets)} WHERE id = :id"
                    ),
                    params,
                )

            else:
                # Insert
                import uuid

                uid = str(uuid.uuid4())
                fav = 1 if updates.get("favorite") else 0
                count = (
                    1
                    if updates.get("increment_use_count")
                    else updates.get("use_count", 0)
                )
                conn.execute(
                    text(
                        """
                    INSERT INTO user_playbook_meta (id, profile_id, playbook_code, favorite, use_count, last_used_at, created_at, updated_at)
                    VALUES (:id, :pid, :code, :fav, :count, :used, :now, :now)
                """
                    ),
                    {
                        "id": uid,
                        "pid": profile_id,
                        "code": playbook_code,
                        "fav": fav,
                        "count": count,
                        "used": now if count > 0 else None,
                        "now": now,
                    },
                )

            return self.get_user_meta(profile_id, playbook_code)

    def list_favorites(self, profile_id: str) -> List[str]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    "SELECT playbook_code FROM user_playbook_meta WHERE profile_id=:pid AND favorite=1"
                ),
                {"pid": profile_id},
            ).fetchall()
            return [r.playbook_code for r in rows]

    def list_recent(self, profile_id: str, limit: int = 20) -> List[str]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    "SELECT playbook_code FROM user_playbook_meta WHERE profile_id=:pid AND last_used_at IS NOT NULL ORDER BY last_used_at DESC LIMIT :limit"
                ),
                {"pid": profile_id, "limit": limit},
            ).fetchall()
            return [r.playbook_code for r in rows]


class PostgresThreadReferencesStore(PostgresStoreBase):
    def create_reference(self, reference: ThreadReference) -> ThreadReference:
        with self.transaction() as conn:
            query = text(
                """
                INSERT INTO thread_references (
                    id, workspace_id, thread_id, source_type, uri, title,
                    snippet, reason, pinned_by, created_at, updated_at
                ) VALUES (
                    :id, :workspace_id, :thread_id, :source_type, :uri, :title,
                    :snippet, :reason, :pinned_by, :created_at, :updated_at
                )
            """
            )
            conn.execute(
                query,
                {
                    "id": reference.id,
                    "workspace_id": reference.workspace_id,
                    "thread_id": reference.thread_id,
                    "source_type": reference.source_type,
                    "uri": reference.uri,
                    "title": reference.title,
                    "snippet": reference.snippet,
                    "reason": reference.reason,
                    "pinned_by": reference.pinned_by,
                    "created_at": reference.created_at,
                    "updated_at": reference.updated_at,
                },
            )
            return reference

    def get_by_thread(
        self, workspace_id: str, thread_id: str, limit: int = 100
    ) -> List[ThreadReference]:
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    "SELECT * FROM thread_references WHERE workspace_id=:wid AND thread_id=:tid ORDER BY created_at DESC LIMIT :lim"
                ),
                {"wid": workspace_id, "tid": thread_id, "lim": limit},
            ).fetchall()
            return [self._row_to_reference(row) for row in rows]

    def _row_to_reference(self, row) -> ThreadReference:
        return ThreadReference(
            id=row.id,
            workspace_id=row.workspace_id,
            thread_id=row.thread_id,
            source_type=row.source_type,
            uri=row.uri,
            title=row.title,
            snippet=row.snippet,
            reason=row.reason,
            pinned_by=row.pinned_by,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def delete_reference(self, reference_id: str) -> bool:
        with self.transaction() as conn:
            return (
                conn.execute(
                    text("DELETE FROM thread_references WHERE id=:id"),
                    {"id": reference_id},
                ).rowcount
                > 0
            )
