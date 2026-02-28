"""
Playbook routes module
"""

import logging

from fastapi import APIRouter
from ._shared import mindscape_store, playbook_service

router = APIRouter(prefix="/api/v1/playbooks", tags=["playbooks"])
logger = logging.getLogger(__name__)

try:
    from .queries import router as queries_router

    router.include_router(queries_router)
except Exception as e:
    logger.error("Failed to import queries router: %s", e, exc_info=True)

try:
    from .crud import router as crud_router

    router.include_router(crud_router)
except Exception as e:
    logger.error("Failed to import crud router: %s", e, exc_info=True)

try:
    from .management import router as management_router

    router.include_router(management_router)
except Exception as e:
    logger.error("Failed to import management router: %s", e, exc_info=True)

try:
    from .variants import router as variants_router

    router.include_router(variants_router)
except Exception as e:
    logger.error("Failed to import variants router: %s", e, exc_info=True)

try:
    from .intents import router as intents_router

    router.include_router(intents_router)
except Exception as e:
    logger.error("Failed to import intents router: %s", e, exc_info=True)

try:
    from .tools import router as tools_router

    router.include_router(tools_router)
except Exception as e:
    logger.error("Failed to import tools router: %s", e, exc_info=True)

try:
    from .testing import router as testing_router

    router.include_router(testing_router)
except Exception as e:
    logger.error("Failed to import testing router: %s", e, exc_info=True)

try:
    from .resources import router as resources_router

    router.include_router(resources_router)
except Exception as e:
    logger.error("Failed to import resources router: %s", e, exc_info=True)

try:
    from .fork import router as fork_router

    router.include_router(fork_router)
except Exception as e:
    logger.error("Failed to import fork router: %s", e, exc_info=True)

# Playbook handlers are registered dynamically via handler registry
# See backend/app/services/playbook_handlers/base.py
# Handlers are loaded from playbook packages, not hardcoded here

__all__ = ["router", "mindscape_store", "playbook_service"]
