"""
Sandbox Manager - System-level sandbox management

Provides unified version management, storage abstraction, and sandbox instance management.
"""

import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging

from backend.app.services.sandbox.types import get_sandbox_class

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.sandbox.base_sandbox import BaseSandbox
from backend.app.services.sandbox.storage.local_storage import LocalStorage
# Import ProjectSandboxManager lazily to avoid circular import

logger = logging.getLogger(__name__)


class SandboxManager:
    """
    System-level sandbox manager

    Manages all sandbox instances with unified version management and storage abstraction.
    Supports multiple sandbox types: threejs_hero, writing_project, project_repo, web_page.
    """

    def __init__(
        self,
        store: MindscapeStore,
        base_sandbox_dir: Optional[Path] = None
    ):
        """
        Initialize Sandbox Manager

        Args:
            store: MindscapeStore instance
            base_sandbox_dir: Base directory for sandbox storage (default: data/sandboxes)
        """
        self.store = store
        self._project_sandbox_manager = None  # Lazy initialization to avoid circular dependency

        if base_sandbox_dir:
            self.base_sandbox_dir = Path(base_sandbox_dir)
        else:
            data_dir = Path(store.db_path).parent
            self.base_sandbox_dir = data_dir / "sandboxes"

        self.base_sandbox_dir.mkdir(parents=True, exist_ok=True)

        self._sandboxes: Dict[str, BaseSandbox] = {}

    def _get_sandbox_path(
        self,
        sandbox_id: str,
        workspace_id: str,
        sandbox_type: str
    ) -> Path:
        """
        Get storage path for sandbox

        Args:
            sandbox_id: Sandbox identifier
            workspace_id: Workspace identifier
            sandbox_type: Type of sandbox

        Returns:
            Path to sandbox storage directory
        """
        return self.base_sandbox_dir / workspace_id / sandbox_type / sandbox_id

    async def create_sandbox(
        self,
        sandbox_type: str,
        workspace_id: str,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Create a new sandbox

        Args:
            sandbox_type: Type of sandbox (threejs_hero, writing_project, etc.)
            workspace_id: Workspace identifier
            context: Optional context dictionary (e.g., {"project_id": "..."})

        Returns:
            Sandbox identifier
        """
        sandbox_id = str(uuid.uuid4())
        sandbox_path = self._get_sandbox_path(sandbox_id, workspace_id, sandbox_type)

        storage = LocalStorage(sandbox_path)

        sandbox_class = get_sandbox_class(sandbox_type)
        sandbox = sandbox_class(
            sandbox_id=sandbox_id,
            sandbox_type=sandbox_type,
            workspace_id=workspace_id,
            storage=storage,
            metadata={
                "created_at": str(Path().cwd()),
                "context": context or {},
            }
        )

        self._sandboxes[sandbox_id] = sandbox

        logger.info(f"Created sandbox {sandbox_id} of type {sandbox_type} in workspace {workspace_id}")
        return sandbox_id

    async def get_sandbox(
        self,
        sandbox_id: str,
        workspace_id: Optional[str] = None
    ) -> Optional[BaseSandbox]:
        """
        Get sandbox instance

        Args:
            sandbox_id: Sandbox identifier
            workspace_id: Optional workspace identifier for validation

        Returns:
            Sandbox instance or None if not found
        """
        if sandbox_id in self._sandboxes:
            sandbox = self._sandboxes[sandbox_id]
            if workspace_id and sandbox.workspace_id != workspace_id:
                logger.warning(f"Workspace mismatch for sandbox {sandbox_id}")
                return None
            return sandbox

        logger.warning(f"Sandbox {sandbox_id} not found in cache")
        return None

    async def list_sandboxes(
        self,
        workspace_id: Optional[str] = None,
        sandbox_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List all sandboxes

        Args:
            workspace_id: Optional workspace filter
            sandbox_type: Optional sandbox type filter

        Returns:
            List of sandbox metadata dictionaries
        """
        sandboxes = []
        workspace_path = self.base_sandbox_dir

        if workspace_id:
            workspace_path = workspace_path / workspace_id
            if not workspace_path.exists():
                return []

        try:
            for ws_dir in workspace_path.iterdir():
                if not ws_dir.is_dir():
                    continue

                ws_id = ws_dir.name
                if workspace_id and ws_id != workspace_id:
                    continue

                for type_dir in ws_dir.iterdir():
                    if not type_dir.is_dir():
                        continue

                    type_name = type_dir.name
                    if sandbox_type and type_name != sandbox_type:
                        continue

                    for sandbox_dir in type_dir.iterdir():
                        if not sandbox_dir.is_dir():
                            continue

                        sandbox_id = sandbox_dir.name
                        sandboxes.append({
                            "sandbox_id": sandbox_id,
                            "sandbox_type": type_name,
                            "workspace_id": ws_id,
                            "path": str(sandbox_dir),
                        })
        except Exception as e:
            logger.error(f"Failed to list sandboxes: {e}")

        return sandboxes

    async def delete_sandbox(
        self,
        sandbox_id: str,
        workspace_id: Optional[str] = None
    ) -> bool:
        """
        Delete sandbox

        Args:
            sandbox_id: Sandbox identifier
            workspace_id: Optional workspace identifier for validation

        Returns:
            True if delete successful, False otherwise
        """
        sandbox = await self.get_sandbox(sandbox_id, workspace_id)
        if not sandbox:
            return False

        try:
            import shutil
            sandbox_path = self._get_sandbox_path(
                sandbox_id,
                sandbox.workspace_id,
                sandbox.sandbox_type
            )
            if sandbox_path.exists():
                shutil.rmtree(sandbox_path)

            if sandbox_id in self._sandboxes:
                del self._sandboxes[sandbox_id]

            logger.info(f"Deleted sandbox {sandbox_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete sandbox {sandbox_id}: {e}")
            return False

