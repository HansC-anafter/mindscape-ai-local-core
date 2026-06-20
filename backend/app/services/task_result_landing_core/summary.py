"""Summary extraction helpers for task result landing."""

from typing import Any, Dict

from app.services.task_result_landing_core.common import DATA_SOURCE_SUMMARY_LIMIT


def extract_result_summary(result_data: Dict[str, Any]) -> str:
    """Extract a compact metrics summary from task result payload."""
    if not result_data:
        return ""
    steps = result_data.get("steps") or {}
    for step_data in steps.values():
        outputs = step_data.get("outputs") or step_data.get("step_outputs", {})
        if isinstance(outputs, dict):
            flat = {}
            for value in outputs.values():
                if isinstance(value, dict):
                    flat.update(value)
                else:
                    flat = outputs
                    break
            if flat:
                parts = []
                for key, value in flat.items():
                    compact_value = compact_summary_value(value)
                    if compact_value:
                        parts.append(f"{key}={compact_value}")
                if parts:
                    return limit_summary_text(", ".join(parts[:5]))
    status = result_data.get("status")
    if not status:
        return ""
    return limit_summary_text(str(status))


def compact_summary_value(value: Any) -> str:
    """Return a compact display string for a nested result value."""
    if value is None:
        return ""
    if isinstance(value, (bool, int, float)):
        return str(value)
    if isinstance(value, str):
        return limit_summary_text(value)
    if isinstance(value, dict):
        summary_parts = []
        storyboard_id = value.get("storyboard_id")
        scenes = value.get("scenes")
        if storyboard_id is not None:
            summary_parts.append(f"storyboard_id={storyboard_id}")
        if isinstance(scenes, list):
            summary_parts.append(f"scenes={len(scenes)}")
        if summary_parts:
            return limit_summary_text(", ".join(summary_parts))

        scalar_parts = []
        for key, nested_value in value.items():
            if nested_value is None:
                continue
            if isinstance(nested_value, (bool, int, float, str)):
                nested_text = limit_summary_text(str(nested_value), limit=120)
                scalar_parts.append(f"{key}={nested_text}")
            if len(scalar_parts) >= 3:
                break
        if scalar_parts:
            return limit_summary_text("{" + ", ".join(scalar_parts) + "}")

        keys = ", ".join(str(key) for key in list(value.keys())[:5])
        return f"object(keys={keys}, count={len(value)})"
    if isinstance(value, (list, tuple, set)):
        return f"list(count={len(value)})"
    return limit_summary_text(str(value))


def limit_summary_text(
    value: str,
    *,
    limit: int = DATA_SOURCE_SUMMARY_LIMIT,
) -> str:
    """Trim a summary string to the configured storage limit."""
    text_value = str(value).strip()
    if len(text_value) <= limit:
        return text_value
    return text_value[: limit - 3].rstrip() + "..."
