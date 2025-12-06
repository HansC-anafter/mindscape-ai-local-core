"""
Data Source Overlay Service

Handles data source overlay logic for workspace-specific data source customization:
1. Data source binding (which data sources are available in workspace)
2. Access mode override (can only be more restrictive, not less)
3. Display name override
4. Enabled/disabled status

Security rule: Overrides can only be more restrictive, never more permissive.
Access mode design is abstract to align with future RBAC system.
"""

import logging
from typing import List, Optional, Dict, Any
from enum import Enum

from backend.app.models.data_source import DataSource
from backend.app.models.workspace_resource_binding import ResourceType, AccessMode
from backend.app.services.stores.workspace_resource_binding_store import WorkspaceResourceBindingStore

logger = logging.getLogger(__name__)


class AccessModeHierarchy(str, Enum):
    """
    Access mode hierarchy for validation

    More restrictive = fewer permissions:
    - read: Only read access
    - write: Read + write access
    - admin: Full access (read + write + configure)
    """
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class DataSourceOverlayService:
    """
    Service for applying workspace overlay to data sources
    """

    def __init__(self):
        """Initialize the service"""
        self.binding_store = WorkspaceResourceBindingStore()

    def _get_access_mode_hierarchy(self) -> Dict[str, int]:
        """
        Get access mode hierarchy (for comparison)

        Returns:
            Dict mapping access mode to numeric value (higher = more permissions)
        """
        return {
            AccessModeHierarchy.READ: 1,
            AccessModeHierarchy.WRITE: 2,
            AccessModeHierarchy.ADMIN: 3,
        }

    def _is_more_restrictive(self, original: str, override: str) -> bool:
        """
        Check if override access mode is more restrictive than original

        More restrictive means lower access mode (fewer permissions).

        Args:
            original: Original access mode
            override: Override access mode

        Returns:
            True if override is more restrictive, False otherwise
        """
        hierarchy = self._get_access_mode_hierarchy()
        original_level = hierarchy.get(original.lower(), 3)  # Default to admin if unknown
        override_level = hierarchy.get(override.lower(), 1)  # Default to read if unknown

        # More restrictive = lower level
        return override_level < original_level

    def _is_more_permissive(self, original: str, override: str) -> bool:
        """
        Check if override access mode is more permissive than original

        More permissive means higher access mode (more permissions).

        Args:
            original: Original access mode
            override: Override access mode

        Returns:
            True if override is more permissive, False otherwise
        """
        hierarchy = self._get_access_mode_hierarchy()
        original_level = hierarchy.get(original.lower(), 1)  # Default to read if unknown
        override_level = hierarchy.get(override.lower(), 3)  # Default to admin if unknown

        # More permissive = higher level
        return override_level > original_level

    def validate_access_mode_override(
        self,
        original_access_mode: str,
        override_access_mode: str
    ) -> bool:
        """
        Validate that access mode override is more restrictive (not more permissive)

        Security rule: Overrides can only be more restrictive, never more permissive.

        Args:
            original_access_mode: Original access mode
            override_access_mode: Proposed override access mode

        Returns:
            True if override is valid (more restrictive or same), False if invalid (more permissive)
        """
        original = original_access_mode.lower()
        override = override_access_mode.lower()

        # Same level is allowed (no change)
        if original == override:
            return True

        # More restrictive is allowed
        if self._is_more_restrictive(original, override):
            return True

        # More permissive is NOT allowed
        if self._is_more_permissive(original, override):
            logger.warning(
                f"Invalid access mode override: "
                f"cannot make {original} more permissive to {override}"
            )
            return False

        return True

    def apply_data_source_overlay(
        self,
        data_source: DataSource,
        workspace_id: str,
        default_access_mode: str = "read"
    ) -> Optional[DataSource]:
        """
        Apply workspace overlay to a data source

        This method:
        1. Checks if data source is bound to workspace
        2. Applies access mode override (if exists and valid)
        3. Applies display name override (if exists)
        4. Applies enabled/disabled status (if exists)

        Args:
            data_source: Original data source
            workspace_id: Workspace ID
            default_access_mode: Default access mode if no binding exists

        Returns:
            Modified data source with overlay applied, or None if data source is not bound
        """
        # Get workspace binding for this data source
        binding = self.binding_store.get_binding_by_resource(
            workspace_id=workspace_id,
            resource_type=ResourceType.DATA_SOURCE,
            resource_id=data_source.id
        )

        # If no binding, check if we should return None or use default
        # For now, we'll return the data source with default access mode
        # (This can be configured based on requirements)
        if not binding:
            # Option: Return None if strict binding is required
            # return None

            # Option: Return with default access mode (current implementation)
            # Create a view with default access mode
            try:
                overlay_data_source = data_source.model_copy()
            except AttributeError:
                # Fallback for Pydantic v1
                overlay_data_source = data_source.copy()
            return overlay_data_source

        overrides = binding.overrides or {}
        binding_access_mode = binding.access_mode.value

        # Step 1: Validate and apply access mode override
        # The binding's access_mode is the workspace-level restriction
        # We need to check if it's more restrictive than the original
        # For now, we'll use the binding's access_mode as the effective access mode
        # (The original data source doesn't have an access_mode field, so we use the binding's)

        # Step 2: Apply display name override (if exists)
        local_display_name = overrides.get("local_display_name")
        if local_display_name:
            try:
                data_source = data_source.model_copy(update={"name": local_display_name})
            except AttributeError:
                # Fallback for Pydantic v1
                data_source = data_source.copy(update={"name": local_display_name})
            logger.debug(
                f"Applied display name override for data source {data_source.id} in workspace {workspace_id}: "
                f"{data_source.name}"
            )

        # Step 3: Apply enabled/disabled status (if exists)
        local_enabled = overrides.get("local_enabled")
        if local_enabled is not None:
            try:
                data_source = data_source.model_copy(update={"is_active": local_enabled})
            except AttributeError:
                # Fallback for Pydantic v1
                data_source = data_source.copy(update={"is_active": local_enabled})
            logger.debug(
                f"Applied enabled override for data source {data_source.id} in workspace {workspace_id}: {local_enabled}"
            )

        # Step 4: Check local_access_mode override (if exists)
        local_access_mode = overrides.get("local_access_mode")
        if local_access_mode:
            # Validate that local_access_mode is not more permissive than binding's access_mode
            if not self.validate_access_mode_override(binding_access_mode, local_access_mode):
                # Invalid override: log warning and use binding's access_mode
                logger.warning(
                    f"Invalid access mode override for data source {data_source.id} in workspace {workspace_id}, "
                    f"using binding access mode {binding_access_mode}"
                )
                local_access_mode = binding_access_mode
        else:
            local_access_mode = binding_access_mode

        # Store effective access mode in a metadata field (for future RBAC integration)
        # Note: DataSource model doesn't have access_mode field, so we'll add it to config or create a view
        # For now, we'll add it to the config as metadata
        try:
            config = data_source.config.copy()
            config["_workspace_access_mode"] = local_access_mode
            data_source = data_source.model_copy(update={"config": config})
        except AttributeError:
            # Fallback for Pydantic v1
            config = data_source.config.copy()
            config["_workspace_access_mode"] = local_access_mode
            data_source = data_source.copy(update={"config": config})

        return data_source

    def apply_data_sources_overlay(
        self,
        data_sources: List[DataSource],
        workspace_id: str,
        default_access_mode: str = "read"
    ) -> List[DataSource]:
        """
        Apply workspace overlay to a list of data sources

        Args:
            data_sources: List of original data sources
            workspace_id: Workspace ID
            default_access_mode: Default access mode if no binding exists

        Returns:
            List of data sources with overlay applied (filtered and modified)
        """
        result = []
        for data_source in data_sources:
            overlay_data_source = self.apply_data_source_overlay(
                data_source, workspace_id, default_access_mode
            )
            if overlay_data_source:
                result.append(overlay_data_source)

        return result

    def get_workspace_data_source_bindings(
        self,
        workspace_id: str
    ) -> Dict[str, Any]:
        """
        Get all data source bindings for a workspace

        Args:
            workspace_id: Workspace ID

        Returns:
            Dict mapping data_source_id to binding overrides
        """
        bindings = self.binding_store.list_bindings_by_workspace(
            workspace_id=workspace_id,
            resource_type=ResourceType.DATA_SOURCE
        )

        result = {}
        for binding in bindings:
            result[binding.resource_id] = {
                "access_mode": binding.access_mode.value,
                "overrides": binding.overrides,
            }

        return result

