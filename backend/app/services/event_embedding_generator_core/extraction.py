import json
from typing import Optional

from backend.app.models.mindscape import EventType, MindEvent


def extract_text_from_event(event: MindEvent) -> Optional[str]:
    """Extract text content from event payload."""
    if not event.payload or not isinstance(event.payload, dict):
        return None

    if event.event_type == EventType.MESSAGE:
        return _extract_message_text(event)

    if (
        event.event_type == EventType.INTENT_CREATED
        or event.event_type == EventType.INTENT_UPDATED
    ):
        title = event.payload.get("title", "")
        description = event.payload.get("description", "")
        if title or description:
            return f"{title}\n{description}".strip()

    if event.event_type == EventType.PROJECT_UPDATED:
        description = event.payload.get("description", "")
        if description:
            return description

    if event.event_type == EventType.OBSIDIAN_NOTE_UPDATED:
        note_content = event.payload.get("content") or event.payload.get("body")
        note_title = event.payload.get("title", "")
        if note_content:
            return f"{note_title}\n\n{note_content}" if note_title else note_content

    if event.event_type == EventType.EXECUTION_PLAN:
        return _extract_execution_plan_text(event)

    return None


def _extract_message_text(event: MindEvent) -> Optional[str]:
    message = event.payload.get("message", "")

    if event.metadata and isinstance(event.metadata, dict):
        file_analysis = event.metadata.get("file_analysis", {})
        if file_analysis:
            collaboration = file_analysis.get("collaboration_results", {})
            file_info_data = file_analysis.get("file_info", {})

            extracted_text = (
                collaboration.get("extracted_text")
                or collaboration.get("summary")
                or collaboration.get("content")
                or file_analysis.get("extracted_text")
                or file_analysis.get("summary")
            )

            files = event.payload.get("files", [])
            file_name = ""
            if files and len(files) > 0:
                file_name = files[0].get("name", "unknown")
            elif file_info_data:
                file_name = file_info_data.get("name", "unknown")

            if extracted_text:
                file_info = f"File: {file_name}\n" if file_name else ""
                return f"{file_info}{extracted_text}"
            if file_name:
                return _build_file_info_text(file_name, file_info_data, collaboration)

    if message:
        return message

    return None


def _build_file_info_text(
    file_name: str, file_info_data: dict, collaboration: dict
) -> str:
    file_info_parts = [f"File: {file_name}"]
    if file_info_data:
        if file_info_data.get("type"):
            file_info_parts.append(f"Type: {file_info_data['type']}")
        if file_info_data.get("size"):
            file_info_parts.append(f"Size: {file_info_data['size']}")
        if file_info_data.get("pages"):
            file_info_parts.append(f"Pages: {file_info_data['pages']}")

    semantic_seeds = collaboration.get("semantic_seeds", {})
    if semantic_seeds.get("intents"):
        intents = semantic_seeds.get("intents", [])
        if intents:
            file_info_parts.append(f"Intents: {', '.join(intents[:5])}")

    return "\n".join(file_info_parts)


def _extract_execution_plan_text(event: MindEvent) -> str:
    summary = event.payload.get("summary", "")
    steps = event.payload.get("steps", [])

    text_parts = []
    if summary:
        text_parts.append(f"Plan Summary: {summary}")

    if steps and isinstance(steps, list):
        step_texts = []
        for i, step in enumerate(steps, 1):
            step_name = step.get("name", "") if isinstance(step, dict) else str(step)
            step_desc = step.get("description", "") if isinstance(step, dict) else ""
            if step_name:
                step_text = f"Step {i}: {step_name}"
                if step_desc:
                    step_text += f" - {step_desc}"
                step_texts.append(step_text)

        if step_texts:
            text_parts.append("Steps:\n" + "\n".join(step_texts))

    if text_parts:
        return "\n\n".join(text_parts)

    return json.dumps(event.payload, indent=2)
