"""Resource requirement resolution for runner admission."""

from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional

DB_WRITE_BUDGETS = ("none", "low", "medium", "high")
DURATION_CLASSES = ("short", "medium", "long")


@dataclass(frozen=True)
class ResourceRequirements:
    browser_contexts: int = 0
    ig_profile_lock: Optional[str] = None
    cpu_weight: int = 1
    memory_mb: int = 0
    vision_lane: Optional[str] = None
    llm_lane: Optional[str] = None
    db_write_budget: str = "low"
    expected_duration_class: str = "short"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _as_mapping(value: Any) -> dict[str, Any]:
    return copy.deepcopy(value) if isinstance(value, Mapping) else {}


def _positive_int(value: Any, default: int, *, minimum: int = 0, maximum: int = 100) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _optional_token(value: Any) -> Optional[str]:
    if value is None or value is False:
        return None
    if value is True:
        return "__auto__"
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, (dict, list, tuple, set)):
        return None
    stripped = str(value).strip()
    return stripped or None


def _enum(value: Any, allowed: tuple[str, ...], default: str) -> str:
    if not isinstance(value, str):
        return default
    normalized = value.strip().lower()
    return normalized if normalized in allowed else default


def _render_template(value: str, *, context: Mapping[str, Any], inputs: Mapping[str, Any]) -> str:
    rendered = value
    replacements = {
        "workspace_id": context.get("workspace_id") or inputs.get("workspace_id") or "",
        "pack_id": context.get("pack_id") or context.get("playbook_code") or "",
        "playbook_code": context.get("playbook_code") or context.get("pack_id") or "",
        "user_data_dir": inputs.get("user_data_dir") or "",
        "ig_profile_id": inputs.get("ig_profile_id") or inputs.get("profile_id") or "",
    }
    for key, replacement in replacements.items():
        rendered = rendered.replace("{" + key + "}", str(replacement or ""))
    return rendered.strip()


def _resolve_profile_lock(
    value: Any,
    *,
    context: Mapping[str, Any],
    inputs: Mapping[str, Any],
) -> Optional[str]:
    token = _optional_token(value)
    if not token:
        return None
    if token == "__auto__":
        token = (
            _optional_token(inputs.get("ig_profile_id"))
            or _optional_token(inputs.get("profile_id"))
            or _optional_token(inputs.get("user_data_dir"))
            or "default"
        )
    return _render_template(token, context=context, inputs=inputs) or None


def _coerce_requirements(
    raw: Mapping[str, Any],
    *,
    base: ResourceRequirements,
    context: Mapping[str, Any],
    inputs: Mapping[str, Any],
) -> ResourceRequirements:
    data = base.to_dict()
    if "browser_contexts" in raw:
        data["browser_contexts"] = _positive_int(
            raw.get("browser_contexts"),
            data["browser_contexts"],
        )
    if "ig_profile_lock" in raw:
        data["ig_profile_lock"] = _resolve_profile_lock(
            raw.get("ig_profile_lock"),
            context=context,
            inputs=inputs,
        )
    if "cpu_weight" in raw:
        data["cpu_weight"] = _positive_int(
            raw.get("cpu_weight"),
            data["cpu_weight"],
            minimum=1,
            maximum=100,
        )
    if "memory_mb" in raw:
        data["memory_mb"] = _positive_int(
            raw.get("memory_mb"),
            data["memory_mb"],
            minimum=0,
            maximum=1048576,
        )
    if "vision_lane" in raw:
        data["vision_lane"] = _resolve_lane(raw.get("vision_lane"))
    if "llm_lane" in raw:
        data["llm_lane"] = _resolve_lane(raw.get("llm_lane"))
    if "db_write_budget" in raw:
        data["db_write_budget"] = _enum(
            raw.get("db_write_budget"),
            DB_WRITE_BUDGETS,
            data["db_write_budget"],
        )
    if "expected_duration_class" in raw:
        data["expected_duration_class"] = _enum(
            raw.get("expected_duration_class"),
            DURATION_CLASSES,
            data["expected_duration_class"],
        )
    return ResourceRequirements(**data)


def _resolve_lane(value: Any) -> Optional[str]:
    token = _optional_token(value)
    if not token:
        return None
    if token == "__auto__":
        return "default"
    return token


def _metadata_resource_requirements(metadata: Mapping[str, Any]) -> dict[str, Any]:
    direct = _as_mapping(metadata.get("resource_requirements"))
    if direct:
        return direct
    execution_profile = _as_mapping(metadata.get("execution_profile"))
    return _as_mapping(execution_profile.get("resource_requirements"))


def _context_execution_profile_requirements(context: Mapping[str, Any]) -> dict[str, Any]:
    execution_profile = _as_mapping(context.get("execution_profile"))
    return _as_mapping(execution_profile.get("resource_requirements"))


def resolve_resource_requirements(
    task: Any,
    *,
    execution_context: Optional[Mapping[str, Any]] = None,
    playbook_metadata: Optional[Mapping[str, Any]] = None,
    pack_defaults: Optional[Mapping[str, Any]] = None,
) -> ResourceRequirements:
    """Resolve task resource requirements by the locked precedence order."""
    context = _as_mapping(execution_context)
    if not context and not isinstance(task, Mapping):
        context = _as_mapping(getattr(task, "execution_context", None))
    if isinstance(task, Mapping):
        context.setdefault("pack_id", task.get("pack_id"))
    else:
        context.setdefault("pack_id", getattr(task, "pack_id", None))

    inputs = _as_mapping(context.get("inputs"))
    metadata = _as_mapping(playbook_metadata)

    resolved = ResourceRequirements()
    for source in (
        _as_mapping(pack_defaults) or _as_mapping(context.get("pack_resource_defaults")),
        _metadata_resource_requirements(metadata),
        _context_execution_profile_requirements(context),
        _as_mapping(context.get("resource_requirements"))
        or _as_mapping(context.get("runner_resource_requirements")),
    ):
        if source:
            resolved = _coerce_requirements(
                source,
                base=resolved,
                context=context,
                inputs=inputs,
            )
    return resolved
