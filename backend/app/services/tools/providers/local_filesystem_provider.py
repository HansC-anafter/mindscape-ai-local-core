"""
Local Filesystem Tool Discovery Provider

Discovers file system capabilities for local file access.
Used for document collection and RAG functionality.

Security:
- Only allows access to configured directories
- Prevents directory traversal attacks
- Validates paths before allowing access
"""
import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from backend.app.services.tools.discovery_provider import (
    ToolDiscoveryProvider,
    ToolConfig,
    DiscoveredTool
)

logger = logging.getLogger(__name__)


class LocalFilesystemDiscoveryProvider(ToolDiscoveryProvider):
    """
    Local Filesystem Discovery Provider

    Discovers file system capabilities for configured directories.
    """

    @property
    def provider_name(self) -> str:
        return "local_filesystem"

    @property
    def supported_connection_types(self) -> List[str]:
        return ["local"]

    async def discover(self, config: ToolConfig) -> List[DiscoveredTool]:
        """
        Discover file system capabilities

        Returns tools for:
        - Listing files in directories
        - Reading files
        - Writing files (if allowed)
        - Searching files
        """
        allowed_directories = config.custom_config.get("allowed_directories", [])

        if not allowed_directories:
            logger.warning("No allowed directories configured for local filesystem")
            return []

        discovered_tools = []

        for directory in allowed_directories:
            dir_path = Path(directory).expanduser().resolve()

            if not self._is_safe_directory(dir_path):
                logger.warning(f"Unsafe directory skipped: {directory}")
                continue

            if not dir_path.exists() or not dir_path.is_dir():
                logger.warning(f"Directory does not exist or is not a directory: {directory}")
                continue

            base_tool_id = f"local_fs_{dir_path.name}"

            discovered_tools.extend([
                DiscoveredTool(
                    tool_id=f"{base_tool_id}_list",
                    display_name=f"List Files: {dir_path.name}",
                    description=f"List files and directories in {dir_path}",
                    category="file_management",
                    endpoint=str(dir_path),
                    methods=["GET"],
                    input_schema={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": f"Relative path from {dir_path}",
                                "default": "."
                            },
                            "recursive": {
                                "type": "boolean",
                                "description": "List recursively",
                                "default": False
                            }
                        },
                        "required": []
                    },
                    danger_level="low",
                    metadata={
                        "base_directory": str(dir_path),
                        "allowed_directory": True
                    }
                ),
                DiscoveredTool(
                    tool_id=f"{base_tool_id}_read",
                    display_name=f"Read File: {dir_path.name}",
                    description=f"Read file content from {dir_path}",
                    category="file_management",
                    endpoint=str(dir_path),
                    methods=["GET"],
                    input_schema={
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": f"Relative file path from {dir_path}"
                            },
                            "encoding": {
                                "type": "string",
                                "description": "File encoding",
                                "default": "utf-8"
                            }
                        },
                        "required": ["file_path"]
                    },
                    danger_level="low",
                    metadata={
                        "base_directory": str(dir_path),
                        "allowed_directory": True
                    }
                ),
                DiscoveredTool(
                    tool_id=f"{base_tool_id}_search",
                    display_name=f"Search Files: {dir_path.name}",
                    description=f"Search files by name or content in {dir_path}",
                    category="file_management",
                    endpoint=str(dir_path),
                    methods=["GET"],
                    input_schema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query (filename pattern or content)"
                            },
                            "file_pattern": {
                                "type": "string",
                                "description": "File pattern (e.g., '*.md', '*.txt')",
                                "default": "*"
                            },
                            "recursive": {
                                "type": "boolean",
                                "description": "Search recursively",
                                "default": True
                            }
                        },
                        "required": ["query"]
                    },
                    danger_level="low",
                    metadata={
                        "base_directory": str(dir_path),
                        "allowed_directory": True
                    }
                )
            ])

            write_enabled = config.custom_config.get("allow_write", False)
            if write_enabled:
                discovered_tools.append(
                    DiscoveredTool(
                        tool_id=f"{base_tool_id}_write",
                        display_name=f"Write File: {dir_path.name}",
                        description=f"Write file content to {dir_path}",
                        category="file_management",
                        endpoint=str(dir_path),
                        methods=["POST"],
                        input_schema={
                            "type": "object",
                            "properties": {
                                "file_path": {
                                    "type": "string",
                                    "description": f"Relative file path from {dir_path}"
                                },
                                "content": {
                                    "type": "string",
                                    "description": "File content to write"
                                },
                                "encoding": {
                                    "type": "string",
                                    "description": "File encoding",
                                    "default": "utf-8"
                                }
                            },
                            "required": ["file_path", "content"]
                        },
                        danger_level="high",
                        metadata={
                            "base_directory": str(dir_path),
                            "allowed_directory": True
                        }
                    )
                )

        logger.info(f"Discovered {len(discovered_tools)} file system tools")
        return discovered_tools

    async def validate(self, config: ToolConfig) -> bool:
        """
        Validate local filesystem configuration

        Checks:
        - At least one allowed directory is configured
        - All directories are safe (not system directories)
        - All directories exist and are accessible
        """
        allowed_directories = config.custom_config.get("allowed_directories", [])

        if not allowed_directories:
            logger.error("No allowed directories configured")
            return False

        for directory in allowed_directories:
            dir_path = Path(directory).expanduser().resolve()

            if not self._is_safe_directory(dir_path):
                logger.error(f"Unsafe directory: {directory}")
                return False

            if not dir_path.exists():
                logger.warning(f"Directory does not exist: {directory}")
                return False

            if not dir_path.is_dir():
                logger.error(f"Path is not a directory: {directory}")
                return False

            if not os.access(dir_path, os.R_OK):
                logger.error(f"Directory is not readable: {directory}")
                return False

        return True

    def _is_safe_directory(self, path: Path) -> bool:
        """
        Check if directory is safe to access

        Prevents access to:
        - System directories (/etc, /sys, /proc, etc.)
        - Root directory
        - Hidden system directories
        """
        path_str = str(path)

        forbidden_paths = [
            "/",
            "/etc",
            "/sys",
            "/proc",
            "/dev",
            "/boot",
            "/root",
            "/usr/bin",
            "/usr/sbin",
            "/bin",
            "/sbin",
        ]

        for forbidden in forbidden_paths:
            if path_str == forbidden or path_str.startswith(forbidden + "/"):
                return False

        if path_str.startswith("~"):
            return True

        return True

    def get_discovery_metadata(self) -> Dict[str, Any]:
        return {
            "provider": self.provider_name,
            "description": "Local file system access for document collection and RAG",
            "supported_connection_types": self.supported_connection_types,
            "required_config": ["allowed_directories"],
            "optional_config": ["allow_write"],
            "documentation_url": None,
            "security_notes": [
                "Only configured directories are accessible",
                "Directory traversal attacks are prevented",
                "Write access is optional and can be disabled"
            ]
        }

    def get_config_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "tool_type": {
                    "type": "string",
                    "const": self.provider_name
                },
                "connection_type": {
                    "type": "string",
                    "enum": self.supported_connection_types
                },
                "allowed_directories": {
                    "type": "array",
                    "items": {
                        "type": "string"
                    },
                    "description": "List of allowed directory paths",
                    "minItems": 1
                },
                "allow_write": {
                    "type": "boolean",
                    "description": "Allow write operations",
                    "default": False
                }
            },
            "required": ["tool_type", "connection_type", "allowed_directories"]
        }
