"""Router aggregation for chat and embedding settings."""

from fastapi import APIRouter

from .chat_test_routes import router as chat_test_router
from .embedding_test_routes import router as embedding_test_router
from .settings_routes import router as settings_router

router = APIRouter()
router.include_router(settings_router)
router.include_router(chat_test_router)
router.include_router(embedding_test_router)
