"""Session finalization helpers for meeting pipeline runtime."""

import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def finalize_meeting_session(result: Any, session_store: Any) -> None:
    if not result.meeting_session_id:
        return

    try:
        loop = asyncio.get_running_loop()
        session = await loop.run_in_executor(
            None,
            lambda: session_store.get_by_id(result.meeting_session_id),
        )
        if not session:
            return

        run_meta = session.metadata.get("runs", [])
        run_meta.append(
            {
                "playbook": result.playbook_code,
                "execution_id": result.execution_id,
                "success": result.success,
                "error": result.error,
            }
        )
        session.metadata["runs"] = run_meta

        if hasattr(result, "completion_status") and result.completion_status:
            session.metadata["completion_status"] = result.completion_status

        await loop.run_in_executor(None, lambda: session_store.update(session))
        logger.info(
            "[PipelineCore] Session %s finalized (decisions=%s)",
            session.id,
            len(session.decisions),
        )
    except Exception as exc:
        logger.warning(
            "[PipelineCore] Session finalize error: %s",
            exc,
            exc_info=True,
        )
