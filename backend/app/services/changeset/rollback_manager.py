"""
Rollback Manager

Manages rollback points for change sets.
"""

import logging
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime

from backend.app.core.ir.changeset import ChangeSetIR, ChangeSetStatus
from backend.app.services.sandbox.sandbox_manager import SandboxManager
from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


class RollbackPoint:
    """Rollback point for a change set"""

    def __init__(
        self,
        rollback_point_id: str,
        changeset_id: str,
        workspace_id: str,
        sandbox_id: str,
        snapshot_data: Dict[str, Any],
        created_at: Optional[datetime] = None
    ):
        self.rollback_point_id = rollback_point_id
        self.changeset_id = changeset_id
        self.workspace_id = workspace_id
        self.sandbox_id = sandbox_id
        self.snapshot_data = snapshot_data
        self.created_at = created_at or datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "rollback_point_id": self.rollback_point_id,
            "changeset_id": self.changeset_id,
            "workspace_id": self.workspace_id,
            "sandbox_id": self.sandbox_id,
            "snapshot_data": self.snapshot_data,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RollbackPoint":
        """Create RollbackPoint from dictionary"""
        created_at = datetime.fromisoformat(data["created_at"]) if isinstance(data.get("created_at"), str) else data.get("created_at", datetime.utcnow())
        return cls(
            rollback_point_id=data["rollback_point_id"],
            changeset_id=data["changeset_id"],
            workspace_id=data["workspace_id"],
            sandbox_id=data["sandbox_id"],
            snapshot_data=data["snapshot_data"],
            created_at=created_at,
        )


class RollbackManager:
    """
    Manages rollback points for change sets
    """

    def __init__(self, store: Optional[MindscapeStore] = None):
        """
        Initialize RollbackManager

        Args:
            store: MindscapeStore instance (will create if not provided)
        """
        if store is None:
            from backend.app.services.mindscape_store import MindscapeStore
            store = MindscapeStore()
        self.store = store
        self.sandbox_manager = SandboxManager(store)
        self._rollback_points: Dict[str, RollbackPoint] = {}

    async def create_rollback_point(
        self,
        changeset: ChangeSetIR,
        sandbox_id: str
    ) -> RollbackPoint:
        """
        Create rollback point for a change set

        Args:
            changeset: ChangeSetIR instance
            sandbox_id: Sandbox ID to snapshot

        Returns:
            RollbackPoint instance
        """
        try:
            # Get sandbox
            sandbox = await self.sandbox_manager.get_sandbox(sandbox_id, changeset.workspace_id)
            if not sandbox:
                raise ValueError(f"Sandbox not found: {sandbox_id}")

            # Create snapshot
            snapshot_data = await self._create_sandbox_snapshot(sandbox)

            # Create rollback point
            rollback_point_id = str(uuid.uuid4())
            rollback_point = RollbackPoint(
                rollback_point_id=rollback_point_id,
                changeset_id=changeset.changeset_id,
                workspace_id=changeset.workspace_id,
                sandbox_id=sandbox_id,
                snapshot_data=snapshot_data
            )

            # Store rollback point
            self._rollback_points[rollback_point_id] = rollback_point

            # Update changeset
            changeset.rollback_point_id = rollback_point_id
            changeset.rollback_available = True

            logger.info(f"RollbackManager: Created rollback point {rollback_point_id} for changeset {changeset.changeset_id}")
            return rollback_point

        except Exception as e:
            logger.error(f"RollbackManager: Failed to create rollback point: {e}", exc_info=True)
            raise

    async def rollback(
        self,
        changeset: ChangeSetIR
    ) -> ChangeSetIR:
        """
        Rollback a change set to its rollback point

        Args:
            changeset: ChangeSetIR instance with rollback_point_id

        Returns:
            Updated ChangeSetIR with status ROLLED_BACK
        """
        try:
            if not changeset.rollback_point_id:
                raise ValueError(f"Changeset {changeset.changeset_id} does not have a rollback point")

            # Get rollback point
            rollback_point = self._rollback_points.get(changeset.rollback_point_id)
            if not rollback_point:
                raise ValueError(f"Rollback point not found: {changeset.rollback_point_id}")

            # Get sandbox
            sandbox = await self.sandbox_manager.get_sandbox(
                rollback_point.sandbox_id,
                rollback_point.workspace_id
            )
            if not sandbox:
                raise ValueError(f"Sandbox not found: {rollback_point.sandbox_id}")

            # Restore snapshot
            await self._restore_sandbox_snapshot(sandbox, rollback_point.snapshot_data)

            # Update changeset
            changeset.status = ChangeSetStatus.ROLLED_BACK

            logger.info(f"RollbackManager: Rolled back changeset {changeset.changeset_id} to rollback point {changeset.rollback_point_id}")
            return changeset

        except Exception as e:
            logger.error(f"RollbackManager: Failed to rollback: {e}", exc_info=True)
            raise

    async def _create_sandbox_snapshot(self, sandbox: Any) -> Dict[str, Any]:
        """
        Create snapshot of sandbox state

        Args:
            sandbox: Sandbox instance

        Returns:
            Snapshot data dictionary
        """
        snapshot = {
            "sandbox_id": getattr(sandbox, 'sandbox_id', None),
            "sandbox_type": getattr(sandbox, 'sandbox_type', None),
            "files": {},
        }

        # Snapshot files if sandbox supports it
        if hasattr(sandbox, 'list_files'):
            try:
                files = await sandbox.list_files()
                for file_path in files:
                    if hasattr(sandbox, 'read_file'):
                        try:
                            content = await sandbox.read_file(file_path)
                            snapshot["files"][file_path] = content
                        except Exception as e:
                            logger.warning(f"RollbackManager: Failed to read file {file_path} for snapshot: {e}")
            except Exception as e:
                logger.warning(f"RollbackManager: Failed to list files for snapshot: {e}")

        return snapshot

    async def _restore_sandbox_snapshot(self, sandbox: Any, snapshot_data: Dict[str, Any]) -> None:
        """
        Restore sandbox from snapshot

        Args:
            sandbox: Sandbox instance
            snapshot_data: Snapshot data dictionary
        """
        # Restore files
        if "files" in snapshot_data and hasattr(sandbox, 'write_file'):
            for file_path, content in snapshot_data["files"].items():
                try:
                    await sandbox.write_file(file_path, content)
                except Exception as e:
                    logger.warning(f"RollbackManager: Failed to restore file {file_path}: {e}")

    def get_rollback_point(self, rollback_point_id: str) -> Optional[RollbackPoint]:
        """Get rollback point by ID"""
        return self._rollback_points.get(rollback_point_id)

