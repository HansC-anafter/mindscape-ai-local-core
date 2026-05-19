"""Project flag helpers for meeting pipeline runtime."""

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def is_project_meeting_enabled(project_id: Optional[str], store: Any) -> bool:
    if not project_id:
        return False
    try:
        loop = asyncio.get_running_loop()
        project = await loop.run_in_executor(
            None,
            lambda: store.get_project(project_id),
        )
        if not project:
            return False
        metadata = getattr(project, "metadata", {}) or {}
        raw = metadata.get("meeting_enabled")
        return raw is True or (isinstance(raw, str) and raw.lower() == "true")
    except Exception as exc:
        logger.warning(
            "[PipelineCore] Failed to read project meeting flag: %s",
            exc,
            exc_info=True,
        )
        return False
