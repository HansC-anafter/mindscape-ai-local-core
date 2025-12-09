"""
Workspace-Sandbox Sync Service

Provides automatic synchronization between workspace files and sandboxes.
Implements the "workspace as source of truth" pattern with sandbox as feature layer.

Architecture:
    Workspace (persistent) ←→ Sandbox (features: preview, versioning, deploy)

If sandbox is missing or corrupted, it can be rebuilt from workspace.
"""

import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any, List

from backend.app.services.sandbox.sandbox_manager import SandboxManager
from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


# Protected patterns that should NEVER be synced (framework/system files)
PROTECTED_PATTERNS = [
    "package.json",      # Framework config
    "package-lock.json", # Lock files
    "yarn.lock",
    "pnpm-lock.yaml",
    "node_modules/",     # Dependencies
    ".git/",             # Version control
    ".gitignore",
    ".env",              # Environment
    ".env.*",
    "tsconfig.json",     # TypeScript config
    "next.config.*",     # Next.js config
    "vite.config.*",     # Vite config
    "tailwind.config.*", # Tailwind config
    "postcss.config.*",  # PostCSS config
    ".next/",            # Build output
    "dist/",
    "build/",
    "out/",
    "__pycache__/",
    "*.pyc",
    ".DS_Store",
]

# Default sync directories per sandbox type
# Each sandbox type can override this in its class
DEFAULT_SYNC_DIRECTORIES = {
    "web_page": ["spec", "hero", "sections", "pages", "components", "styles", "public"],
    "threejs_hero": ["components", "scenes", "assets"],
    "writing_project": ["chapters", "drafts", "notes", "outline"],
    "project_repo": None,  # None = sync all non-protected files
}


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
        return DEFAULT_SYNC_DIRECTORIES.get(sandbox_type)

    def _should_sync_file(self, file_path: str, sync_dirs: Optional[List[str]]) -> bool:
        """
        Check if file should be synced based on directory whitelist.

        Args:
            file_path: Relative file path
            sync_dirs: List of allowed directories, or None for all

        Returns:
            True if file should be synced
        """
        # Always skip protected patterns
        if self._is_protected(file_path):
            return False

        # If no whitelist, sync all non-protected files
        if sync_dirs is None:
            return True

        # Check if file is in whitelisted directory
        for dir_name in sync_dirs:
            if file_path.startswith(dir_name + "/") or file_path.startswith(dir_name + "\\"):
                return True
            # Also allow files directly named with directory prefix
            if file_path == dir_name or file_path.startswith(dir_name):
                return True

        return False

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

            if sync_dirs:
                # Sync specific directories
                for dir_name in sync_dirs:
                    source_dir = workspace_path / dir_name
                    if not source_dir.exists():
                        continue

                    for root, _, files in os.walk(source_dir):
                        for filename in files:
                            source_file = Path(root) / filename
                            relative_path = source_file.relative_to(workspace_path)

                            if not self._should_sync_file(str(relative_path), sync_dirs):
                                continue

                            try:
                                content = source_file.read_text(encoding="utf-8")
                                await sandbox.write_file(str(relative_path), content)
                                synced_files.append(str(relative_path))
                                logger.debug(f"Synced: {relative_path}")
                            except Exception as e:
                                logger.warning(f"Failed to sync {relative_path}: {e}")
            else:
                # Sync all non-protected files
                if workspace_path.exists():
                    for root, _, files in os.walk(workspace_path):
                        for filename in files:
                            source_file = Path(root) / filename
                            relative_path = source_file.relative_to(workspace_path)

                            if not self._should_sync_file(str(relative_path), None):
                                continue

                            try:
                                content = source_file.read_text(encoding="utf-8")
                                await sandbox.write_file(str(relative_path), content)
                                synced_files.append(str(relative_path))
                                logger.debug(f"Synced: {relative_path}")
                            except Exception as e:
                                logger.warning(f"Failed to sync {relative_path}: {e}")

            # Post-sync hooks for specific sandbox types
            if sandbox.sandbox_type == "web_page":
                if hasattr(sandbox, "sync_pages_to_app"):
                    await sandbox.sync_pages_to_app()

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
            workspace_path.mkdir(parents=True, exist_ok=True)

            # Get sync directories from sandbox type or override
            sync_dirs = directories or self._get_sync_directories(sandbox.sandbox_type)

            # Get all files in sandbox
            sandbox_files = await sandbox.list_files()

            for file_info in sandbox_files:
                file_path = file_info["path"]

                # Check if file should be synced
                if not self._should_sync_file(file_path, sync_dirs):
                    logger.debug(f"Skipping file (not in sync dirs or protected): {file_path}")
                    continue

                try:
                    content = await sandbox.read_file(file_path)
                    target_path = workspace_path / file_path

                    # Create backup if file exists and backup is enabled
                    if create_backup and target_path.exists():
                        backup_path = target_path.with_suffix(target_path.suffix + ".backup")
                        import shutil
                        shutil.copy2(target_path, backup_path)
                        backed_up_files.append(str(file_path))
                        logger.debug(f"Backed up: {file_path}")

                    # Ensure parent directory exists
                    target_path.parent.mkdir(parents=True, exist_ok=True)

                    # Write file
                    target_path.write_text(content, encoding="utf-8")
                    synced_files.append(file_path)
                    logger.debug(f"Synced to workspace: {file_path}")

                except Exception as e:
                    logger.warning(f"Failed to sync {file_path} to workspace: {e}")

            logger.info(f"Synced {len(synced_files)} files from sandbox to workspace")
            return {
                "synced_files": synced_files,
                "backed_up_files": backed_up_files,
                "status": "success"
            }

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
        import fnmatch
        for pattern in PROTECTED_PATTERNS:
            if fnmatch.fnmatch(file_path, pattern) or pattern in file_path:
                return True
        return False

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

            # Get sandbox files (filtered by sync dirs)
            sandbox_files = await sandbox.list_files()
            sandbox_paths = {
                f["path"] for f in sandbox_files
                if self._should_sync_file(f["path"], sync_dirs)
            }

            # Get workspace files
            workspace_paths = set()
            if sync_dirs:
                for dir_name in sync_dirs:
                    dir_path = workspace_path / dir_name
                    if dir_path.exists():
                        for root, _, files in os.walk(dir_path):
                            for f in files:
                                rel_path = str(Path(root).relative_to(workspace_path) / f)
                                if self._should_sync_file(rel_path, sync_dirs):
                                    workspace_paths.add(rel_path)
            else:
                # All non-protected files
                if workspace_path.exists():
                    for root, _, files in os.walk(workspace_path):
                        for f in files:
                            rel_path = str(Path(root).relative_to(workspace_path) / f)
                            if self._should_sync_file(rel_path, None):
                                workspace_paths.add(rel_path)

            added = sandbox_paths - workspace_paths
            deleted = workspace_paths - sandbox_paths
            common = sandbox_paths & workspace_paths

            # Check for modifications
            modified = []
            for path in common:
                try:
                    sandbox_content = await sandbox.read_file(path)
                    workspace_content = (workspace_path / path).read_text(encoding="utf-8")
                    if sandbox_content != workspace_content:
                        modified.append(path)
                except Exception:
                    pass

            return {
                "added": list(added),
                "modified": modified,
                "deleted": list(deleted),
                "unchanged": list(common - set(modified)),
                "sandbox_type": sandbox.sandbox_type,
                "sync_directories": sync_dirs
            }

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

