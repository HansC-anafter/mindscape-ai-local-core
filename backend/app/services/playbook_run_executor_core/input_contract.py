"""Input contract helpers for PlaybookRunExecutor."""

from copy import deepcopy
from typing import Any, Dict


def is_missing_playbook_input(value: Any) -> bool:
    """Return whether a playbook input value is missing."""
    return value is None or (isinstance(value, str) and not value.strip())


def definition_value(definition: Any, key: str, default: Any = None) -> Any:
    """Read an input definition value from mapping or object form."""
    if isinstance(definition, dict):
        return definition.get(key, default)
    return getattr(definition, key, default)


def apply_playbook_input_contract(
    playbook_code: str,
    playbook_run: Any,
    inputs: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply required-input checks and default values for a playbook run."""
    normalized_inputs = dict(inputs or {})
    playbook_json = getattr(playbook_run, "playbook_json", None)
    input_definitions = getattr(playbook_json, "inputs", None)
    if not isinstance(input_definitions, dict):
        return normalized_inputs

    missing_required = []
    for input_name, definition in input_definitions.items():
        if not is_missing_playbook_input(normalized_inputs.get(input_name)):
            continue
        default_value = definition_value(definition, "default")
        if default_value is not None:
            normalized_inputs[input_name] = deepcopy(default_value)
            continue
        if bool(definition_value(definition, "required", True)):
            missing_required.append(input_name)

    if missing_required:
        missing = ", ".join(sorted(missing_required))
        raise ValueError(
            f"Missing required playbook inputs for {playbook_code}: {missing}"
        )

    return normalized_inputs
