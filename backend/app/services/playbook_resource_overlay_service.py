"""
Playbook Resource Overlay Service

Handles resource storage and retrieval with support for:
1. Shared resources (based on playbook scope: system/tenant/profile)
2. Workspace overlay (from workspace_resource_bindings)
3. Backward compatibility (fallback to old workspace paths)

Reading strategy:
- First check new path (shared + overlay)
- Fallback to old workspace path

Writing strategy:
- Only write to new path (shared/overlay path)
"""

import logging
import json
from typing import List, Optional, Dict, Any
from pathlib import Path

from backend.app.models.workspace import Workspace
from backend.app.models.playbook import Playbook, PlaybookMetadata
from backend.app.models.workspace_resource_binding import ResourceType
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.workspace_resource_binding_store import (
    WorkspaceResourceBindingStore,
)

logger = logging.getLogger(__name__)


class PlaybookResourceOverlayService:
    """
    Service for managing playbook resources with overlay support
    """

    def __init__(self, store: Optional[MindscapeStore] = None):
        """
        Initialize the service

        Args:
            store: MindscapeStore instance
        """
        self.store = store or MindscapeStore()
        self.binding_store = WorkspaceResourceBindingStore()

    def _get_shared_resource_path(
        self,
        playbook: Playbook,
        resource_type: str,
        workspace: Optional[Workspace] = None,
    ) -> Optional[Path]:
        """
        Get shared resource path based on playbook scope

        Args:
            playbook: Playbook instance
            resource_type: Resource type (e.g., 'chapters', 'lessons')
            workspace: Optional workspace (for tenant/profile scope resolution)

        Returns:
            Path to shared resources directory, or None if workspace-scoped
        """
        scope_level = playbook.metadata.get_scope_level()

        # Workspace-scoped playbooks don't have shared resources
        if scope_level == "workspace":
            return None

        # System scope: use system playbook directory
        if scope_level == "system":
            # System playbooks are typically in backend/i18n/playbooks or NPM packages
            # For resources, we'll use a shared system directory
            base_dir = Path(__file__).parent.parent.parent.parent
            shared_path = (
                base_dir
                / "data"
                / "shared"
                / "playbooks"
                / playbook.metadata.playbook_code
                / "resources"
                / resource_type
            )
            return shared_path

        # Tenant scope: use tenant shared directory
        if scope_level == "tenant" and workspace:
            tenant_id = (
                workspace.tenant_id
                if hasattr(workspace, "tenant_id") and workspace.tenant_id
                else None
            )
            if tenant_id:
                base_dir = Path(__file__).parent.parent.parent.parent
                shared_path = (
                    base_dir
                    / "data"
                    / "tenants"
                    / tenant_id
                    / "playbooks"
                    / playbook.metadata.playbook_code
                    / "resources"
                    / resource_type
                )
                return shared_path

        # Profile scope: use profile shared directory
        if scope_level == "profile" and workspace:
            profile_id = (
                workspace.profile_id
                if hasattr(workspace, "profile_id") and workspace.profile_id
                else None
            )
            if profile_id:
                base_dir = Path(__file__).parent.parent.parent.parent
                shared_path = (
                    base_dir
                    / "data"
                    / "profiles"
                    / profile_id
                    / "playbooks"
                    / playbook.metadata.playbook_code
                    / "resources"
                    / resource_type
                )
                return shared_path

        return None

    def _get_workspace_resource_path(
        self, workspace: Workspace, playbook_code: str, resource_type: str
    ) -> Path:
        """
        Get workspace-specific resource path (old path for backward compatibility)

        Args:
            workspace: Workspace instance
            playbook_code: Playbook code
            resource_type: Resource type

        Returns:
            Path to workspace resources directory
        """
        if workspace.storage_base_path:
            base_path = Path(workspace.storage_base_path)
        else:
            import os

            base_path = Path(os.path.expanduser("~/Documents/Mindscape"))

        resource_path = (
            base_path / "playbooks" / playbook_code / "resources" / resource_type
        )
        return resource_path

    def _get_overlay_path(
        self, workspace: Workspace, playbook_code: str, resource_type: str
    ) -> Path:
        """
        Get workspace overlay path for resources

        Args:
            workspace: Workspace instance
            playbook_code: Playbook code
            resource_type: Resource type

        Returns:
            Path to workspace overlay directory
        """
        if workspace.storage_base_path:
            base_path = Path(workspace.storage_base_path)
        else:
            import os

            base_path = Path(os.path.expanduser("~/Documents/Mindscape"))

        overlay_path = (
            base_path
            / "workspace_overlays"
            / "playbooks"
            / playbook_code
            / "resources"
            / resource_type
        )
        return overlay_path

    def _merge_resource_with_overlay(
        self, base_resource: Dict[str, Any], overlay: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Merge base resource with overlay

        Args:
            base_resource: Base resource data
            overlay: Overlay data from workspace_resource_binding

        Returns:
            Merged resource data
        """
        # Deep merge: overlay takes precedence
        merged = base_resource.copy()

        # Apply overlay fields
        for key, value in overlay.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                # Recursive merge for nested dicts
                merged[key] = self._merge_resource_with_overlay(merged[key], value)
            else:
                merged[key] = value

        return merged

    async def get_resource(
        self,
        workspace_id: str,
        playbook_code: str,
        resource_type: str,
        resource_id: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a resource with overlay support

        Reading strategy:
        1. Check workspace overlay path (new path)
        2. Check shared resource path (if template playbook)
        3. Fallback to old workspace path (backward compatibility)

        Args:
            workspace_id: Workspace ID
            playbook_code: Playbook code
            resource_type: Resource type
            resource_id: Resource ID

        Returns:
            Resource data with overlay applied, or None if not found
        """
        workspace = await self.store.get_workspace(workspace_id)
        if not workspace:
            logger.warning(f"Workspace {workspace_id} not found")
            return None

        # Get playbook to determine scope
        from backend.app.services.playbook_service import PlaybookService

        playbook_service = PlaybookService(store=self.store)
        playbook = await playbook_service.get_playbook(
            playbook_code, workspace_id=workspace_id
        )
        if not playbook:
            logger.warning(f"Playbook {playbook_code} not found")
            return None

        # Strategy 1: Check workspace overlay path (new path)
        overlay_path = self._get_overlay_path(workspace, playbook_code, resource_type)
        overlay_file = overlay_path / f"{resource_id}.json"
        if overlay_file.exists():
            try:
                with open(overlay_file, "r", encoding="utf-8") as f:
                    overlay_data = json.load(f)
                    logger.debug(f"Found resource in overlay path: {overlay_file}")
                    return overlay_data
            except Exception as e:
                logger.warning(
                    f"Failed to load resource from overlay path {overlay_file}: {e}"
                )

        # Strategy 2: Check shared resource path (if template playbook)
        shared_path = self._get_shared_resource_path(playbook, resource_type, workspace)
        if shared_path:
            shared_file = shared_path / f"{resource_id}.json"
            if shared_file.exists():
                try:
                    with open(shared_file, "r", encoding="utf-8") as f:
                        shared_data = json.load(f)

                    # Apply overlay from workspace_resource_binding
                    binding = self.binding_store.get_binding_by_resource(
                        workspace_id=workspace_id,
                        resource_type=ResourceType.PLAYBOOK,
                        resource_id=playbook_code,
                    )

                    if binding and binding.overrides:
                        # Check if there's a resource-specific overlay
                        resource_overlay = (
                            binding.overrides.get("resources", {})
                            .get(resource_type, {})
                            .get(resource_id, {})
                        )
                        if resource_overlay:
                            shared_data = self._merge_resource_with_overlay(
                                shared_data, resource_overlay
                            )

                    logger.debug(f"Found resource in shared path: {shared_file}")
                    return shared_data
                except Exception as e:
                    logger.warning(
                        f"Failed to load resource from shared path {shared_file}: {e}"
                    )

        # Strategy 3: Fallback to old workspace path (backward compatibility)
        old_path = self._get_workspace_resource_path(
            workspace, playbook_code, resource_type
        )
        old_file = old_path / f"{resource_id}.json"
        if old_file.exists():
            try:
                with open(old_file, "r", encoding="utf-8") as f:
                    old_data = json.load(f)
                    logger.debug(f"Found resource in old workspace path: {old_file}")
                    return old_data
            except Exception as e:
                logger.warning(f"Failed to load resource from old path {old_file}: {e}")

        return None

    async def list_resources(
        self, workspace_id: str, playbook_code: str, resource_type: str
    ) -> List[Dict[str, Any]]:
        """
        List all resources of a type with overlay support

        Args:
            workspace_id: Workspace ID
            playbook_code: Playbook code
            resource_type: Resource type

        Returns:
            List of resources with overlay applied
        """
        workspace = await self.store.get_workspace(workspace_id)
        if not workspace:
            logger.warning(f"Workspace {workspace_id} not found")
            return []

        # Get playbook to determine scope
        from backend.app.services.playbook_service import PlaybookService

        playbook_service = PlaybookService(store=self.store)
        playbook = await playbook_service.get_playbook(
            playbook_code, workspace_id=workspace_id
        )
        if not playbook:
            logger.warning(f"Playbook {playbook_code} not found")
            return []

        resources = {}
        resource_ids = set()

        # Strategy 1: Load from shared path (if template playbook)
        shared_path = self._get_shared_resource_path(playbook, resource_type, workspace)
        if shared_path and shared_path.exists():
            for resource_file in shared_path.glob("*.json"):
                try:
                    resource_id = resource_file.stem
                    with open(resource_file, "r", encoding="utf-8") as f:
                        resource_data = json.load(f)
                        resources[resource_id] = resource_data
                        resource_ids.add(resource_id)
                except Exception as e:
                    logger.warning(f"Failed to load resource {resource_file}: {e}")

        # Strategy 2: Load from workspace overlay path (new path)
        overlay_path = self._get_overlay_path(workspace, playbook_code, resource_type)
        if overlay_path.exists():
            for resource_file in overlay_path.glob("*.json"):
                try:
                    resource_id = resource_file.stem
                    with open(resource_file, "r", encoding="utf-8") as f:
                        overlay_data = json.load(f)
                        # If exists in shared, merge; otherwise use overlay as base
                        if resource_id in resources:
                            resources[resource_id] = self._merge_resource_with_overlay(
                                resources[resource_id], overlay_data
                            )
                        else:
                            resources[resource_id] = overlay_data
                        resource_ids.add(resource_id)
                except Exception as e:
                    logger.warning(f"Failed to load resource {resource_file}: {e}")

        # Strategy 3: Fallback to old workspace path (backward compatibility)
        old_path = self._get_workspace_resource_path(
            workspace, playbook_code, resource_type
        )
        if old_path.exists():
            for resource_file in old_path.glob("*.json"):
                try:
                    resource_id = resource_file.stem
                    # Only add if not already found in new paths
                    if resource_id not in resource_ids:
                        with open(resource_file, "r", encoding="utf-8") as f:
                            old_data = json.load(f)
                            resources[resource_id] = old_data
                            resource_ids.add(resource_id)
                except Exception as e:
                    logger.warning(f"Failed to load resource {resource_file}: {e}")

        # Apply overlay from workspace_resource_binding
        binding = self.binding_store.get_binding_by_resource(
            workspace_id=workspace_id,
            resource_type=ResourceType.PLAYBOOK,
            resource_id=playbook_code,
        )

        if binding and binding.overrides:
            resource_overlays = binding.overrides.get("resources", {}).get(
                resource_type, {}
            )
            for resource_id, overlay in resource_overlays.items():
                if resource_id in resources:
                    resources[resource_id] = self._merge_resource_with_overlay(
                        resources[resource_id], overlay
                    )

        # Convert to list and sort
        resource_list = list(resources.values())
        return sorted(
            resource_list, key=lambda x: x.get("created_at", ""), reverse=True
        )

    async def save_resource(
        self,
        workspace_id: str,
        playbook_code: str,
        resource_type: str,
        resource: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Save a resource (only to new path)

        Writing strategy:
        - Always write to workspace overlay path (new path)
        - Never write to shared path or old workspace path

        Args:
            workspace_id: Workspace ID
            playbook_code: Playbook code
            resource_type: Resource type
            resource: Resource data

        Returns:
            Saved resource data
        """
        workspace = await self.store.get_workspace(workspace_id)
        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")

        resource_id = resource.get("id")
        if not resource_id:
            raise ValueError("Resource must have an 'id' field")

        # Always write to workspace overlay path (new path)
        overlay_path = self._get_overlay_path(workspace, playbook_code, resource_type)
        overlay_path.mkdir(parents=True, exist_ok=True)

        overlay_file = overlay_path / f"{resource_id}.json"

        # Preserve timestamps if updating
        if overlay_file.exists():
            try:
                with open(overlay_file, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                    resource["created_at"] = resource.get(
                        "created_at", existing_data.get("created_at")
                    )
            except:
                pass

        # Update updated_at
        from datetime import datetime

        resource["updated_at"] = datetime.utcnow().isoformat()

        # Write to overlay path
        with open(overlay_file, "w", encoding="utf-8") as f:
            json.dump(resource, f, indent=2, ensure_ascii=False)

        logger.info(
            f"Saved resource {resource_type}/{resource_id} to overlay path: {overlay_file}"
        )
        return resource

    async def delete_resource(
        self,
        workspace_id: str,
        playbook_code: str,
        resource_type: str,
        resource_id: str,
    ) -> bool:
        """
        Delete a resource

        Args:
            workspace_id: Workspace ID
            playbook_code: Playbook code
            resource_type: Resource type
            resource_id: Resource ID

        Returns:
            True if deleted, False if not found
        """
        workspace = await self.store.get_workspace(workspace_id)
        if not workspace:
            return False

        # Try to delete from overlay path (new path)
        overlay_path = self._get_overlay_path(workspace, playbook_code, resource_type)
        overlay_file = overlay_path / f"{resource_id}.json"
        if overlay_file.exists():
            overlay_file.unlink()
            logger.info(
                f"Deleted resource {resource_type}/{resource_id} from overlay path"
            )
            return True

        # Try to delete from old workspace path (backward compatibility)
        old_path = self._get_workspace_resource_path(
            workspace, playbook_code, resource_type
        )
        old_file = old_path / f"{resource_id}.json"
        if old_file.exists():
            old_file.unlink()
            logger.info(f"Deleted resource {resource_type}/{resource_id} from old path")
            return True

        return False
