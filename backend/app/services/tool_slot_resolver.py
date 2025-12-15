"""
Tool Slot Resolver

Resolves logical tool slots to concrete tool IDs based on workspace/project-level mappings.

Resolution order:
1. Project-level mapping (if project_id provided)
2. Workspace-level mapping
3. System-level default mapping
4. Raise SlotNotFoundError if none found
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class SlotNotFoundError(Exception):
    """Raised when tool slot cannot be resolved to a tool ID"""
    pass


class ToolSlotResolver:
    """
    Resolves tool slots to concrete tool IDs

    Tool slots are logical identifiers (e.g., 'cms.footer.apply_style') that
    are bound to concrete tool IDs (e.g., 'wp-ets1.wordpress.update_footer')
    at the workspace or project level.
    """

    def __init__(self, store=None):
        """
        Initialize ToolSlotResolver

        Args:
            store: MindscapeStore instance (optional, will create if not provided)
        """
        if store is None:
            from backend.app.services.mindscape_store import MindscapeStore
            store = MindscapeStore()
        self.store = store

    async def resolve(
        self,
        slot: str,
        workspace_id: str,
        project_id: Optional[str] = None
    ) -> str:
        """
        Resolve tool slot to concrete tool_id

        Args:
            slot: Tool slot identifier (e.g., 'cms.footer.apply_style')
            workspace_id: Workspace ID
            project_id: Optional project ID (for project-level mapping)

        Returns:
            Concrete tool ID (e.g., 'wp-ets1.wordpress.update_footer')

        Raises:
            SlotNotFoundError: If slot cannot be resolved
        """
        try:
            # Try project-level mapping first (highest priority)
            if project_id:
                mapping = await self._get_mapping(slot, workspace_id, project_id)
                if mapping and mapping.get('enabled', True):
                    tool_id = mapping.get('tool_id')
                    if tool_id:
                        logger.info(f"Resolved slot '{slot}' to tool '{tool_id}' (project-level mapping)")
                        return tool_id

            # Try workspace-level mapping
            mapping = await self._get_mapping(slot, workspace_id, None)
            if mapping and mapping.get('enabled', True):
                tool_id = mapping.get('tool_id')
                if tool_id:
                    logger.info(f"Resolved slot '{slot}' to tool '{tool_id}' (workspace-level mapping)")
                    return tool_id

            # Try system-level default mapping (future: could come from playbook metadata)
            # For now, system defaults are not implemented

            # If slot looks like a concrete tool ID, return it as-is (backward compatibility)
            if self._looks_like_tool_id(slot):
                logger.info(f"Slot '{slot}' appears to be a concrete tool ID, using as-is")
                return slot

            # No mapping found
            project_msg = f"or project '{project_id}'" if project_id else ""
            raise SlotNotFoundError(
                f"Tool slot '{slot}' not found. "
                f"Please configure a mapping in workspace '{workspace_id}' {project_msg}"
            )

        except SlotNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error resolving tool slot '{slot}': {e}", exc_info=True)
            raise SlotNotFoundError(f"Failed to resolve tool slot '{slot}': {str(e)}")

    async def _get_mapping(
        self,
        slot: str,
        workspace_id: str,
        project_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get tool slot mapping from database

        Args:
            slot: Tool slot identifier
            workspace_id: Workspace ID
            project_id: Optional project ID

        Returns:
            Mapping dictionary with tool_id, priority, enabled, etc., or None if not found
        """
        try:
            from backend.app.services.stores.tool_slot_mappings_store import ToolSlotMappingsStore

            mappings_store = ToolSlotMappingsStore(self.store.db_path)
            mappings = mappings_store.get_mappings(
                slot=slot,
                workspace_id=workspace_id,
                project_id=project_id,
                enabled_only=True
            )

            if not mappings:
                return None

            # Sort by priority (higher priority first), then by created_at (newer first)
            mappings.sort(key=lambda m: (-m.get('priority', 0), m.get('created_at', datetime.min)))

            # Return highest priority mapping
            return mappings[0] if mappings else None

        except ImportError:
            # ToolSlotMappingsStore not yet implemented, return None
            logger.debug(f"ToolSlotMappingsStore not available, returning None for slot '{slot}'")
            return None
        except Exception as e:
            logger.warning(f"Failed to get mapping for slot '{slot}': {e}")
            return None

    def _looks_like_tool_id(self, slot: str) -> bool:
        """
        Check if slot looks like a concrete tool ID (for backward compatibility)

        Tool IDs typically follow patterns like:
        - connection_id.tool_type.tool_name (e.g., 'wp-ets1.wordpress.update_footer')
        - capability.tool_name (e.g., 'core_files.ocr_pdf')
        - filesystem_tool_name (e.g., 'filesystem_read_file')

        Slots typically follow patterns like:
        - category.subcategory.action (e.g., 'cms.footer.apply_style')

        Args:
            slot: String to check

        Returns:
            True if it looks like a tool ID, False if it looks like a slot
        """
        # Check if it starts with known tool prefixes (before checking dots)
        if slot.startswith('filesystem_') or slot.startswith('sandbox.'):
            return True

        # If it contains dots, check if it matches tool ID patterns
        if '.' not in slot:
            return False

        parts = slot.split('.')

        # Tool IDs usually have 2-3 parts
        # Slots usually have 3+ parts with descriptive names

        # Heuristic: if first part contains hyphens (common in connection IDs like 'wp-ets1'),
        # it's likely a tool ID
        if '-' in parts[0]:
            return True

        # Heuristic: if it has exactly 2 parts, check patterns
        if len(parts) == 2:
            # Known capability patterns (e.g., 'core_files.ocr_pdf')
            known_capabilities = ['core_files', 'filesystem', 'capability']
            if parts[0] in known_capabilities:
                return True

            # Known tool types (e.g., 'connection.wordpress')
            known_tool_types = ['wordpress', 'canva', 'slack', 'github', 'airtable', 'google_sheets', 'notion', 'mcp']
            if parts[1] in known_tool_types:
                return True

        # Heuristic: if it has 3 parts and first part has hyphen, it's likely tool_id
        # (e.g., 'wp-ets1.wordpress.update_footer')
        if len(parts) == 3 and '-' in parts[0]:
            return True

        # Default: assume it's a slot (more restrictive)
        # Slots typically have 3+ parts without hyphens
        return False


# Global instance
_resolver_instance: Optional[ToolSlotResolver] = None


def get_tool_slot_resolver(store=None) -> ToolSlotResolver:
    """
    Get global ToolSlotResolver instance

    Args:
        store: Optional MindscapeStore instance

    Returns:
        ToolSlotResolver instance
    """
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = ToolSlotResolver(store=store)
    return _resolver_instance

