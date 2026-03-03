from typing import Any, Dict, List, Tuple

INSTRUCTION_FIELDS = (
    "persona",
    "goals",
    "anti_goals",
    "style_rules",
    "domain_context",
)
LIST_FIELDS = {"goals", "anti_goals", "style_rules"}


def normalize_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    normalized: List[str] = []
    for item in value:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


def normalize_instruction(raw_instruction: Any) -> Dict[str, Any]:
    if raw_instruction is None:
        return {
            "persona": None,
            "goals": [],
            "anti_goals": [],
            "style_rules": [],
            "domain_context": None,
        }

    if hasattr(raw_instruction, "model_dump"):
        data = raw_instruction.model_dump()
    elif isinstance(raw_instruction, dict):
        data = dict(raw_instruction)
    else:
        data = {}

    return {
        "persona": data.get("persona"),
        "goals": normalize_string_list(data.get("goals")),
        "anti_goals": normalize_string_list(data.get("anti_goals")),
        "style_rules": normalize_string_list(data.get("style_rules")),
        "domain_context": data.get("domain_context"),
    }


def merge_instruction_patch(
    current_instruction: Dict[str, Any], patch: Dict[str, Any]
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Merge semantics:
    - omitted field: no change
    - null: clear field
    - []: clear list
    """
    normalized_current = normalize_instruction(current_instruction)
    merged = dict(normalized_current)
    changed_fields: List[str] = []

    for field in INSTRUCTION_FIELDS:
        if field not in patch:
            continue
        changed_fields.append(field)
        value = patch[field]
        if field in LIST_FIELDS:
            if value is None:
                merged[field] = []
            else:
                merged[field] = normalize_string_list(value)
        else:
            merged[field] = value

    return merged, changed_fields

