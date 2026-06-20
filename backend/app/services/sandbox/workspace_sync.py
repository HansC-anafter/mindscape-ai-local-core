"""
Workspace-Sandbox Sync Service

Provides automatic synchronization between workspace files and sandboxes.
Implements the "workspace as source of truth" pattern with sandbox as feature layer.

Architecture:
    Workspace (persistent) ←→ Sandbox (features: preview, versioning, deploy)

If sandbox is missing or corrupted, it can be rebuilt from workspace.
"""

import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

from backend.app.services.sandbox.sandbox_manager import SandboxManager
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.sandbox.workspace_sync_core.file_operations import (
    get_workspace_sandbox_diff,
    sync_sandbox_files_to_workspace,
    sync_workspace_files_to_sandbox,
)
from backend.app.services.sandbox.workspace_sync_core.filters import (
    DEFAULT_SYNC_DIRECTORIES,
    PROTECTED_PATTERNS,
    get_sync_directories,
    is_protected,
    should_sync_file,
)

logger = logging.getLogger(__name__)


class WorkspaceSandboxSync:
    """
    Synchronizes workspace files to sandbox for preview and version management.

    Key behaviors:
    1. Workspace is the source of truth - files always written there first
    2. Sandbox provides features (preview, versioning) on top of workspace files
    3. If sandbox missing/corrupted, auto-rebuild from workspace
    """

    def __init__(
        self,
        store: MindscapeStore,
        sandbox_manager: Optional[SandboxManager] = None
    ):
        """
        Initialize sync service.

        Args:
            store: MindscapeStore instance
            sandbox_manager: Optional SandboxManager (created if not provided)
        """
        self.store = store
        self.sandbox_manager = sandbox_manager or SandboxManager(store)

        # Get workspace base directory
        data_dir = Path(store.db_path).parent
        self.workspace_dir = data_dir / "workspaces"

    def get_workspace_path(self, workspace_id: str) -> Path:
        """Get workspace directory path"""
        return self.workspace_dir / workspace_id if workspace_id else self.workspace_dir

    async def ensure_sandbox_for_preview(
        self,
        workspace_id: str,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Ensure a sandbox exists and is synced for preview.

        Creates sandbox if not exists, syncs from workspace if needed.

        Args:
            workspace_id: Workspace identifier
            project_id: Optional project identifier

        Returns:
            Dict with sandbox_id, synced_files, status
        """
        try:
            # Check for existing sandbox
            existing_sandbox = await self._find_existing_sandbox(workspace_id, project_id)

            if existing_sandbox:
                sandbox_id = existing_sandbox["sandbox_id"]
                logger.info(f"Found existing sandbox: {sandbox_id}")

                # Ensure template is initialized (may be missing after restart)
                sandbox = await self.sandbox_manager.get_sandbox(sandbox_id, workspace_id)
                if sandbox and hasattr(sandbox, "initialize_template"):
                    await sandbox.initialize_template()
                    logger.info(f"Ensured template initialized for sandbox {sandbox_id}")

                # Sync latest workspace changes
                synced = await self.sync_workspace_to_sandbox(workspace_id, sandbox_id)

                return {
                    "sandbox_id": sandbox_id,
                    "synced_files": synced,
                    "status": "synced",
                    "created": False
                }

            # Create new sandbox
            sandbox_id = await self._create_and_initialize_sandbox(
                workspace_id, project_id
            )

            # Sync workspace files
            synced = await self.sync_workspace_to_sandbox(workspace_id, sandbox_id)

            return {
                "sandbox_id": sandbox_id,
                "synced_files": synced,
                "status": "created",
                "created": True
            }

        except Exception as e:
            logger.error(f"Failed to ensure sandbox: {e}")
            return {
                "sandbox_id": None,
                "synced_files": [],
                "status": "error",
                "error": str(e)
            }

    def _get_sync_directories(self, sandbox_type: str) -> Optional[List[str]]:
        """
        Get sync directories for sandbox type.

        Args:
            sandbox_type: Type of sandbox

        Returns:
            List of directories to sync, or None to sync all non-protected files
        """
        return get_sync_directories(sandbox_type)

    def _should_sync_file(self, file_path: str, sync_dirs: Optional[List[str]]) -> bool:
        """
        Check if file should be synced based on directory whitelist.

        Args:
            file_path: Relative file path
            sync_dirs: List of allowed directories, or None for all

        Returns:
            True if file should be synced
        """
        return should_sync_file(file_path, sync_dirs)

    async def sync_workspace_to_sandbox(
        self,
        workspace_id: str,
        sandbox_id: str,
        directories: Optional[List[str]] = None
    ) -> List[str]:
        """
        Sync workspace files to sandbox.

        Copies files from workspace to sandbox based on sandbox type's sync directories.

        Args:
            workspace_id: Workspace identifier
            sandbox_id: Sandbox identifier
            directories: Optional override for directories to sync

        Returns:
            List of synced file paths
        """
        synced_files = []

        try:
            sandbox = await self.sandbox_manager.get_sandbox(sandbox_id, workspace_id)
            if not sandbox:
                logger.error(f"Sandbox not found: {sandbox_id}")
                return []

            workspace_path = self.get_workspace_path(workspace_id)

            # Get sync directories from sandbox type or override
            sync_dirs = directories or self._get_sync_directories(sandbox.sandbox_type)

            synced_files = await sync_workspace_files_to_sandbox(
                workspace_path,
                sandbox,
                sync_dirs,
            )

            logger.info(f"Synced {len(synced_files)} files to sandbox {sandbox_id}")
            return synced_files

        except Exception as e:
            logger.error(f"Sync failed: {e}")
            return synced_files

    async def rebuild_sandbox_from_workspace(
        self,
        workspace_id: str,
        sandbox_id: str
    ) -> bool:
        """
        Rebuild sandbox from workspace files.

        Use when sandbox is corrupted or needs reset.

        Args:
            workspace_id: Workspace identifier
            sandbox_id: Sandbox identifier

        Returns:
            True if rebuild successful
        """
        try:
            sandbox = await self.sandbox_manager.get_sandbox(sandbox_id, workspace_id)
            if not sandbox:
                return False

            # Initialize template if web_page sandbox
            if sandbox.sandbox_type == "web_page":
                if hasattr(sandbox, "initialize_template"):
                    await sandbox.initialize_template()

            # Sync all workspace files
            synced = await self.sync_workspace_to_sandbox(workspace_id, sandbox_id)

            logger.info(f"Rebuilt sandbox {sandbox_id} with {len(synced)} files")
            return len(synced) > 0

        except Exception as e:
            logger.error(f"Rebuild failed: {e}")
            return False

    async def sync_sandbox_to_workspace(
        self,
        workspace_id: str,
        sandbox_id: str,
        create_backup: bool = True,
        directories: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Sync sandbox files back to workspace (for persistence).

        This is the "save" operation - takes sandbox changes and persists them.
        Creates backup of existing files before overwriting.

        Args:
            workspace_id: Workspace identifier
            sandbox_id: Sandbox identifier
            create_backup: Whether to backup existing files before overwriting
            directories: Optional override for directories to sync

        Returns:
            Dict with synced_files, backed_up_files, status
        """
        synced_files = []
        backed_up_files = []

        try:
            sandbox = await self.sandbox_manager.get_sandbox(sandbox_id, workspace_id)
            if not sandbox:
                return {"synced_files": [], "backed_up_files": [], "status": "error", "error": "Sandbox not found"}

            workspace_path = self.get_workspace_path(workspace_id)

            # Get sync directories from sandbox type or override
            sync_dirs = directories or self._get_sync_directories(sandbox.sandbox_type)

            result = await sync_sandbox_files_to_workspace(
                workspace_path,
                sandbox,
                sync_dirs,
                create_backup=create_backup,
            )
            synced_files = result["synced_files"]
            backed_up_files = result["backed_up_files"]

            logger.info(f"Synced {len(synced_files)} files from sandbox to workspace")
            return result

        except Exception as e:
            logger.error(f"Sync to workspace failed: {e}")
            return {
                "synced_files": synced_files,
                "backed_up_files": backed_up_files,
                "status": "error",
                "error": str(e)
            }

    def _is_protected(self, file_path: str) -> bool:
        """Check if file matches protected patterns"""
        return is_protected(file_path)

    async def get_sync_diff(
        self,
        workspace_id: str,
        sandbox_id: str,
        directories: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Get diff between workspace and sandbox files.

        Useful for showing user what will change before sync.

        Args:
            workspace_id: Workspace identifier
            sandbox_id: Sandbox identifier
            directories: Optional override for directories to compare

        Returns:
            Dict with added, modified, deleted files
        """
        try:
            sandbox = await self.sandbox_manager.get_sandbox(sandbox_id, workspace_id)
            if not sandbox:
                return {"error": "Sandbox not found"}

            workspace_path = self.get_workspace_path(workspace_id)

            # Get sync directories from sandbox type or override
            sync_dirs = directories or self._get_sync_directories(sandbox.sandbox_type)

            return await get_workspace_sandbox_diff(
                workspace_path,
                sandbox,
                sync_dirs,
            )

        except Exception as e:
            logger.error(f"Failed to get sync diff: {e}")
            return {"error": str(e)}

    async def _find_existing_sandbox(
        self,
        workspace_id: str,
        project_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Find existing web_page sandbox for workspace/project"""
        try:
            sandboxes = await self.sandbox_manager.list_sandboxes(
                workspace_id=workspace_id,
                sandbox_type="web_page"
            )

            if project_id:
                # Find sandbox with matching project_id
                for s in sandboxes:
                    ctx = s.get("metadata", {}).get("context", {})
                    if ctx.get("project_id") == project_id:
                        return s

            # Return first web_page sandbox if no project_id specified
            if sandboxes:
                return sandboxes[0]

            return None

        except Exception as e:
            logger.error(f"Failed to find sandbox: {e}")
            return None

    async def _create_and_initialize_sandbox(
        self,
        workspace_id: str,
        project_id: Optional[str] = None
    ) -> str:
        """Create new web_page sandbox and initialize template"""
        context = {}
        if project_id:
            context["project_id"] = project_id

        sandbox_id = await self.sandbox_manager.create_sandbox(
            sandbox_type="web_page",
            workspace_id=workspace_id,
            context=context
        )

        # Initialize Next.js template
        sandbox = await self.sandbox_manager.get_sandbox(sandbox_id, workspace_id)
        if sandbox and hasattr(sandbox, "initialize_template"):
            await sandbox.initialize_template()
            logger.info(f"Initialized Next.js template for sandbox {sandbox_id}")

        return sandbox_id


# Global instance
_sync_service: Optional[WorkspaceSandboxSync] = None


def get_workspace_sync_service(store: Optional[MindscapeStore] = None) -> WorkspaceSandboxSync:
    """
    Get or create global workspace sync service.

    Args:
        store: Optional MindscapeStore (uses default if not provided)

    Returns:
        WorkspaceSandboxSync instance
    """
    global _sync_service

    if _sync_service is None:
        if store is None:
            store = MindscapeStore()
        _sync_service = WorkspaceSandboxSync(store)

    return _sync_service
