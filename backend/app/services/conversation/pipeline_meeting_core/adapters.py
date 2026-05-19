"""Adapter helpers for meeting pipeline runtime."""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def build_execution_launcher(store: Any) -> Optional[Any]:
    try:
        from backend.app.services.conversation.execution_launcher import (
            ExecutionLauncher,
        )
        from backend.app.services.playbook_service import PlaybookService

        playbook_service = PlaybookService(store=store)
        return ExecutionLauncher(playbook_service=playbook_service)
    except Exception as exc:
        logger.warning(
            "[PipelineCore] Failed to initialize ExecutionLauncher for meeting mode: %s",
            exc,
            exc_info=True,
        )
        return None


def extract_handoff_in(request: Optional[Any]) -> Optional[Any]:
    if not request:
        return None
    handoff_data = getattr(request, "handoff_in", None)
    if not handoff_data:
        return None
    from backend.app.models.handoff import HandoffIn

    if isinstance(handoff_data, dict):
        return HandoffIn(**handoff_data)
    if isinstance(handoff_data, HandoffIn):
        return handoff_data
    return None


async def persist_meeting_task_ir(task_ir: Any) -> None:
    try:
        from backend.app.services.stores.postgres.task_ir_store import (
            PostgresTaskIRStore,
        )

        store = PostgresTaskIRStore()
        replaced = store.replace_task_ir(task_ir)
        logger.info(
            "[PipelineCore] Persisted TaskIR %s (replaced=%s)",
            task_ir.task_id,
            replaced,
        )
    except Exception as exc:
        logger.warning(
            "[PipelineCore] Failed to persist TaskIR: %s",
            exc,
            exc_info=True,
        )
