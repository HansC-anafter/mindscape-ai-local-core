from typing import Any, Dict, List, Optional

from backend.app.models.playbook import Playbook


async def validate_playbook_slots_for_service(
    *,
    store: Any,
    playbook_code: str,
    workspace_id: str,
    locale: str = "zh-TW",
    project_id: Optional[str] = None,
    logger: Any,
) -> tuple[bool, List[str], Dict[str, str]]:
    """Validate playbook tool slot mappings through the existing resolver path."""
    try:
        from backend.app.services.playbook_loaders.json_loader import (
            PlaybookJsonLoader,
        )
        from backend.app.services.tool_slot_resolver import (
            SlotNotFoundError,
            get_tool_slot_resolver,
        )

        playbook_json = PlaybookJsonLoader.load_playbook_json(playbook_code)
        if not playbook_json or not playbook_json.steps:
            return True, [], {}

        slots = [
            step.tool_slot
            for step in playbook_json.steps
            if hasattr(step, "tool_slot") and step.tool_slot
        ]
        if not slots:
            return True, [], {}

        resolver = get_tool_slot_resolver(store=store)
        missing_slots = []
        slot_mappings = {}
        for slot in slots:
            try:
                tool_id = await resolver.resolve(
                    slot=slot,
                    workspace_id=workspace_id,
                    project_id=project_id,
                )
                slot_mappings[slot] = tool_id
            except SlotNotFoundError:
                missing_slots.append(slot)

        return len(missing_slots) == 0, missing_slots, slot_mappings
    except Exception as exc:
        logger.error(
            "Failed to validate playbook slots for %s: %s",
            playbook_code,
            exc,
            exc_info=True,
        )
        return False, [], {}


def validate_edit_permission_for_playbook(
    playbook: Playbook,
    edit_type: str = "sop",
) -> tuple[bool, Optional[str]]:
    """Validate existing template/workspace edit permission rules."""
    if not playbook:
        return False, "Playbook not found"

    if playbook.metadata.is_template():
        if edit_type == "sop":
            return False, (
                "Cannot edit SOP for template playbook. "
                f"Please fork to workspace first (scope: {playbook.metadata.get_scope_level()})"
            )
        if edit_type == "resources":
            return False, (
                "Cannot edit resources for template playbook. "
                f"Please fork to workspace first (scope: {playbook.metadata.get_scope_level()})"
            )
        return True, None

    return True, None
