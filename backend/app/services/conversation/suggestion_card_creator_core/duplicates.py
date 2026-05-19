"""Duplicate detection helpers for suggestion card creation."""

import logging

logger = logging.getLogger(__name__)


def should_create_new_suggestion_task(existing_tasks: list, task_plan) -> bool:
    if not existing_tasks:
        return True

    new_params = task_plan.params or {}
    new_params_source = new_params.get("source", "")
    new_params_files = new_params.get("files", [])

    for existing_task in existing_tasks:
        existing_params = existing_task.params or {}
        existing_source = existing_params.get("source", "")
        existing_files = existing_params.get("files", [])

        source_match = new_params_source == existing_source
        files_match = set(new_params_files) == set(existing_files)

        if source_match and files_match:
            logger.info(
                "SuggestionCardCreator: Found duplicate suggestion task %s for "
                "pack %s, skipping creation",
                existing_task.id,
                task_plan.pack_id,
            )
            return False

    return True
