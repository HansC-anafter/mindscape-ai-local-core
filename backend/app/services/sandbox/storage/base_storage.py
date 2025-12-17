"""
Base storage interface for Sandbox system

Defines the storage abstraction layer that supports both local and cloud storage.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, List, Dict, Any


class BaseStorage(ABC):
    """
    Abstract base class for storage backends

    Provides unified interface for reading, writing, and managing files
    in sandbox storage (local filesystem or cloud storage).
    """

    @abstractmethod
    async def read_file(self, file_path: str, version: Optional[str] = None) -> str:
        """
        Read file content from storage

        Args:
            file_path: Relative path to file within sandbox
            version: Optional version identifier (e.g., "v1", "v2")

        Returns:
            File content as string

        Raises:
            FileNotFoundError: If file does not exist
            IOError: If file cannot be read
        """
        pass

    @abstractmethod
    async def write_file(
        self,
        file_path: str,
        content: str,
        version: Optional[str] = None
    ) -> bool:
        """
        Write file content to storage

        Args:
            file_path: Relative path to file within sandbox
            content: File content to write
            version: Optional version identifier (e.g., "v1", "v2")

        Returns:
            True if write successful, False otherwise

        Raises:
            IOError: If file cannot be written
        """
        pass

    @abstractmethod
    async def delete_file(self, file_path: str, version: Optional[str] = None) -> bool:
        """
        Delete file from storage

        Args:
            file_path: Relative path to file within sandbox
            version: Optional version identifier

        Returns:
            True if delete successful, False otherwise
        """
        pass

    @abstractmethod
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
            version: Optional version identifier
            recursive: Whether to list files recursively

        Returns:
            List of file metadata dictionaries with keys:
            - path: Relative file path
            - size: File size in bytes
            - modified: Modification timestamp
            - type: File type (file/directory)
        """
        pass

    @abstractmethod
    async def file_exists(self, file_path: str, version: Optional[str] = None) -> bool:
        """
        Check if file exists

        Args:
            file_path: Relative path to file within sandbox
            version: Optional version identifier

        Returns:
            True if file exists, False otherwise
        """
        pass

    @abstractmethod
    async def create_version(self, version: str, source_version: Optional[str] = None) -> bool:
        """
        Create a new version snapshot

        Args:
            version: Version identifier (e.g., "v1", "v2")
            source_version: Optional source version to copy from

        Returns:
            True if version created successfully, False otherwise
        """
        pass

    @abstractmethod
    async def list_versions(self) -> List[str]:
        """
        List all available versions

        Returns:
            List of version identifiers (e.g., ["v1", "v2", "v3"])
        """
        pass

    @abstractmethod
    async def get_version_metadata(self, version: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific version

        Args:
            version: Version identifier

        Returns:
            Dictionary with version metadata:
            - created_at: Creation timestamp
            - file_count: Number of files in version
            - total_size: Total size in bytes
        """
        pass

    @abstractmethod
    async def switch_version(self, version: str) -> bool:
        """
        Switch current version to a specific version

        Args:
            version: Version identifier to switch to

        Returns:
            True if switch successful, False otherwise
        """
        pass

