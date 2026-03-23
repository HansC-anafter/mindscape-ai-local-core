"""Step-event helpers for workspace execution routes."""

from __future__ import annotations

from backend.app.models.workspace import PlaybookExecutionStep


def build_step_payloads(
    step_events,
    *,
    logger,
    step_factory=PlaybookExecutionStep.from_mind_event,
):
    """Convert step events into serialized step payloads."""
    steps = []
    for event in step_events:
        try:
            step = step_factory(event)
            steps.append(step.model_dump() if hasattr(step, "model_dump") else step)
        except Exception as exc:
            logger.warning(
                "Failed to create PlaybookExecutionStep from event %s: %s",
                getattr(event, "id", "<unknown>"),
                exc,
            )
    return steps


def group_step_events_by_execution(events):
    """Group PLAYBOOK_STEP events by execution ID and sort by step index."""
    steps_by_execution = {}
    for event in events:
        payload = event.payload if isinstance(event.payload, dict) else {}
        execution_id = payload.get("execution_id")
        if not execution_id:
            continue
        steps_by_execution.setdefault(execution_id, []).append(event)

    for execution_id in steps_by_execution:
        steps_by_execution[execution_id].sort(
            key=lambda event: (event.payload or {}).get("step_index", 0)
        )
    return steps_by_execution


def get_current_step_payload(
    events,
    *,
    execution_id: str,
    current_step_index: int,
    logger,
    step_factory=PlaybookExecutionStep.from_mind_event,
):
    """Return the current step payload for one execution when available."""
    matching_events = [
        event
        for event in events
        if event.event_type.name == "PLAYBOOK_STEP"
        and isinstance(event.payload, dict)
        and event.payload.get("execution_id") == execution_id
        and event.payload.get("step_index") == current_step_index
    ]
    if not matching_events:
        return None

    try:
        current_step = step_factory(matching_events[0])
        return (
            current_step.model_dump()
            if hasattr(current_step, "model_dump")
            else current_step
        )
    except Exception as exc:
        logger.warning("Failed to create current_step from event: %s", exc)
        return None
