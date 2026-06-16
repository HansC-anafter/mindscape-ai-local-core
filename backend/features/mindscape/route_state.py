"""Shared state for Mindscape route modules."""

import logging

from backend.app.services.mindscape_onboarding import MindscapeOnboardingService
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.orchestration.governance_engine import GovernanceEngine

logger = logging.getLogger("backend.features.mindscape.routes")

store = MindscapeStore()
onboarding_service = MindscapeOnboardingService(store)
governance_engine = GovernanceEngine()
