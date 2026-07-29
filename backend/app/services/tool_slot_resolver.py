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
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ToolSlotResolution:
    """Immutable evidence returned by one admission-time slot lookup."""

    slot: str
    tool_id: str
    mapping_kind: str
    mapping_id: Optional[str] = None
    mapping_updated_at: Optional[str] = None
    project_id: Optional[str] = None


class SlotNotFoundError(Exception):
    """
    Raised when tool slot cannot be resolved to a tool ID

    Attributes:
        slot: The slot that was not found
        workspace_id: Workspace ID where the slot was searched
        project_id: Optional project ID where the slot was searched
        available_slots: List of available slots (if available)
        suggestion: Suggested action message
    """

    def __init__(
        self,
        message: str,
        slot: Optional[str] = None,
        workspace_id: Optional[str] = None,
        project_id: Optional[str] = None,
        available_slots: Optional[List[str]] = None,
        suggestion: Optional[str] = None
    ):
        super().__init__(message)
        self.slot = slot
        self.workspace_id = workspace_id
        self.project_id = project_id
        self.available_slots = available_slots or []
        self.suggestion = suggestion


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

    def _is_registered_capability_tool(self, tool_id: str) -> bool:
        """
        Check if a tool_id is available via the capability registry.

        This supports the "system-level default mapping" behavior for capability tools:
        if a capability pack is installed and registers `capability.tool_name`, we can
        treat the slot as already-resolved (unless an explicit mapping overrides it).
        """
        try:
            # Local import to avoid import cycles during app bootstrap.
            from backend.app.services.capability_registry import (
                get_registry,
                reload_capability,
            )

            reg = get_registry()
            tool = reg.get_tool(tool_id)
            if tool:
                return True

            # Resolve only the requested pack when its manifest has not been seen yet.
            capability_code = tool_id.split(".", 1)[0]
            if capability_code and reload_capability(capability_code):
                reg = get_registry()
                return bool(reg.get_tool(tool_id))

            return False
        except Exception:
            return False

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
        resolution = await self.resolve_with_evidence(
            slot=slot,
            workspace_id=workspace_id,
            project_id=project_id,
        )
        return resolution.tool_id

    async def resolve_with_evidence(
        self,
        *,
        slot: str,
        workspace_id: str,
        project_id: Optional[str] = None,
    ) -> ToolSlotResolution:
        """Resolve once and retain the exact mapping identity for admission pinning."""
        try:
            mapping = await self._get_resolution_candidate(
                slot=slot,
                workspace_id=workspace_id,
                project_id=project_id,
            )
            if mapping:
                tool_id = str(mapping.get("tool_id") or "").strip()
                if tool_id:
                    mapping_project_id = mapping.get("project_id")
                    mapping_kind = (
                        "project" if mapping_project_id is not None else "workspace"
                    )
                    logger.info(
                        "Resolved slot '%s' to tool '%s' (%s mapping)",
                        slot,
                        tool_id,
                        mapping_kind,
                    )
                    return ToolSlotResolution(
                        slot=slot,
                        tool_id=tool_id,
                        mapping_kind=mapping_kind,
                        mapping_id=str(mapping.get("id") or "") or None,
                        mapping_updated_at=(
                            str(mapping.get("updated_at") or "") or None
                        ),
                        project_id=(
                            str(mapping_project_id)
                            if mapping_project_id is not None
                            else None
                        ),
                    )

            if self._is_registered_capability_tool(slot):
                logger.info(
                    "Slot '%s' is a registered capability tool, using as-is",
                    slot,
                )
                return ToolSlotResolution(
                    slot=slot,
                    tool_id=slot,
                    mapping_kind="registered_default",
                )

            if self._looks_like_tool_id(slot):
                logger.info(
                    "Slot '%s' appears to be a concrete tool ID, using as-is",
                    slot,
                )
                return ToolSlotResolution(
                    slot=slot,
                    tool_id=slot,
                    mapping_kind="legacy_concrete_tool",
                )

            available_slots = await self._get_available_slots(
                workspace_id,
                project_id,
            )
            suggestion = self._generate_suggestion(
                slot,
                available_slots,
                workspace_id,
                project_id,
            )
            project_msg = f"or project '{project_id}'" if project_id else ""
            raise SlotNotFoundError(
                f"Tool slot '{slot}' not found. "
                f"Please configure a mapping in workspace '{workspace_id}' {project_msg}",
                slot=slot,
                workspace_id=workspace_id,
                project_id=project_id,
                available_slots=available_slots,
                suggestion=suggestion,
            )
        except SlotNotFoundError:
            raise
        except Exception as exc:
            logger.error(
                "Error resolving tool slot '%s': %s",
                slot,
                exc,
                exc_info=True,
            )
            raise SlotNotFoundError(
                f"Failed to resolve tool slot '{slot}': {str(exc)}",
                slot=slot,
                workspace_id=workspace_id,
                project_id=project_id,
            ) from exc

    async def _get_resolution_candidate(
        self,
        *,
        slot: str,
        workspace_id: str,
        project_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Return the highest-priority candidate from one indexed store read."""
        try:
            from backend.app.services.stores.tool_slot_mappings_store import (
                ToolSlotMappingsStore,
            )

            mappings_store = ToolSlotMappingsStore(self.store.db_path)
            candidates = mappings_store.get_resolution_candidates(
                slot=slot,
                workspace_id=workspace_id,
                project_id=project_id,
            )
            return candidates[0] if candidates else None
        except ImportError:
            logger.debug(
                "ToolSlotMappingsStore not available for slot '%s'",
                slot,
            )
            return None
        except Exception as exc:
            logger.warning(
                "Failed to get resolution candidate for slot '%s': %s",
                slot,
                exc,
            )
            return None

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

        # Heuristic: if it has exactly 2 parts, check if tool is registered in registry
        if len(parts) == 2:
            # Check if this tool_id is registered in MindscapeTool registry
            try:
                from backend.app.services.tools.registry import get_mindscape_tool
                tool = get_mindscape_tool(slot)
                if tool is not None:
                    return True
            except Exception:
                pass  # Tool not found in registry, continue with other heuristics

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

    async def _get_available_slots(
        self,
        workspace_id: str,
        project_id: Optional[str] = None
    ) -> List[str]:
        """
        Get list of available slots for helpful error messages

        Args:
            workspace_id: Workspace ID
            project_id: Optional project ID

        Returns:
            List of available slot names
        """
        try:
            from backend.app.services.stores.tool_slot_mappings_store import ToolSlotMappingsStore

            mappings_store = ToolSlotMappingsStore(self.store.db_path)
            mappings = mappings_store.get_mappings(
                workspace_id=workspace_id,
                project_id=project_id,
                enabled_only=True
            )

            # Extract unique slot names
            slots = list(set(m.get('slot') for m in mappings if m.get('slot')))
            return sorted(slots)

        except Exception as e:
            logger.debug(f"Failed to get available slots: {e}")
            return []

    def _generate_suggestion(
        self,
        slot: str,
        available_slots: List[str],
        workspace_id: str,
        project_id: Optional[str]
    ) -> str:
        """
        Generate helpful suggestion message for slot not found error

        Args:
            slot: The slot that was not found
            available_slots: List of available slots
            workspace_id: Workspace ID
            project_id: Optional project ID

        Returns:
            Suggestion message
        """
        suggestions = []

        # Check for similar slot names (fuzzy match)
        slot_parts = slot.split('.')
        similar_slots = []
        for available_slot in available_slots:
            available_parts = available_slot.split('.')
            # Check if slots share common prefix
            if len(slot_parts) > 0 and len(available_parts) > 0:
                if slot_parts[0] == available_parts[0] or slot_parts[-1] == available_parts[-1]:
                    similar_slots.append(available_slot)

        if similar_slots:
            suggestions.append(f"Similar slots found: {', '.join(similar_slots[:3])}")

        # Add configuration guidance
        config_level = "project" if project_id else "workspace"
        suggestions.append(
            f"To configure this slot, use the API: "
            f"POST /api/v1/tool-slots with slot='{slot}', tool_id=<your_tool_id>"
        )

        if available_slots:
            suggestions.append(
                f"Currently configured slots in this {config_level}: {', '.join(available_slots[:5])}"
                + (f" (and {len(available_slots) - 5} more)" if len(available_slots) > 5 else "")
            )

        return ". ".join(suggestions)


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
