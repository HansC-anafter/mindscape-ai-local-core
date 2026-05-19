"""Intent steward LLM analysis."""

import json
import logging
from typing import List, Optional

from backend.app.models.mindscape import (
    EphemeralTask,
    IntentLayoutPlan,
    IntentOperation,
    IntentSignal,
    IntentStewardInput,
)

logger = logging.getLogger(__name__)


async def llm_analyze_signals(
    service, filtered_signals: List[IntentSignal], context: IntentStewardInput
) -> Optional[IntentLayoutPlan]:
    try:
        from backend.app.shared.llm_provider_helper import (
            create_llm_provider_manager,
            get_llm_provider_from_settings,
            get_model_name_from_chat_model,
        )
        from backend.app.shared.llm_utils import build_prompt, call_llm

        model_name = get_model_name_from_chat_model()
        if not model_name:
            logger.warning("No chat model configured for LLM analysis")
            return None

        llm_manager = create_llm_provider_manager()
        try:
            llm_provider = get_llm_provider_from_settings(llm_manager)
        except Exception as exc:
            logger.warning(f"Could not get LLM provider: {exc}")
            return None

        system_prompt = _build_system_prompt(service)
        user_prompt = _build_user_prompt(filtered_signals, context)
        messages = build_prompt(system_prompt=system_prompt, user_prompt=user_prompt)
        response = await call_llm(
            messages=messages,
            llm_provider=llm_provider,
            model=model_name,
            temperature=0.3,
            max_tokens=2000,
        )
        content = response.get("content", "").strip()
        json_start = content.find("{")
        json_end = content.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            content = content[json_start:json_end]
        result = json.loads(content)
        return _layout_plan_from_llm_result(service, result, filtered_signals, context)
    except json.JSONDecodeError as exc:
        logger.warning(f"Failed to parse LLM JSON response: {exc}")
        return None
    except Exception as exc:
        logger.error(f"LLM analysis failed: {exc}", exc_info=True)
        return None


def _build_system_prompt(service) -> str:
    system_prompt = """You are an Intent Steward AI that analyzes user intent signals and decides which should become long-term IntentCards.

Rules:
- CREATE_INTENT_CARD: For signals that represent long-term goals or projects (confidence >= 0.75, appears important)
- UPDATE_INTENT_CARD: For signals that relate to existing IntentCards
- Ephemeral: For short-term tasks or low-priority items

Return JSON with this structure:
{
  "operations": [
    {
      "type": "CREATE_INTENT_CARD" or "UPDATE_INTENT_CARD",
      "intent_id": "existing_id" (only for UPDATE),
      "title": "Intent title",
      "description": "Brief description",
      "priority": "high" or "medium" or "low",
      "status": "active",
      "confidence": 0.0-1.0,
      "reasoning": "Why this decision"
    }
  ],
  "ephemeral": [
    {
      "title": "Task title",
      "reasoning": "Why ephemeral"
    }
  ]
}

Limit: Maximum 3 CREATE operations, 5 UPDATE operations."""
    workspace_id = getattr(service, "_current_workspace_id", None)
    if workspace_id:
        try:
            from backend.app.services.stores.postgres.workspaces_store import (
                PostgresWorkspacesStore,
            )
            from backend.app.services.workspace_instruction_helper import (
                build_workspace_instruction_block,
            )

            ws_store = PostgresWorkspacesStore()
            workspace = ws_store.get_workspace_sync(workspace_id)
            ws_block, _src = build_workspace_instruction_block(
                workspace, caller="intent_steward"
            )
            if ws_block:
                system_prompt = ws_block + "\n\n" + system_prompt
        except Exception as exc:
            logger.debug("IntentSteward: workspace instruction skipped: %s", exc)
    return system_prompt


def _build_user_prompt(
    filtered_signals: List[IntentSignal], context: IntentStewardInput
) -> str:
    signals_text = "\n".join(
        [
            f"- {index + 1}. {signal.label} (confidence: {signal.confidence:.2f})"
            for index, signal in enumerate(filtered_signals[:10])
        ]
    )
    current_intents_text = (
        "\n".join(
            [
                f"- {intent.title} ({intent.status.value}, {intent.priority.value})"
                for intent in context.current_intent_cards[:5]
            ]
        )
        if context.current_intent_cards
        else "None"
    )
    return f"""Analyze these intent signals:

Signals:
{signals_text}

Current IntentCards:
{current_intents_text}

Determine which signals should become IntentCards (CREATE or UPDATE) and which are ephemeral tasks.
Return only valid JSON, no additional text."""


def _layout_plan_from_llm_result(
    service,
    result,
    filtered_signals: List[IntentSignal],
    context: IntentStewardInput,
) -> IntentLayoutPlan:
    layout_plan = IntentLayoutPlan()
    max_operations = service.MAX_CREATE_INTENT_CARDS + service.MAX_UPDATE_INTENT_CARDS
    for op_data in result.get("operations", [])[:max_operations]:
        op_type = op_data.get("type", "")
        if op_type == "CREATE_INTENT_CARD":
            _append_llm_create(service, layout_plan, op_data, filtered_signals)
        elif op_type == "UPDATE_INTENT_CARD":
            _append_llm_update(service, layout_plan, op_data, filtered_signals, context)

    for ephem_data in result.get("ephemeral", [])[:10]:
        layout_plan.ephemeral_tasks.append(
            EphemeralTask(
                signal_id=filtered_signals[0].id if filtered_signals else "",
                title=ephem_data.get("title", ""),
                description=None,
                reasoning=ephem_data.get("reasoning", ""),
            )
        )

    logger.info(
        f"LLM analysis generated {len(layout_plan.long_term_intents)} operations, "
        f"{len(layout_plan.ephemeral_tasks)} ephemeral tasks"
    )
    return layout_plan


def _append_llm_create(
    service,
    layout_plan: IntentLayoutPlan,
    op_data,
    filtered_signals: List[IntentSignal],
) -> None:
    if len(layout_plan.long_term_intents) >= service.MAX_CREATE_INTENT_CARDS:
        return
    layout_plan.long_term_intents.append(
        IntentOperation(
            operation_type="CREATE_INTENT_CARD",
            intent_id=None,
            intent_data={
                "title": op_data.get("title", ""),
                "description": op_data.get("description", ""),
                "priority": op_data.get("priority", "medium"),
                "status": op_data.get("status", "active"),
            },
            relation_signals=[signal.id for signal in filtered_signals[:3]],
            confidence=op_data.get("confidence", 0.7),
            reasoning=op_data.get("reasoning", ""),
        )
    )


def _append_llm_update(
    service,
    layout_plan: IntentLayoutPlan,
    op_data,
    filtered_signals: List[IntentSignal],
    context: IntentStewardInput,
) -> None:
    max_operations = service.MAX_CREATE_INTENT_CARDS + service.MAX_UPDATE_INTENT_CARDS
    if len(layout_plan.long_term_intents) >= max_operations:
        return
    existing_intent = service._find_similar_intent(
        op_data.get("title", ""), context.current_intent_cards
    )
    if not existing_intent:
        return
    layout_plan.long_term_intents.append(
        IntentOperation(
            operation_type="UPDATE_INTENT_CARD",
            intent_id=existing_intent.id,
            intent_data={
                "title": op_data.get("title", existing_intent.title),
                "description": op_data.get(
                    "description", existing_intent.description or ""
                ),
                "priority": op_data.get("priority", existing_intent.priority.value),
                "status": op_data.get("status", existing_intent.status.value),
            },
            relation_signals=[signal.id for signal in filtered_signals[:3]],
            confidence=op_data.get("confidence", 0.7),
            reasoning=op_data.get("reasoning", ""),
        )
    )
