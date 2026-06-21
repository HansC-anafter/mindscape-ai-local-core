from backend.app.models.mindscape import EventType, MindEvent


def should_generate_embedding(event: MindEvent) -> bool:
    """
    Determine if an event should generate embedding.

    Only generates embeddings for stable artifacts, user-explicit saves,
    and completed playbook or plan outputs.
    """
    if event.metadata and isinstance(event.metadata, dict):
        if event.metadata.get("should_embed") is True:
            return True
        if event.metadata.get("is_final") is True:
            return True
        if event.metadata.get("is_artifact") is True:
            return True

    if (
        event.event_type == EventType.INTENT_CREATED
        or event.event_type == EventType.INTENT_UPDATED
    ):
        if event.payload and isinstance(event.payload, dict):
            status = event.payload.get("status")
            priority = event.payload.get("priority")
            if status == "completed" or priority in ["high", "critical"]:
                return True

    if event.event_type == EventType.PLAYBOOK_STEP:
        if event.payload and isinstance(event.payload, dict):
            if event.payload.get("is_final_output") is True:
                return True
            if (
                event.payload.get("step_type") == "output"
                and event.payload.get("status") == "completed"
            ):
                return True

    if event.event_type == EventType.MESSAGE:
        if event.metadata and isinstance(event.metadata, dict):
            if event.metadata.get("from_completed_playbook") is True:
                return True
            if event.metadata.get("is_artifact_output") is True:
                return True

    if event.event_type == EventType.OBSIDIAN_NOTE_UPDATED:
        if event.metadata and isinstance(event.metadata, dict):
            should_embed = event.metadata.get("should_embed", False)
            if should_embed:
                return True

    if event.event_type == EventType.EXECUTION_PLAN:
        return True

    return False


def map_event_type_to_seed_type(event_type: EventType) -> str:
    """Map event type to seed type for memory_embeddings."""
    mapping = {
        EventType.MESSAGE: "conversation",
        EventType.INTENT_CREATED: "intent",
        EventType.INTENT_UPDATED: "intent",
        EventType.PROJECT_UPDATED: "project",
        EventType.PLAYBOOK_STEP: "workflow",
        EventType.EXECUTION_PLAN: "plan",
    }
    return mapping.get(event_type, "general")
