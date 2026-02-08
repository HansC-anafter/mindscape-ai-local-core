"""
LLM Settings Sub-Package

This package splits the llm_models.py (1735 lines) into smaller, focused modules:
- models.py: Model CRUD operations (get, toggle, config, test, pull)
- chat_embedding.py: Chat/embedding model settings and migration helpers
- capability_profiles.py: Capability profile configuration
- utility_configs.py: Model utility configuration

All routers are combined and re-exported from here.
"""

from fastapi import APIRouter

from .models import router as models_router
from .chat_embedding import router as chat_embedding_router
from .capability_profiles import router as capability_profiles_router
from .utility_configs import router as utility_configs_router

# Combined router for backward compatibility
router = APIRouter()

# Include all sub-routers
router.include_router(models_router)
router.include_router(chat_embedding_router)
router.include_router(capability_profiles_router)
router.include_router(utility_configs_router)

__all__ = [
    "router",
    "models_router",
    "chat_embedding_router",
    "capability_profiles_router",
    "utility_configs_router",
]
