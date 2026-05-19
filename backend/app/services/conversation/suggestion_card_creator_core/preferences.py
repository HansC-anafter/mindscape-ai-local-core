"""User preference helpers for suggestion card creation."""

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


async def check_user_preference(
    *,
    task_plan,
    workspace_id: str,
    workspace_store_factory: Optional[Callable[[], Any]] = None,
    preference_store_factory: Optional[Callable[[], Any]] = None,
) -> Dict[str, Any]:
    try:
        if workspace_store_factory is None:
            from backend.app.services.mindscape_store import MindscapeStore

            workspace_store_factory = MindscapeStore

        if preference_store_factory is None:
            from backend.app.services.stores.postgres.task_preference_store import (
                PostgresTaskPreferenceStore,
            )

            preference_store_factory = PostgresTaskPreferenceStore

        store = workspace_store_factory()
        preference_store = preference_store_factory()

        workspace = await store.get_workspace(workspace_id)
        if workspace:
            should_auto_suggest = preference_store.should_auto_suggest(
                workspace_id=workspace_id,
                user_id=workspace.owner_user_id,
                pack_id=task_plan.pack_id,
                task_type=task_plan.task_type,
            )
            return {"should_auto_suggest": should_auto_suggest}

        return {"should_auto_suggest": True}

    except Exception as exc:
        logger.warning(
            "SuggestionCardCreator: Failed to check user preference: %s",
            exc,
        )
        return {"should_auto_suggest": True}
