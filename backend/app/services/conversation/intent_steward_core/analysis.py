"""Intent steward layout analysis."""

import logging
from typing import List, Optional

from backend.app.models.mindscape import (
    EphemeralTask,
    IntentLayoutPlan,
    IntentOperation,
    IntentSignal,
    IntentStewardInput,
    SignalMapping,
)

logger = logging.getLogger(__name__)


async def steward_analyze(
    service,
    filtered_signals: Optional[List[IntentSignal]] = None,
    context: Optional[IntentStewardInput] = None,
    *,
    workspace_id: Optional[str] = None,
    profile_id: Optional[str] = None,
    steward_input: Optional[IntentStewardInput] = None,
) -> IntentLayoutPlan:
    del profile_id
    if workspace_id:
        service._current_workspace_id = workspace_id
    if steward_input is not None:
        context = steward_input
        filtered_signals = await service.prefilter_signals(context.recent_signals)
    if filtered_signals is None:
        filtered_signals = []
    if context is None:
        context = IntentStewardInput(recent_signals=filtered_signals)

    layout_plan = IntentLayoutPlan()
    if not filtered_signals:
        return layout_plan

    try:
        llm_plan = await service._llm_analyze_signals(filtered_signals, context)
        if llm_plan and (llm_plan.long_term_intents or llm_plan.ephemeral_tasks):
            return llm_plan
    except Exception as exc:
        logger.warning(f"LLM analysis failed, falling back to rule-based: {exc}")

    signal_groups = {}
    for signal in filtered_signals:
        key = signal.label[:20].lower().strip()
        if key not in signal_groups:
            signal_groups[key] = []
        signal_groups[key].append(signal)

    for group_signals in signal_groups.values():
        if len(group_signals) == 0:
            continue

        representative = max(group_signals, key=lambda signal: signal.confidence)
        if representative.confidence >= 0.8 and len(group_signals) >= 2:
            existing_intent = service._find_similar_intent(
                representative.label, context.current_intent_cards
            )
            if existing_intent:
                _append_update_operation(
                    service,
                    layout_plan,
                    existing_intent,
                    representative,
                    group_signals,
                )
            else:
                _append_create_operation(
                    service,
                    layout_plan,
                    representative,
                    group_signals,
                )
        else:
            layout_plan.ephemeral_tasks.append(
                EphemeralTask(
                    signal_id=representative.id,
                    title=representative.label,
                    description=None,
                    reasoning=f"Signal confidence {representative.confidence:.2f} or "
                    f"occurrence count {len(group_signals)} below threshold",
                )
            )

        for signal in group_signals:
            layout_plan.signal_mapping.append(
                SignalMapping(
                    signal_id=signal.id,
                    action=(
                        "mapped_to_intent_id"
                        if len(group_signals) >= 2
                        and representative.confidence >= 0.8
                        else "ignored"
                    ),
                    target_intent_id=None,
                    reasoning=f"Grouped with {len(group_signals)} similar signals",
                )
            )

    return layout_plan


def _append_update_operation(
    service,
    layout_plan: IntentLayoutPlan,
    existing_intent,
    representative: IntentSignal,
    group_signals: List[IntentSignal],
) -> None:
    if len(layout_plan.long_term_intents) >= service.MAX_UPDATE_INTENT_CARDS:
        return
    layout_plan.long_term_intents.append(
        IntentOperation(
            operation_type="UPDATE_INTENT_CARD",
            intent_id=existing_intent.id,
            intent_data={
                "title": existing_intent.title,
                "description": existing_intent.description or "",
                "priority": existing_intent.priority.value,
                "status": existing_intent.status.value,
            },
            relation_signals=[signal.id for signal in group_signals],
            confidence=representative.confidence,
            reasoning=f"High confidence signal ({representative.confidence:.2f}) "
            f"with multiple occurrences ({len(group_signals)}) "
            f"matches existing IntentCard",
        )
    )


def _append_create_operation(
    service,
    layout_plan: IntentLayoutPlan,
    representative: IntentSignal,
    group_signals: List[IntentSignal],
) -> None:
    if len(layout_plan.long_term_intents) >= service.MAX_CREATE_INTENT_CARDS:
        return
    layout_plan.long_term_intents.append(
        IntentOperation(
            operation_type="CREATE_INTENT_CARD",
            intent_id=None,
            intent_data={
                "title": representative.label,
                "description": f"Auto-detected from {len(group_signals)} signals",
                "priority": "medium",
                "status": "active",
            },
            relation_signals=[signal.id for signal in group_signals],
            confidence=representative.confidence,
            reasoning=f"High confidence signal ({representative.confidence:.2f}) "
            f"with multiple occurrences ({len(group_signals)}) "
            f"warrants IntentCard creation",
        )
    )
