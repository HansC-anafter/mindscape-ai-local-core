"""Candidate IntentTag creation helpers."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from backend.app.models.mindscape import IntentSource, IntentTag, IntentTagStatus
from backend.app.services.conversation.intent_extractor_core.clock import utc_now

logger = logging.getLogger(__name__)


def normalize_intent_item(
    intent_item: Any,
    fallback_confidence: float,
) -> Tuple[str, Optional[float]]:
    if isinstance(intent_item, dict):
        intent_label = (
            intent_item.get("title") or intent_item.get("text") or str(intent_item)
        )
        intent_confidence = intent_item.get("confidence", fallback_confidence)
    else:
        intent_label = str(intent_item)
        intent_confidence = fallback_confidence

    clean_label = intent_label.strip() if intent_label else ""
    clean_confidence = float(intent_confidence) if intent_confidence else None
    return clean_label, clean_confidence


def create_candidate_intent_tags(
    *,
    intent_tags_store: Any,
    ctx: Any,
    message_id: str,
    intents: List[Any],
    confidence: Optional[float],
    llm_analysis: Optional[Dict[str, Any]],
) -> List[str]:
    llm_confidence = confidence or 0.0
    intent_tag_ids = []

    for intent_item in list(intents or [])[:5]:
        try:
            intent_label, intent_confidence = normalize_intent_item(
                intent_item,
                llm_confidence,
            )
            if not intent_label:
                continue

            candidate_tag = IntentTag(
                id=str(uuid.uuid4()),
                workspace_id=ctx.workspace_id,
                profile_id=ctx.actor_id,
                label=intent_label,
                confidence=intent_confidence,
                status=IntentTagStatus.CANDIDATE,
                source=IntentSource.LLM,
                execution_id=None,
                playbook_code=None,
                message_id=message_id,
                metadata={
                    "extraction_source": "intent_extractor",
                    "llm_analysis": llm_analysis or {},
                },
                created_at=utc_now(),
                updated_at=utc_now(),
                confirmed_at=None,
                rejected_at=None,
            )
            intent_tags_store.create_intent_tag(candidate_tag)
            intent_tag_ids.append(candidate_tag.id)
            logger.info(
                "Created candidate IntentTag %s: %s",
                candidate_tag.id,
                intent_label[:50],
            )
        except Exception as exc:
            logger.warning("Failed to create candidate IntentTag: %s", exc)

    return intent_tag_ids
