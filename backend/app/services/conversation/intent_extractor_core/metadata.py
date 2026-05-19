"""Event metadata helpers for intent extraction."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


async def update_event_metadata(
    *,
    store: Any,
    event_id: str,
    intents: List[Dict[str, Any]],
    themes: List[str],
) -> bool:
    try:
        event = store.get_event(event_id)
        if not event:
            logger.warning("Event %s not found for metadata update", event_id)
            return False

        if event.metadata is None:
            event.metadata = {}

        event.metadata["llm_extracted_intents"] = intents
        event.metadata["llm_extracted_themes"] = themes

        store.update_event(event_id, metadata=event.metadata)
        logger.debug("Updated event %s metadata with extracted intents/themes", event_id)
        return True

    except Exception as exc:
        logger.warning("Failed to update event metadata: %s", exc)
        return False
