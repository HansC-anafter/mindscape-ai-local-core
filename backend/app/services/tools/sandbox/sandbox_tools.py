"""
Sandbox Tools Implementation

Tools for interacting with the unified Sandbox system.
"""

from typing import Dict, Any, Optional, List
import logging

from backend.app.services.tools.base import MindscapeTool
from backend.app.services.tools.schemas import ToolMetadata, ToolInputSchema, ToolCategory
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.sandbox.sandbox_manager import SandboxManager

logger = logging.getLogger(__name__)


class SandboxWriteFileTool(MindscapeTool):
    """Write file to sandbox"""

    def __init__(self, store: MindscapeStore):
        self.store = store
        self.sandbox_manager = SandboxManager(store)

        metadata = ToolMetadata(
            name="sandbox.write_file",
            description=(
                "Write file content to sandbox. "
                "**Preferred tool for Project mode** - provides version management, change tracking, and unified UI. "
                "In Project mode, sandbox_id and workspace_id are automatically provided from execution context. "
                "Use this instead of filesystem_write_file when working within a Project."
            ),
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "file_path": {
                        "type": "string",
                        "description": "Relative file path within sandbox (e.g., 'Component.tsx', 'pages/index.tsx')"
                    },
                    "content": {
                        "type": "string",
                        "description": "File content to write"
                    },
                    "sandbox_id": {
                        "type": "string",
                        "description": "Sandbox identifier (optional in Project mode - auto-detected from context)"
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": "Workspace identifier (optional in Project mode - auto-detected from context)"
                    },
                    "version": {
                        "type": "string",
                        "description": "Optional version identifier (default: current)"
                    }
                },
                required=["file_path", "content"]
            ),
            category=ToolCategory.DATA,
            source_type="builtin",
            provider="sandbox",
            danger_level="medium"
        )
        super().__init__(metadata)

    async def execute(
        self,
        file_path: str,
        content: str,
        sandbox_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        version: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Write file to sandbox

        If sandbox_id and workspace_id are not provided, will attempt to get them from:
        1. kwargs (from tool execution context)
        2. Execution context (if available)

        Args:
            file_path: Relative file path within sandbox
            content: File content to write
            sandbox_id: Optional sandbox identifier (will be auto-detected if in Project mode)
            workspace_id: Optional workspace identifier (will be auto-detected if in Project mode)
            version: Optional version identifier (default: current)
            **kwargs: Additional context (may contain sandbox_id, workspace_id from execution context)
        """
        try:
            execution_sandbox_id = sandbox_id or kwargs.get("sandbox_id")
            execution_workspace_id = workspace_id or kwargs.get("workspace_id")

            if not execution_sandbox_id or not execution_workspace_id:
                raise ValueError(
                    "sandbox_id and workspace_id are required. "
                    "In Project mode, these should be automatically provided. "
                    "Please ensure you are using this tool within a Project context."
                )

            sandbox = await self.sandbox_manager.get_sandbox(execution_sandbox_id, execution_workspace_id)
            if not sandbox:
                raise ValueError(f"Sandbox {execution_sandbox_id} not found")

            success = await sandbox.write_file(file_path, content, version)
            if not success:
                raise ValueError(f"Failed to write file {file_path}")

            return {
                "sandbox_id": execution_sandbox_id,
                "file_path": file_path,
                "size": len(content.encode("utf-8")),
                "version": version or "current",
                "success": True
            }
        except Exception as e:
            logger.error(f"Failed to write file to sandbox: {e}")
            raise ValueError(f"Error writing file: {str(e)}")


class SandboxReadFileTool(MindscapeTool):
    """Read file from sandbox"""

    def __init__(self, store: MindscapeStore):
        self.store = store
        self.sandbox_manager = SandboxManager(store)

        metadata = ToolMetadata(
            name="sandbox.read_file",
            description="Read file content from sandbox",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "sandbox_id": {
                        "type": "string",
                        "description": "Sandbox identifier"
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": "Workspace identifier"
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Relative file path within sandbox"
                    },
                    "version": {
                        "type": "string",
                        "description": "Optional version identifier (default: current)"
                    }
                },
                required=["sandbox_id", "workspace_id", "file_path"]
            ),
            category=ToolCategory.DATA,
            source_type="builtin",
            provider="sandbox",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        sandbox_id: str,
        workspace_id: str,
        file_path: str,
        version: Optional[str] = None
    ) -> Dict[str, Any]:
        """Read file from sandbox"""
        try:
            sandbox = await self.sandbox_manager.get_sandbox(sandbox_id, workspace_id)
            if not sandbox:
                raise ValueError(f"Sandbox {sandbox_id} not found")

            content = await sandbox.read_file(file_path, version)
            return {
                "sandbox_id": sandbox_id,
                "file_path": file_path,
                "content": content,
                "size": len(content.encode("utf-8")),
                "version": version or "current"
            }
        except Exception as e:
            logger.error(f"Failed to read file from sandbox: {e}")
            raise ValueError(f"Error reading file: {str(e)}")


class SandboxListFilesTool(MindscapeTool):
    """List files in sandbox"""

    def __init__(self, store: MindscapeStore):
        self.store = store
        self.sandbox_manager = SandboxManager(store)

        metadata = ToolMetadata(
            name="sandbox.list_files",
            description="List files in sandbox",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "sandbox_id": {
                        "type": "string",
                        "description": "Sandbox identifier"
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": "Workspace identifier"
                    },
                    "directory": {
                        "type": "string",
                        "description": "Directory path (empty for root)",
                        "default": ""
                    },
                    "version": {
                        "type": "string",
                        "description": "Optional version identifier (default: current)"
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "List files recursively",
                        "default": True
                    }
                },
                required=["sandbox_id", "workspace_id"]
            ),
            category=ToolCategory.DATA,
            source_type="builtin",
            provider="sandbox",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        sandbox_id: str,
        workspace_id: str,
        directory: str = "",
        version: Optional[str] = None,
        recursive: bool = True
    ) -> Dict[str, Any]:
        """List files in sandbox"""
        try:
            sandbox = await self.sandbox_manager.get_sandbox(sandbox_id, workspace_id)
            if not sandbox:
                raise ValueError(f"Sandbox {sandbox_id} not found")

            files = await sandbox.list_files(directory, version, recursive)
            return {
                "sandbox_id": sandbox_id,
                "directory": directory,
                "files": files,
                "count": len(files),
                "version": version or "current"
            }
        except Exception as e:
            logger.error(f"Failed to list files in sandbox: {e}")
            raise ValueError(f"Error listing files: {str(e)}")


class SandboxCreateVersionTool(MindscapeTool):
    """Create a new version snapshot"""

    def __init__(self, store: MindscapeStore):
        self.store = store
        self.sandbox_manager = SandboxManager(store)

        metadata = ToolMetadata(
            name="sandbox.create_version",
            description="Create a new version snapshot of sandbox",
            input_schema=ToolInputSchema(
                type="object",
                properties={
                    "sandbox_id": {
                        "type": "string",
                        "description": "Sandbox identifier"
                    },
                    "workspace_id": {
                        "type": "string",
                        "description": "Workspace identifier"
                    },
                    "version": {
                        "type": "string",
                        "description": "Version identifier (e.g., v1, v2)"
                    },
                    "source_version": {
                        "type": "string",
                        "description": "Optional source version to copy from"
                    }
                },
                required=["sandbox_id", "workspace_id", "version"]
            ),
            category=ToolCategory.DATA,
            source_type="builtin",
            provider="sandbox",
            danger_level="low"
        )
        super().__init__(metadata)

    async def execute(
        self,
        sandbox_id: str,
        workspace_id: str,
        version: str,
        source_version: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new version snapshot"""
        try:
            sandbox = await self.sandbox_manager.get_sandbox(sandbox_id, workspace_id)
            if not sandbox:
                raise ValueError(f"Sandbox {sandbox_id} not found")

            success = await sandbox.create_version(version, source_version)
            if not success:
                raise ValueError(f"Failed to create version {version}")

            return {
                "sandbox_id": sandbox_id,
                "version": version,
                "source_version": source_version,
                "success": True
            }
        except Exception as e:
            logger.error(f"Failed to create version: {e}")
            raise ValueError(f"Error creating version: {str(e)}")

