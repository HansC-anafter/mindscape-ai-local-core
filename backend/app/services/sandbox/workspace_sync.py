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


# Directories to sync from workspace to sandbox
SYNC_DIRECTORIES = ["spec", "hero", "sections", "pages"]


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
    
    async def sync_workspace_to_sandbox(
        self,
        workspace_id: str,
        sandbox_id: str
    ) -> List[str]:
        """
        Sync workspace files to sandbox.
        
        Copies files from workspace SYNC_DIRECTORIES to sandbox.
        
        Args:
            workspace_id: Workspace identifier
            sandbox_id: Sandbox identifier
            
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
            
            for dir_name in SYNC_DIRECTORIES:
                source_dir = workspace_path / dir_name
                if not source_dir.exists():
                    continue
                
                # Walk directory and sync files
                for root, _, files in os.walk(source_dir):
                    for filename in files:
                        source_file = Path(root) / filename
                        relative_path = source_file.relative_to(workspace_path)
                        
                        try:
                            content = source_file.read_text(encoding="utf-8")
                            await sandbox.write_file(str(relative_path), content)
                            synced_files.append(str(relative_path))
                            logger.debug(f"Synced: {relative_path}")
                        except Exception as e:
                            logger.warning(f"Failed to sync {relative_path}: {e}")
            
            # For web_page sandbox, also sync pages to app directory
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

