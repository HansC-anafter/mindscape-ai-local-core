"""
Playbook Handler Router Registration

This module registers playbook handlers using the handler registry system.
Handlers are loaded dynamically from playbook packages, not hardcoded here.
"""

import logging
from fastapi import APIRouter

from ....services.playbook_handlers.base import get_handler_registry

logger = logging.getLogger(__name__)

# Create a router for playbook handlers
router = APIRouter(tags=["playbook-handlers"])


async def register_playbook_handlers(main_router: APIRouter) -> None:
    """
    Register all playbook handlers on the main router

    This function should be called during application startup.
    It loads handlers from installed playbook packages and registers their routes.

    Args:
        main_router: Main FastAPI router to register handlers on
    """
    try:
        registry = get_handler_registry()

        # Load handlers from packages
        await registry.load_handlers_from_packages()

        # Register all handler routes
        registry.register_all_routes(main_router)

        logger.info(f"Registered handlers for {len(registry.list())} playbook(s)")
    except Exception as e:
        logger.error(f"Failed to register playbook handlers: {e}", exc_info=True)

