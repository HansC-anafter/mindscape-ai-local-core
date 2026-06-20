"""Template and content helpers for playbook output artifacts."""

import json
import re
from typing import Any, Dict


def resolve_template(template: str, context: Dict[str, Any]) -> str:
    """
    Resolve template variables in a string.

    Args:
        template: Template string with variables
        context: Context dictionary with step, input, execution_id, etc.

    Returns:
        Resolved string
    """
    if not template:
        return ""

    def replace_var(match):
        var_path = match.group(1).strip()
        parts = var_path.split(".")

        if parts[0] == "execution_id":
            return str(context.get("execution_id", ""))
        if parts[0] == "workspace_id":
            return str(context.get("workspace_id", ""))
        if parts[0] == "intent_id":
            return str(context.get("intent_id", ""))
        if parts[0] == "step":
            if len(parts) >= 3:
                step_id = parts[1]
                output_key = ".".join(parts[2:])
                step_outputs = context.get("step", {})
                if step_id in step_outputs:
                    value = get_nested_value(step_outputs[step_id], output_key)
                    return str(value) if value is not None else ""
        if parts[0] == "input":
            if len(parts) >= 2:
                input_key = ".".join(parts[1:])
                inputs = context.get("input", {})
                value = get_nested_value(inputs, input_key)
                if value is None or value == "":
                    if input_key == "source_content":
                        return "specified_content"
                    return ""
                return str(value)
        if parts[0] == "artifact":
            if len(parts) >= 2:
                artifact_key = parts[1]
                artifact_info = context.get("artifact", {})
                value = artifact_info.get(artifact_key)
                return str(value) if value is not None else ""
        if len(parts) == 1 and parts[0] == "title":
            value = context.get("title")
            if value is None:
                artifact_info = context.get("artifact", {})
                value = artifact_info.get("title")
            return str(value) if value is not None else ""

        value = get_nested_value(context, var_path)
        if value is not None:
            return str(value)
        if parts and parts[0] in context:
            return ""

        return match.group(0)

    pattern = r"\{\{([^}]+)\}\}"
    return re.sub(pattern, replace_var, template)


def get_nested_value(data: Any, path: str) -> Any:
    """
    Get a nested value from a dictionary using dot notation.

    Args:
        data: Dictionary or nested structure
        path: Dot-separated path

    Returns:
        Value at path or None if not found
    """
    if not path or not data:
        return None

    parts = path.split(".")
    current = data

    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                index = int(part)
                if 0 <= index < len(current):
                    current = current[index]
                else:
                    return None
            except (ValueError, TypeError):
                return None
        else:
            return None

        if current is None:
            return None

    return current


def _resolve_context_path(context: Dict[str, Any], path: str) -> Any:
    normalized_path = str(path or "").strip()
    if not normalized_path:
        return None
    return get_nested_value(context, normalized_path)


def _serialize_artifact_file_content(source_data: Any) -> str:
    if isinstance(source_data, dict):
        data_to_write = (
            source_data.get("content") if "content" in source_data else source_data
        )
    else:
        data_to_write = source_data

    if isinstance(data_to_write, str):
        return data_to_write
    if isinstance(data_to_write, bytes):
        return data_to_write.decode("utf-8")
    if isinstance(data_to_write, (dict, list)):
        return json.dumps(data_to_write, ensure_ascii=False, indent=2)
    return str(data_to_write)
