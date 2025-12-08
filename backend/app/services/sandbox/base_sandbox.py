"""
Base Sandbox class for all sandbox types

Provides unified interface for all sandbox implementations with version management
and change tracking.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import datetime
import logging

from backend.app.services.sandbox.storage.base_storage import BaseStorage

logger = logging.getLogger(__name__)


class BaseSandbox(ABC):
    """
    Abstract base class for all sandbox types

    Provides unified interface for:
    - File operations (read, write, list, delete)
    - Version management (create, switch, list)
    - Change tracking and summaries
    """

    def __init__(
        self,
        sandbox_id: str,
        sandbox_type: str,
        workspace_id: str,
        storage: BaseStorage,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize sandbox

        Args:
            sandbox_id: Unique sandbox identifier
            sandbox_type: Type of sandbox (threejs_hero, writing_project, etc.)
            workspace_id: Workspace identifier
            storage: Storage backend instance
            metadata: Optional metadata dictionary
        """
        self.sandbox_id = sandbox_id
        self.sandbox_type = sandbox_type
        self.workspace_id = workspace_id
        self.storage = storage
        self.metadata = metadata or {}
        self.current_version: Optional[str] = None

    async def read_file(self, file_path: str, version: Optional[str] = None) -> str:
        """
        Read file content

        Args:
            file_path: Relative path to file within sandbox
            version: Optional version identifier (default: current)

        Returns:
            File content as string
        """
        return await self.storage.read_file(file_path, version or self.current_version)

    async def write_file(
        self,
        file_path: str,
        content: str,
        version: Optional[str] = None
    ) -> bool:
        """
        Write file content

        Args:
            file_path: Relative path to file within sandbox
            content: File content to write
            version: Optional version identifier (default: current)

        Returns:
            True if write successful, False otherwise
        """
        return await self.storage.write_file(file_path, content, version or self.current_version)

    async def delete_file(self, file_path: str, version: Optional[str] = None) -> bool:
        """
        Delete file

        Args:
            file_path: Relative path to file within sandbox
            version: Optional version identifier (default: current)

        Returns:
            True if delete successful, False otherwise
        """
        return await self.storage.delete_file(file_path, version or self.current_version)

    async def list_files(
        self,
        directory: str = "",
        version: Optional[str] = None,
        recursive: bool = True
    ) -> List[Dict[str, Any]]:
        """
        List files in directory

        Args:
            directory: Relative path to directory (empty string for root)
            version: Optional version identifier (default: current)
            recursive: Whether to list files recursively

        Returns:
            List of file metadata dictionaries
        """
        return await self.storage.list_files(
            directory,
            version or self.current_version,
            recursive
        )

    async def file_exists(self, file_path: str, version: Optional[str] = None) -> bool:
        """
        Check if file exists

        Args:
            file_path: Relative path to file within sandbox
            version: Optional version identifier (default: current)

        Returns:
            True if file exists, False otherwise
        """
        return await self.storage.file_exists(file_path, version or self.current_version)

    async def create_version(self, version: str, source_version: Optional[str] = None) -> bool:
        """
        Create a new version snapshot

        Args:
            version: Version identifier (e.g., "v1", "v2")
            source_version: Optional source version to copy from

        Returns:
            True if version created successfully, False otherwise
        """
        success = await self.storage.create_version(version, source_version)
        if success:
            self.current_version = version
        return success

    async def list_versions(self) -> List[str]:
        """
        List all available versions

        Returns:
            List of version identifiers
        """
        return await self.storage.list_versions()

    async def get_version_metadata(self, version: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific version

        Args:
            version: Version identifier

        Returns:
            Dictionary with version metadata
        """
        return await self.storage.get_version_metadata(version)

    async def switch_version(self, version: str) -> bool:
        """
        Switch to a specific version

        Args:
            version: Version identifier

        Returns:
            True if version exists and switch successful, False otherwise
        """
        versions = await self.list_versions()
        if version not in versions:
            return False

        success = await self.storage.switch_version(version)
        if success:
            self.current_version = version
        return success

    async def rollback_to_version(self, version: str) -> bool:
        """
        Rollback to a specific version

        Creates a new version from the target version and switches to it.

        Args:
            version: Version identifier to rollback to

        Returns:
            True if rollback successful, False otherwise
        """
        versions = await self.list_versions()
        if version not in versions:
            return False

        rollback_version = f"rollback-{version}"
        success = await self.create_version(rollback_version, source_version=version)
        if success:
            return await self.switch_version(rollback_version)
        return False

    @abstractmethod
    async def get_change_summary(
        self,
        from_version: Optional[str],
        to_version: Optional[str]
    ) -> str:
        """
        Get AI-generated summary of changes between versions

        Args:
            from_version: Source version identifier (None for current)
            to_version: Target version identifier (None for current)

        Returns:
            Human-readable summary of changes
        """
        pass

    @abstractmethod
    async def validate(self) -> Dict[str, Any]:
        """
        Validate sandbox structure and content

        Returns:
            Dictionary with validation results:
            - valid: Boolean indicating if sandbox is valid
            - errors: List of error messages
            - warnings: List of warning messages
        """
        pass

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert sandbox to dictionary representation

        Returns:
            Dictionary with sandbox metadata
        """
        return {
            "sandbox_id": self.sandbox_id,
            "sandbox_type": self.sandbox_type,
            "workspace_id": self.workspace_id,
            "current_version": self.current_version,
            "metadata": self.metadata,
        }

