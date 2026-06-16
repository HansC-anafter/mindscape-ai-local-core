"""
Workbench Service

Provides workbench data for workspace including:
- Current context (workspace focus, recent files, detected intents)
- Suggested next steps
- System status (lightweight version)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.system_health_checker import SystemHealthChecker
from backend.app.services.workbench_context import WorkbenchContextMixin
from backend.app.services.workbench_status import WorkbenchStatusMixin
from backend.app.services.workbench_suggestions import WorkbenchSuggestionsMixin

logger = logging.getLogger(__name__)


class WorkbenchService(
    WorkbenchContextMixin,
    WorkbenchSuggestionsMixin,
    WorkbenchStatusMixin,
):
    """Service for providing workbench data"""

    def __init__(
        self,
        store: Optional[MindscapeStore] = None,
        health_checker: Optional[SystemHealthChecker] = None,
    ):
        self.store = store or MindscapeStore()
        self.health_checker = health_checker or SystemHealthChecker()

    async def get_workbench_data(
        self, workspace_id: str, profile_id: str
    ) -> Dict[str, Any]:
        """
        Get workbench data for a workspace

        Returns:
            Dictionary containing:
            - current_context: Current workspace context
            - suggested_next_steps: Suggested next steps
            - system_status: Lightweight system status
        """
        try:
            workspace = await self.store.get_workspace(workspace_id)
            if not workspace:
                raise ValueError(f"Workspace {workspace_id} not found")

            current_context = await self._get_current_context(
                workspace_id=workspace_id, profile_id=profile_id
            )

            suggested_next_steps = []
            use_cached = False

            context_fingerprint = self._build_context_fingerprint(current_context)

            if workspace.suggestion_history and len(workspace.suggestion_history) > 0:
                last_round = workspace.suggestion_history[-1]
                cached_fingerprint = last_round.get("context_fingerprint")

                if cached_fingerprint == context_fingerprint:
                    suggested_next_steps = last_round.get("suggestions", [])
                    use_cached = True
                    logger.info(f"Using cached suggestions (context unchanged)")
                else:
                    logger.info(
                        f"Context changed, regenerating suggestions (old: {cached_fingerprint}, new: {context_fingerprint})"
                    )
                    use_cached = False

            if not use_cached:
                from backend.app.services.suggestion_generator import (
                    SuggestionGenerator,
                )

                locale = workspace.default_locale or "zh-TW"
                suggestion_generator = SuggestionGenerator(default_locale=locale)
                suggested_next_steps = await suggestion_generator.generate_suggestions(
                    workspace_id=workspace_id,
                    profile_id=profile_id,
                    context=current_context,
                    locale=locale,
                )

            if not use_cached:
                if workspace.suggestion_history is None:
                    workspace.suggestion_history = []

                import uuid

                current_round = {
                    "round_id": str(uuid.uuid4()),
                    "timestamp": _utc_now().isoformat(),
                    "suggestions": suggested_next_steps,
                    "context_fingerprint": context_fingerprint,
                }
                workspace.suggestion_history.append(current_round)

                if len(workspace.suggestion_history) > 3:
                    workspace.suggestion_history = workspace.suggestion_history[-3:]

                await self.store.workspaces.update_workspace(workspace)

            system_status = await self._get_lightweight_system_status(
                profile_id=profile_id
            )

            return {
                "current_context": current_context,
                "suggested_next_steps": suggested_next_steps,
                "suggestion_history": (
                    workspace.suggestion_history[-3:]
                    if workspace.suggestion_history
                    else []
                ),
                "system_status": system_status,
            }
        except Exception as e:
            logger.error(f"Failed to get workbench data: {e}", exc_info=True)
            raise
