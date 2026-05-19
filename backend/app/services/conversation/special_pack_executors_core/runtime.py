"""Runtime orchestration for special pack executors."""

import logging
from typing import Any, Dict, List, Optional

from backend.app.services.conversation.special_pack_executors_core.extraction import (
    extract_intents_from_files,
    extract_intents_from_message,
)
from backend.app.services.conversation.special_pack_executors_core.results import (
    build_execution_result,
)
from backend.app.services.conversation.special_pack_executors_core.sources import (
    get_intents_from_events,
    get_intents_from_timeline_items,
)
from backend.app.services.conversation.special_pack_executors_core.task_lifecycle import (
    complete_task,
    create_running_task,
    emit_task_created,
    emit_task_updated,
)

logger = logging.getLogger(__name__)


async def execute_semantic_seeds(
    *,
    executor,
    workspace_id: str,
    profile_id: str,
    message_id: str,
    files: List[str],
    message: str,
    event_emitter=None,
) -> Optional[Dict[str, Any]]:
    try:
        pack_id = "semantic_seeds"
        task = create_running_task(
            tasks_store=executor.tasks_store,
            workspace_id=workspace_id,
            message_id=message_id,
            files=files,
            message=message,
            pack_id=pack_id,
        )

        emitter = event_emitter or executor.event_emitter
        emit_task_created(emitter=emitter, task=task, pack_id=pack_id)

        extracted_intents: List[str] = []
        file_contents: List[str] = []

        extracted_intents.extend(
            await get_intents_from_timeline_items(
                timeline_items_store=executor.timeline_items_store,
                workspace_id=workspace_id,
            )
        )

        extracted_intents, file_contents = await get_intents_from_events(
            store=executor.store,
            workspace_id=workspace_id,
            extracted_intents=extracted_intents,
            file_contents=file_contents,
        )

        if not extracted_intents and file_contents:
            extracted_intents.extend(
                await extract_intents_from_files(
                    config_store=executor.config_store,
                    profile_id=profile_id,
                    message_id=message_id,
                    message=message,
                    file_contents=file_contents,
                )
            )

        if not extracted_intents and not file_contents and message:
            extracted_intents.extend(
                await extract_intents_from_message(
                    config_store=executor.config_store,
                    profile_id=profile_id,
                    message_id=message_id,
                    message=message,
                )
            )

        execution_result = build_execution_result(
            extracted_intents=extracted_intents,
            files=files,
            file_contents=file_contents,
        )

        complete_task(
            tasks_store=executor.tasks_store,
            task=task,
            execution_result=execution_result,
        )
        emit_task_updated(emitter=emitter, task=task, pack_id=pack_id)

        return {
            "pack_id": pack_id,
            "task_id": task.id,
            "result": execution_result,
        }

    except Exception as exc:
        logger.error(
            "SpecialPackExecutors: Failed to execute semantic_seeds: %s",
            exc,
            exc_info=True,
        )
        return None
