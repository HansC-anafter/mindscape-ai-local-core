import logging

from backend.app.services.runtime_auth_service import RuntimeAuthService

logger = logging.getLogger(__name__)
auth_service = RuntimeAuthService()
_pending_states: dict = {}
