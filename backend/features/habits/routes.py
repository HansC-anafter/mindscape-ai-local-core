"""
Habit Learning API route facade.

Keeps the manifest import string stable while route groups live in focused modules.
"""

from fastapi import APIRouter

from backend.features.habits.audit_routes import router as audit_router
from backend.features.habits.candidate_routes import router as candidate_router
from backend.features.habits.dependencies import habit_store, mindscape_store
from backend.features.habits.metrics_routes import router as metrics_router
from backend.features.habits.suggestion_helpers import (
    _generate_suggestion_message,
    _supersede_conflicting_candidates,
)

router = APIRouter(tags=["habits"])
router.include_router(candidate_router)
router.include_router(audit_router)
router.include_router(metrics_router)

__all__ = [
    "_generate_suggestion_message",
    "_supersede_conflicting_candidates",
    "habit_store",
    "mindscape_store",
    "router",
]
