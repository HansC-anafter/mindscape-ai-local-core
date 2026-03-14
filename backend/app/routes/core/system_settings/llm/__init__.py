"""
LLM Settings Sub-Package

Focused modules:
- models.py: Model CRUD operations (get, toggle, config, delete)
- model_testing.py: Provider-specific connection testing
- pull_manager.py: Redis-backed model download/pull tracking
- chat_embedding.py: Chat/embedding model settings and migration helpers
- capability_profiles.py: Capability profile configuration
- utility_configs.py: Model utility configuration
- discovery.py: Provider/model discovery

All routers are combined and re-exported from here.
"""

from fastapi import APIRouter

from .models import router as models_router
from .model_testing import router as model_testing_router
from .pull_manager import router as pull_manager_router
from .chat_embedding import router as chat_embedding_router
from .capability_profiles import router as capability_profiles_router
from .utility_configs import router as utility_configs_router
from .discovery import router as discovery_router

# Combined router for backward compatibility
router = APIRouter()

# Include all sub-routers
router.include_router(models_router)
router.include_router(model_testing_router)
router.include_router(pull_manager_router)
router.include_router(chat_embedding_router)
router.include_router(capability_profiles_router)
router.include_router(utility_configs_router)
router.include_router(discovery_router)

__all__ = [
    "router",
    "models_router",
    "model_testing_router",
    "pull_manager_router",
    "chat_embedding_router",
    "capability_profiles_router",
    "utility_configs_router",
    "discovery_router",
]
