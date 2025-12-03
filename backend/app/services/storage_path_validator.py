"""
Storage Path Validator Service

Validates storage paths for Docker container persistence and provides helpful error messages.
Handles allowed directories validation and path security checks.
"""

import logging
import re
import os
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


class StoragePathValidator:
    """Validate storage paths for Docker container persistence"""

    @staticmethod
    def get_docker_mounted_paths() -> List[str]:
        """
        Get list of Docker mounted paths for persistence validation

        These paths are mounted in docker-compose.yml and will persist to host:
        - /app/data (mapped to ./data on host)
        - /app/backend (mapped to ./backend on host)
        - /app/logs (mapped to ./logs on host)
        - /host/documents (optional, mapped to ${HOME}/Documents on host)

        Note: /app/backend/data is valid because /app/backend is mounted.

        Returns:
            List of mounted path prefixes
        """
        return [
            "/app/data",
            "/app/backend",
            "/app/logs",
            "/host/documents"
        ]

    @staticmethod
    def validate_path_in_mounted_volumes(path: Path) -> Tuple[bool, Optional[str]]:
        """
        Validate path is within Docker mounted volumes for persistence

        Args:
            path: Path to validate

        Returns:
            (is_valid, suggestion_message)
            - is_valid: True if path is within mounted volumes
            - suggestion_message: Suggested correct path if invalid, None if valid
        """
        resolved_path = path.resolve()
        path_str = str(resolved_path)
        mounted_paths = StoragePathValidator.get_docker_mounted_paths()

        # Check if path is within any mounted volume
        for mounted_path in mounted_paths:
            mounted_path_obj = Path(mounted_path)
            try:
                if resolved_path.is_relative_to(mounted_path_obj):
                    return True, None
            except AttributeError:
                # Python < 3.9 manual check
                try:
                    resolved_path.relative_to(mounted_path_obj)
                    return True, None
                except ValueError:
                    continue

        # Path is not in mounted volumes, provide helpful suggestions
        if "/app/backend/data" in path_str:
            suggested_path = path_str.replace("/app/backend/data", "/app/data", 1)
            suggestion = f"Suggested path: {suggested_path} (mapped to ./data on host)"
        elif path_str.startswith("/app/"):
            suggestion = (
                f"Please use /app/data/workspaces/... (mapped to ./data/workspaces/... on host) "
                f"or /app/backend/data/workspaces/... (mapped to ./backend/data/workspaces/... on host)"
            )
        elif path_str.startswith("/Users/") or path_str.startswith("/home/"):
            suggestion = (
                f"This is a host path. To use it, mount it in docker-compose.yml:\n"
                f"  - {path_str}:/host/custom:rw\n"
                f"Then use /host/custom as the storage path."
            )
        elif re.match(r'^[A-Za-z]:\\', path_str):
            path_str_normalized = path_str.replace('\\', '/')
            suggestion = (
                f"This is a Windows host path. To use it, mount it in docker-compose.yml:\n"
                f"  - {path_str_normalized}:/host/custom:rw\n"
                f"Then use /host/custom as the storage path."
            )
        else:
            suggestion = (
                f"Please use /app/data/workspaces/... for persistence, "
                f"or mount your custom path in docker-compose.yml first"
            )

        return False, suggestion

    @staticmethod
    def validate_and_check_host_path(path_str: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate path and check if it's a host path that needs mounting

        Args:
            path_str: Path string to validate

        Returns:
            (is_valid, error_message, host_path_hint)
            - is_valid: True if path is valid and accessible
            - error_message: Error message if invalid
            - host_path_hint: Hint for mounting host path if needed
        """
        requested_path = Path(path_str).expanduser().resolve()

        # Check if path exists in container (might be a host path that's not mounted)
        if not requested_path.exists():
            path_str_resolved = str(requested_path)

            # Check if it looks like a host path (Mac/Windows)
            is_host_path = False
            host_path_hint = ""

            if path_str_resolved.startswith('/Users/') or path_str_resolved.startswith('/home/'):
                is_host_path = True
                host_path_hint = (
                    f"\n\nThis appears to be a host path. To use this path, you need to mount it in docker-compose.yml:\n"
                    f"  - {path_str_resolved}:/host/custom:rw\n\n"
                    f"Then use /host/custom as the storage path in the container."
                )
            elif re.match(r'^[A-Za-z]:\\', path_str_resolved):
                is_host_path = True
                path_str_resolved_normalized = path_str_resolved.replace('\\', '/')
                host_path_hint = (
                    f"\n\nThis appears to be a Windows host path. To use this path, you need to mount it in docker-compose.yml:\n"
                    f"  - {path_str_resolved_normalized}:/host/custom:rw\n\n"
                    f"Then use /host/custom as the storage path in the container."
                )

            if is_host_path:
                error_message = (
                    f"Storage path {path_str} does not exist in the Docker container.{host_path_hint}\n\n"
                    f"Alternatively, use a path within already mounted volumes:\n"
                    f"  - /app/data/workspaces/... (mapped to ./data/workspaces/... on host)\n"
                    f"  - /app/backend/data/workspaces/... (mapped to ./backend/data/workspaces/... on host)"
                )
                return False, error_message, host_path_hint

        # Validate path is within Docker mounted volumes for persistence
        is_in_mounted_volume, volume_suggestion = StoragePathValidator.validate_path_in_mounted_volumes(requested_path)
        if not is_in_mounted_volume:
            error_message = (
                f"Storage path {path_str} is not within a mounted Docker volume and will not persist to host. "
                f"{volume_suggestion}\n\n"
                f"To use a custom host path, mount it in docker-compose.yml first, then use the container path."
            )
            return False, error_message, None

        return True, None, None

    @staticmethod
    def validate_path_in_allowed_directories(
        path: Path,
        allowed_directories: List[str]
    ) -> bool:
        """
        Validate path is within allowed directories (prevent directory traversal)

        Uses Path.resolve() and validates resolved_path is under allowed directories

        Args:
            path: Path to validate
            allowed_directories: List of allowed directories

        Returns:
            True if path is within allowed directories, False otherwise
        """
        resolved_path = path.resolve()

        for allowed_dir in allowed_directories:
            allowed_path = Path(allowed_dir).expanduser().resolve()

            try:
                if resolved_path.is_relative_to(allowed_path):
                    return True
            except AttributeError:
                try:
                    resolved_path.relative_to(allowed_path)
                    return True
                except ValueError:
                    continue

        return False

    @staticmethod
    def get_allowed_directories() -> List[str]:
        """
        Get allowed directories list

        Data source priority (per design requirements):
        1. Environment variable LOCAL_FS_ALLOWED_DIRS (comma-separated)
        2. ToolConnections (read local_filesystem tool config.allowed_directories from tool_connections table)
        3. ToolRegistry (read local_filesystem tool endpoint from tool registry, as fallback)

        Returns:
            List of allowed directories
        """
        allowed_dirs = []

        env_dirs = os.getenv("LOCAL_FS_ALLOWED_DIRS", "")
        if env_dirs:
            allowed_dirs.extend([d.strip() for d in env_dirs.split(",") if d.strip()])

        try:
            from ...services.tool_registry import ToolRegistryService
            tool_registry = ToolRegistryService()
            try:
                connections = tool_registry.get_connections_by_tool_type(
                    profile_id="default-user",
                    tool_type="local_filesystem"
                )
                connections = [conn for conn in connections if conn.is_active]
            except Exception as profile_error:
                logger.debug(f"Failed to get connections for default-user profile: {profile_error}")
                connections = []

            seen_dirs = set(allowed_dirs)
            for connection in connections:
                if connection.config and isinstance(connection.config, dict):
                    allowed_dirs_config = connection.config.get("allowed_directories", [])
                    if isinstance(allowed_dirs_config, list):
                        for dir_path in allowed_dirs_config:
                            if isinstance(dir_path, str) and dir_path.strip():
                                try:
                                    resolved_path = Path(dir_path).expanduser().resolve()
                                    if resolved_path.exists() and resolved_path.is_dir():
                                        dir_str = str(resolved_path)
                                        if dir_str not in seen_dirs:
                                            allowed_dirs.append(dir_str)
                                            seen_dirs.add(dir_str)
                                except Exception as e:
                                    logger.debug(f"Invalid directory path in tool_connection config: {dir_path}, error: {e}")
                                    pass
        except Exception as e:
            logger.warning(f"Failed to read from ToolConnections: {e}")

        if not allowed_dirs:
            try:
                from ...services.tool_registry import ToolRegistryService
                tool_registry = ToolRegistryService()
                tools = tool_registry.get_tools(enabled_only=False)

                seen_dirs = set(allowed_dirs)
                for tool in tools:
                    if tool.provider == "local_filesystem" and tool.endpoint:
                        try:
                            endpoint_path = Path(tool.endpoint).expanduser().resolve()
                            if endpoint_path.exists() and endpoint_path.is_dir():
                                dir_str = str(endpoint_path)
                                if dir_str not in seen_dirs:
                                    allowed_dirs.append(dir_str)
                                    seen_dirs.add(dir_str)
                        except Exception:
                            pass
            except Exception as e:
                logger.warning(f"Failed to read from ToolRegistry: {e}")

        return list(set(allowed_dirs))

