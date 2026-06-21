"""Intent extraction and steward runtime helpers for MCP event hooks."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, List, Optional

logger = logging.getLogger("backend.app.services.mcp_event_hooks")


async def extract_intents(
    service: Any,
    workspace_id_arg: str,
    profile_id: str,
    message: str,
    message_id: str,
    thread_id: Optional[str] = None,
) -> List[Any]:
    """Run intent extraction with MCP sampling fallback semantics."""
    if service.sampling_gate and service.mcp_server:
        try:
            from ..sampling_gate import SamplingGate

            prompt_params = SamplingGate.build_intent_extract_prompt(message)

            async def sampling_fn() -> List[Any]:
                result = await service.mcp_server.createMessage(prompt_params)
                return parse_sampling_intents(
                    result, workspace_id_arg, profile_id, message_id
                )

            async def fallback_fn() -> List[Any]:
                return await ws_extract_intents(
                    service, workspace_id_arg, profile_id, message, message_id
                )

            sampling_result = await service.sampling_gate.with_fallback(
                sampling_fn=sampling_fn,
                fallback_fn=fallback_fn,
                workspace_id=workspace_id_arg,
                template="intent_extract",
            )
            return sampling_result.data or []

        except Exception as exc:
            logger.warning("Sampling-aware extraction failed, using direct: %s", exc)

    return await ws_extract_intents(
        service, workspace_id_arg, profile_id, message, message_id
    )


async def ws_extract_intents(
    service: Any,
    workspace_id_arg: str,
    profile_id: str,
    message: str,
    message_id: str,
) -> List[Any]:
    """Run direct workspace-side LLM intent extraction."""
    try:
        from ...adapters.local.local_intent_registry_adapter import (
            LocalIntentRegistryAdapter,
        )
        from ..conversation.intent_extractor import IntentExtractor
        from ..mindscape_store import MindscapeStore
        from ..stores.postgres.timeline_items_store import PostgresTimelineItemsStore

        store = service.store or MindscapeStore()
        extractor = IntentExtractor(
            store=store,
            timeline_items_store=PostgresTimelineItemsStore(),
            intent_registry=LocalIntentRegistryAdapter(),
        )

        tags = extractor.extract_intents(
            workspace_id=workspace_id_arg,
            profile_id=profile_id,
            message=message,
            message_id=message_id,
        )
        return tags or []

    except ImportError as exc:
        logger.warning("Intent extraction not available: %s", exc)
        return []
    except Exception as exc:
        logger.error("Intent extraction failed: %s", exc, exc_info=True)
        return []


def parse_sampling_intents(
    sampling_result: Any,
    workspace_id: str,
    profile_id: str,
    message_id: str,
) -> List[Any]:
    """Parse an MCP createMessage response into lightweight intent dicts."""
    try:
        content = getattr(sampling_result, "content", sampling_result)
        if isinstance(content, dict):
            text = content.get("text", str(content))
        elif hasattr(content, "text"):
            text = content.text
        else:
            text = str(content)

        if "[" in text:
            json_start = text.index("[")
            json_end = text.rindex("]") + 1
            intents = json.loads(text[json_start:json_end])
        else:
            intents = json.loads(text)

        if not isinstance(intents, list):
            intents = [intents]

        tags = []
        for intent in intents:
            tags.append(
                {
                    "id": str(uuid.uuid4()),
                    "workspace_id": workspace_id,
                    "profile_id": profile_id,
                    "label": intent.get("label", "unknown"),
                    "confidence": intent.get("confidence", 0.5),
                    "source": "mcp_sampling",
                    "message_id": message_id,
                    "reasoning": intent.get("reasoning", ""),
                }
            )
        return tags

    except (json.JSONDecodeError, ValueError, AttributeError) as exc:
        logger.warning("Failed to parse sampling intents: %s", exc)
        return []


async def run_steward(
    service: Any,
    workspace_id_arg: str,
    profile_id: str,
    intent_tags: List[Any],
    message: str,
) -> Any:
    """Run IntentSteward analysis on extracted tags."""
    try:
        from ...models.mindscape import IntentSignal, IntentStewardInput
        from ..conversation.intent_steward import IntentStewardService
        from ..mindscape_store import MindscapeStore

        store = service.store or MindscapeStore()
        steward = IntentStewardService(store=store)

        signals = []
        for tag in intent_tags:
            signal = IntentSignal(
                id=getattr(tag, "id", str(uuid.uuid4())),
                workspace_id=workspace_id_arg,
                profile_id=profile_id,
                label=getattr(tag, "label", str(tag)),
                confidence=getattr(tag, "confidence", 0.5),
                source="ws_hook",
                message_id=getattr(tag, "message_id", None),
            )
            signals.append(signal)

        if not signals:
            return None

        steward_input = IntentStewardInput(
            recent_messages=[{"role": "user", "content": message}],
            recent_signals=signals,
            current_intent_cards=[],
        )

        layout = await steward.steward_analyze(
            workspace_id=workspace_id_arg,
            profile_id=profile_id,
            steward_input=steward_input,
        )
        return layout

    except ImportError as exc:
        logger.warning("Steward analysis not available: %s", exc)
        return None
    except Exception as exc:
        logger.error("Steward analysis failed: %s", exc, exc_info=True)
        return None
