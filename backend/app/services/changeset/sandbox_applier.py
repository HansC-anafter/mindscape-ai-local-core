"""
Sandbox Applier

Applies change sets to sandbox and generates preview URLs.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from backend.app.core.ir.changeset import ChangeSetIR, ChangeSetStatus, ChangePatch, ChangeType
from backend.app.services.sandbox.sandbox_manager import SandboxManager
from backend.app.services.sandbox.preview_server import SandboxPreviewServer
from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


class SandboxApplier:
    """
    Applies change sets to sandbox and generates preview URLs
    """

    def __init__(self, store: Optional[MindscapeStore] = None):
        """
        Initialize SandboxApplier

        Args:
            store: MindscapeStore instance (will create if not provided)
        """
        if store is None:
            from backend.app.services.mindscape_store import MindscapeStore
            store = MindscapeStore()
        self.store = store
        self.sandbox_manager = SandboxManager(store)

    async def apply_to_sandbox(
        self,
        changeset: ChangeSetIR,
        sandbox_id: Optional[str] = None,
        sandbox_type: Optional[str] = None
    ) -> ChangeSetIR:
        """
        Apply change set to sandbox and generate preview URL

        Args:
            changeset: ChangeSetIR instance
            sandbox_id: Sandbox ID (will create if not provided)
            sandbox_type: Sandbox type (required if sandbox_id not provided)

        Returns:
            Updated ChangeSetIR with preview_url and applied_to_sandbox_at
        """
        try:
            # Get or create sandbox
            if not sandbox_id:
                if not sandbox_type:
                    # Infer sandbox type from changeset metadata
                    sandbox_type = self._infer_sandbox_type(changeset)

                sandbox_id = await self.sandbox_manager.create_sandbox(
                    sandbox_type=sandbox_type,
                    workspace_id=changeset.workspace_id,
                    context={
                        "changeset_id": changeset.changeset_id,
                        "plan_id": changeset.plan_id,
                    }
                )
                logger.info(f"SandboxApplier: Created sandbox {sandbox_id} for changeset {changeset.changeset_id}")

            # Get sandbox instance
            sandbox = await self.sandbox_manager.get_sandbox(sandbox_id, changeset.workspace_id)
            if not sandbox:
                raise ValueError(f"Sandbox not found: {sandbox_id}")

            # Apply patches to sandbox
            for patch in changeset.patches:
                await self._apply_patch_to_sandbox(sandbox, patch)

            # Generate preview URL
            preview_url = await self._generate_preview_url(sandbox, changeset)

            # Update changeset
            changeset.preview_url = preview_url
            changeset.applied_to_sandbox_at = datetime.utcnow()
            changeset.status = ChangeSetStatus.APPLIED_TO_SANDBOX

            logger.info(f"SandboxApplier: Applied changeset {changeset.changeset_id} to sandbox {sandbox_id}, preview_url={preview_url}")
            return changeset

        except Exception as e:
            logger.error(f"SandboxApplier: Failed to apply changeset to sandbox: {e}", exc_info=True)
            raise

    async def _apply_patch_to_sandbox(self, sandbox: Any, patch: ChangePatch) -> None:
        """
        Apply a single patch to sandbox

        Args:
            sandbox: Sandbox instance
            patch: ChangePatch instance
        """
        try:
            if patch.change_type == ChangeType.CREATE:
                await self._apply_create_patch(sandbox, patch)
            elif patch.change_type == ChangeType.UPDATE:
                await self._apply_update_patch(sandbox, patch)
            elif patch.change_type == ChangeType.DELETE:
                await self._apply_delete_patch(sandbox, patch)
            elif patch.change_type == ChangeType.MOVE:
                await self._apply_move_patch(sandbox, patch)
            elif patch.change_type == ChangeType.COPY:
                await self._apply_copy_patch(sandbox, patch)
            else:
                logger.warning(f"SandboxApplier: Unknown change type {patch.change_type}, skipping patch")
        except Exception as e:
            logger.error(f"SandboxApplier: Failed to apply patch {patch.target}: {e}", exc_info=True)
            raise

    async def _apply_create_patch(self, sandbox: Any, patch: ChangePatch) -> None:
        """Apply CREATE patch to sandbox"""
        # Implementation depends on sandbox type
        # For now, use sandbox's write_file or similar method
        if hasattr(sandbox, 'write_file') and patch.path:
            await sandbox.write_file(patch.path, patch.new_value)
        elif hasattr(sandbox, 'create_resource'):
            await sandbox.create_resource(patch.target, patch.new_value)
        else:
            logger.warning(f"SandboxApplier: Sandbox does not support CREATE operation, skipping patch {patch.target}")

    async def _apply_update_patch(self, sandbox: Any, patch: ChangePatch) -> None:
        """Apply UPDATE patch to sandbox"""
        if hasattr(sandbox, 'write_file') and patch.path:
            await sandbox.write_file(patch.path, patch.new_value)
        elif hasattr(sandbox, 'update_resource'):
            await sandbox.update_resource(patch.target, patch.new_value, patch.path)
        else:
            logger.warning(f"SandboxApplier: Sandbox does not support UPDATE operation, skipping patch {patch.target}")

    async def _apply_delete_patch(self, sandbox: Any, patch: ChangePatch) -> None:
        """Apply DELETE patch to sandbox"""
        if hasattr(sandbox, 'delete_file') and patch.path:
            await sandbox.delete_file(patch.path)
        elif hasattr(sandbox, 'delete_resource'):
            await sandbox.delete_resource(patch.target, patch.path)
        else:
            logger.warning(f"SandboxApplier: Sandbox does not support DELETE operation, skipping patch {patch.target}")

    async def _apply_move_patch(self, sandbox: Any, patch: ChangePatch) -> None:
        """Apply MOVE patch to sandbox"""
        if hasattr(sandbox, 'move_file'):
            old_path = patch.old_value if isinstance(patch.old_value, str) else patch.path
            new_path = patch.new_value if isinstance(patch.new_value, str) else patch.path
            await sandbox.move_file(old_path, new_path)
        else:
            logger.warning(f"SandboxApplier: Sandbox does not support MOVE operation, skipping patch {patch.target}")

    async def _apply_copy_patch(self, sandbox: Any, patch: ChangePatch) -> None:
        """Apply COPY patch to sandbox"""
        if hasattr(sandbox, 'copy_file'):
            source_path = patch.old_value if isinstance(patch.old_value, str) else patch.path
            dest_path = patch.new_value if isinstance(patch.new_value, str) else patch.path
            await sandbox.copy_file(source_path, dest_path)
        else:
            logger.warning(f"SandboxApplier: Sandbox does not support COPY operation, skipping patch {patch.target}")

    async def _generate_preview_url(self, sandbox: Any, changeset: ChangeSetIR) -> Optional[str]:
        """
        Generate preview URL for sandbox

        Args:
            sandbox: Sandbox instance
            changeset: ChangeSetIR instance

        Returns:
            Preview URL or None
        """
        try:
            # Get sandbox path
            sandbox_path = getattr(sandbox, 'sandbox_path', None)
            if not sandbox_path:
                return None

            # Start preview server if available
            if hasattr(sandbox, 'sandbox_id'):
                preview_server = SandboxPreviewServer(
                    sandbox_id=sandbox.sandbox_id,
                    sandbox_path=sandbox_path
                )
                server_info = await preview_server.start()
                if server_info.get("success"):
                    port = server_info.get("port")
                    return f"http://localhost:{port}"

            return None
        except Exception as e:
            logger.warning(f"SandboxApplier: Failed to generate preview URL: {e}", exc_info=True)
            return None

    def _infer_sandbox_type(self, changeset: ChangeSetIR) -> str:
        """
        Infer sandbox type from changeset

        Args:
            changeset: ChangeSetIR instance

        Returns:
            Sandbox type string
        """
        # Infer from patches or metadata
        if changeset.metadata:
            tool_id = changeset.metadata.get("tool_id", "")
            if "wordpress" in tool_id.lower() or "wp" in tool_id.lower():
                return "web_page"
            elif "filesystem" in tool_id.lower():
                return "project_repo"

        # Default to web_page for most cases
        return "web_page"









