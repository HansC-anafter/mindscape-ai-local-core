"""Intent source collection helpers for special pack executors."""

import logging
from typing import List

from backend.app.models.mindscape import EventType
from backend.app.models.workspace import TimelineItemType

logger = logging.getLogger(__name__)


async def get_intents_from_timeline_items(
    *, timeline_items_store, workspace_id: str
) -> List[str]:
    extracted_intents: List[str] = []

    try:
        if timeline_items_store:
            recent_timeline_items = timeline_items_store.list_timeline_items_by_workspace(
                workspace_id=workspace_id,
                limit=10,
            )
            for item in recent_timeline_items:
                if item.type != TimelineItemType.INTENT_SEEDS:
                    continue
                item_data = item.data if isinstance(item.data, dict) else {}
                intents_list = item_data.get("intents", [])
                if isinstance(intents_list, list):
                    _append_unique_intents(extracted_intents, intents_list)
                logger.info(
                    "SpecialPackExecutors: Found %s intents from "
                    "IntentExtractor timeline_item %s",
                    len(intents_list),
                    item.id,
                )
    except Exception as exc:
        logger.warning(
            "SpecialPackExecutors: Failed to get intents from timeline_items: %s",
            exc,
        )

    return extracted_intents


async def get_intents_from_events(
    *,
    store,
    workspace_id: str,
    extracted_intents: List[str],
    file_contents: List[str],
) -> tuple[List[str], List[str]]:
    try:
        recent_events = store.get_events_by_workspace(
            workspace_id=workspace_id,
            limit=50,
        )

        for event in recent_events:
            if event.event_type != EventType.MESSAGE:
                continue
            metadata = event.metadata if isinstance(event.metadata, dict) else {}
            file_analysis = metadata.get("file_analysis", {})
            collaboration = file_analysis.get("collaboration_results", {})
            semantic_seeds = collaboration.get("semantic_seeds", {})

            if semantic_seeds.get("enabled") and semantic_seeds.get("intents"):
                _append_unique_intents(
                    extracted_intents,
                    semantic_seeds.get("intents", []),
                )

                analysis = file_analysis.get("analysis", {})
                file_info = analysis.get("file_info", {})
                if file_info.get("text_content"):
                    file_contents.append(file_info["text_content"])

    except Exception as exc:
        logger.warning(
            "SpecialPackExecutors: Failed to get intents from events: %s",
            exc,
        )

    return extracted_intents, file_contents


def _append_unique_intents(extracted_intents: List[str], intents: list) -> None:
    for intent in intents:
        if isinstance(intent, dict):
            intent_text = intent.get("title") or intent.get("text") or str(intent)
        else:
            intent_text = str(intent)
        if intent_text and intent_text not in extracted_intents:
            extracted_intents.append(intent_text)
