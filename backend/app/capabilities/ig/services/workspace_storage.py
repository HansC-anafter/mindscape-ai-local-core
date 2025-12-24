"""
Workspace Storage for IG Capability

Provides unified storage interface for IG content, supporting multiple backends
(local filesystem, Obsidian, cloud storage).
"""
import logging
import os
from pathlib import Path
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    """Abstract base class for storage backends"""

    @abstractmethod
    def get_path(self, relative_path: str) -> Path:
        """Get absolute path for a relative path within the workspace"""
        pass

    @abstractmethod
    def exists(self, relative_path: str) -> bool:
        """Check if a path exists"""
        pass

    @abstractmethod
    def mkdir(self, relative_path: str, parents: bool = True) -> Path:
        """Create directory"""
        pass


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend"""

    def __init__(self, base_path: Path):
        self.base_path = base_path.resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def get_path(self, relative_path: str) -> Path:
        """Get absolute path for a relative path"""
        return self.base_path / relative_path

    def exists(self, relative_path: str) -> bool:
        """Check if a path exists"""
        return self.get_path(relative_path).exists()

    def mkdir(self, relative_path: str, parents: bool = True) -> Path:
        """Create directory"""
        path = self.get_path(relative_path)
        path.mkdir(parents=parents, exist_ok=True)
        return path


class ObsidianStorageBackend(StorageBackend):
    """Obsidian vault storage backend (for backward compatibility)"""

    def __init__(self, vault_path: str):
        self.vault_path = Path(vault_path).expanduser().resolve()
        if not self.vault_path.exists():
            raise ValueError(f"Obsidian vault path does not exist: {vault_path}")

    def get_path(self, relative_path: str) -> Path:
        """Get absolute path within Obsidian vault"""
        # Map IG paths to Obsidian structure
        if relative_path.startswith("ig/"):
            relative_path = relative_path.replace("ig/", "IG/", 1)
        return self.vault_path / relative_path

    def exists(self, relative_path: str) -> bool:
        """Check if a path exists"""
        return self.get_path(relative_path).exists()

    def mkdir(self, relative_path: str, parents: bool = True) -> Path:
        """Create directory"""
        path = self.get_path(relative_path)
        path.mkdir(parents=parents, exist_ok=True)
        return path


class WorkspaceStorage:
    """
    Unified workspace storage interface for capability data

    Provides a consistent API for accessing workspace storage, regardless of
    the underlying storage backend (local filesystem, Obsidian, cloud storage).

    Architecture Model:
    - Each capability has its own data directory: {tenant_id}/{workspace_id}/{capability_code}/
    - This follows the capability pack architecture where each capability
      manages its own assets and data independently.
    - Control plane directories: runs/, artifacts/, logs/ for audit, billing, and recovery.

    Security:
    - workspace_path is deprecated for enterprise/multi-tenant mode
    - Use Workspace.storage_root_ref (managed config) instead
    - workspace_path only allowed in migration/single-user mode
    """

    def __init__(
        self,
        workspace_id: str,
        capability_code: str,
        storage_backend: str = "auto",
        custom_path: Optional[str] = None
    ):
        """
        Initialize workspace storage for a capability

        Args:
            workspace_id: Workspace identifier
            capability_code: Capability code (e.g., "ig", "content", "web_generation")
            storage_backend: Storage backend type ("auto", "local", "obsidian")
            custom_path: Custom storage path (for "obsidian" backend or custom local path)
        """
        self.workspace_id = workspace_id
        self.capability_code = capability_code
        self.backend = self._initialize_backend(storage_backend, custom_path)

    def _initialize_backend(
        self,
        storage_backend: str,
        custom_path: Optional[str]
    ) -> StorageBackend:
        """Initialize storage backend"""
        if storage_backend == "obsidian" or custom_path:
            if not custom_path:
                raise ValueError("custom_path is required for Obsidian backend")
            return ObsidianStorageBackend(custom_path)

        elif storage_backend == "local" or storage_backend == "auto":
            # Use default local storage
            # Architecture: {tenant_id}/{workspace_id}/{capability_code}/
            # For now, tenant_id is optional (single-tenant mode)
            storage_root = os.getenv(
                "WORKSPACE_STORAGE_ROOT",
                Path.home() / ".mindscape" / "workspaces"
            )
            tenant_id = os.getenv("TENANT_ID")  # Optional, for multi-tenant
            if tenant_id:
                base_path = Path(storage_root) / tenant_id / self.workspace_id / self.capability_code
            else:
                base_path = Path(storage_root) / self.workspace_id / self.capability_code
            return LocalStorageBackend(base_path)

        else:
            raise ValueError(f"Unknown storage backend: {storage_backend}")

    def get_capability_root(self) -> Path:
        """Get root path for capability data directory"""
        return self.backend.get_path("")

    def get_ig_root(self) -> Path:
        """Get root path for IG content (deprecated, use get_capability_root)"""
        return self.get_capability_root()

    def get_posts_path(self) -> Path:
        """Get path for IG posts directory"""
        path = self.backend.get_path("posts")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_post_path(self, post_slug: str, date: Optional[str] = None) -> Path:
        """
        Get path for a specific post

        Args:
            post_slug: Post slug identifier
            date: Optional date in YYYY-MM-DD format

        Returns:
            Path to post directory
        """
        if date:
            folder_name = f"{date}_{post_slug}"
        else:
            folder_name = post_slug

        path = self.get_posts_path() / folder_name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_post_assets_path(self, post_slug: str, date: Optional[str] = None) -> Path:
        """Get path for post assets directory"""
        post_path = self.get_post_path(post_slug, date)
        assets_path = post_path / "assets"
        assets_path.mkdir(parents=True, exist_ok=True)
        return assets_path

    def get_series_path(self) -> Path:
        """Get path for IG series directory"""
        path = self.backend.get_path("series")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_templates_path(self) -> Path:
        """Get path for IG templates directory"""
        path = self.backend.get_path("templates")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_config_path(self) -> Path:
        """Get path for IG config directory"""
        path = self.backend.get_path("config")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_hashtag_config_path(self) -> Path:
        """Get path for hashtag configuration file"""
        return self.get_config_path() / "hashtag_groups.json"

    def get_blocked_hashtags_path(self) -> Path:
        """Get path for blocked hashtags file"""
        return self.get_config_path() / "blocked_hashtags.json"

    def get_runs_path(self) -> Path:
        """Get path for runs directory (control plane)"""
        path = self.backend.get_path("runs")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_run_path(self, run_id: str) -> Path:
        """Get path for a specific run directory"""
        path = self.get_runs_path() / run_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_artifacts_path(self) -> Path:
        """Get path for artifacts directory (control plane)"""
        path = self.backend.get_path("artifacts")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_artifact_path(self, artifact_id: str) -> Path:
        """Get path for a specific artifact directory"""
        path = self.get_artifacts_path() / artifact_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_logs_path(self) -> Path:
        """Get path for logs directory (control plane)"""
        path = self.backend.get_path("logs")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_manifest_path(self) -> Path:
        """Get path for capability manifest file"""
        return self.backend.get_path("manifest.json")

    @classmethod
    def from_workspace_path(
        cls,
        workspace_id: str,
        capability_code: str,
        workspace_path: str,
        allow_custom_path: bool = False
    ) -> "WorkspaceStorage":
        """
        Create WorkspaceStorage from a custom workspace path

        ⚠️ SECURITY WARNING: This method is deprecated for enterprise/multi-tenant mode.
        Use Workspace.storage_root_ref (managed config) instead.

        This method supports backward compatibility with existing code that
        uses workspace_path parameter. Only allowed in migration/single-user mode.

        Args:
            workspace_id: Workspace identifier
            capability_code: Capability code (e.g., "ig")
            workspace_path: Custom workspace path (can be Obsidian vault or any directory)
            allow_custom_path: Whether to allow custom path (should be False in enterprise mode)

        Returns:
            WorkspaceStorage instance

        Raises:
            ValueError: If allow_custom_path is False (enterprise mode)
        """
        if not allow_custom_path:
            raise ValueError(
                "workspace_path is not allowed in enterprise/multi-tenant mode. "
                "Use Workspace.storage_root_ref (managed config) instead."
            )

        # Detect if it's an Obsidian vault (check for .obsidian folder)
        vault_path = Path(workspace_path).expanduser().resolve()
        if (vault_path / ".obsidian").exists():
            return cls(workspace_id, capability_code, storage_backend="obsidian", custom_path=str(vault_path))
        else:
            # Treat as custom local path
            # Architecture: custom_path/{capability_code}/
            backend = LocalStorageBackend(vault_path / capability_code)
            storage = cls(workspace_id, capability_code, storage_backend="local")
            storage.backend = backend
            return storage

