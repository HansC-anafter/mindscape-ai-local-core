"""Playbook and capability validation helpers for suggestion card creation."""

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


async def validate_playbook(
    *,
    pack_id: str,
    workspace_id: str,
    playbook_service=None,
    default_locale: str = "en",
    registry_factory: Optional[Callable[[], Any]] = None,
) -> Dict[str, Any]:
    if not pack_id:
        return {"is_valid": False, "reason": "empty_pack_id"}

    is_valid = False

    if playbook_service:
        try:
            playbook = await playbook_service.get_playbook(
                playbook_code=pack_id,
                locale=default_locale,
                workspace_id=workspace_id,
            )
            if playbook:
                is_valid = True
                logger.info(
                    "SuggestionCardCreator: Pack %s validated as playbook",
                    pack_id,
                )
        except Exception as exc:
            logger.debug(
                "SuggestionCardCreator: Pack %s not found in PlaybookService: %s",
                pack_id,
                exc,
            )

    if not is_valid:
        if registry_factory is None:
            from backend.app.services.capability_registry import get_registry

            registry_factory = get_registry
        registry = registry_factory()
        execution_method = registry.get_execution_method(pack_id)
        if execution_method in ["playbook", "pack_executor"]:
            is_valid = True
            logger.info(
                "SuggestionCardCreator: Pack %s validated as capability pack "
                "(execution_method=%s)",
                pack_id,
                execution_method,
            )

    pack_id_lower = pack_id.lower()
    if pack_id_lower in ["intent_extraction", "semantic_seeds"]:
        is_valid = True
        logger.info(
            "SuggestionCardCreator: Pack %s validated as special pack",
            pack_id,
        )

    return {
        "is_valid": is_valid,
        "reason": None if is_valid else "invalid_playbook_code",
    }
