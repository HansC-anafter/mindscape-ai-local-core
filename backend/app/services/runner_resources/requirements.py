"""Resource requirement resolution for runner admission."""

from __future__ import annotations

import copy
import posixpath
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional

from .requirement_variants import select_requirement_variant

DB_WRITE_BUDGETS = ("none", "low", "medium", "high")
DURATION_CLASSES = ("short", "medium", "long")


@dataclass(frozen=True)
class ResourceRequirements:
    resource_class: Optional[str] = None
    browser_contexts: int = 0
    ig_profile_lock: Optional[str] = None
    cpu_weight: int = 1
    memory_mb: int = 0
    memory_profile_id: Optional[str] = None
    memory_reservation_source: Optional[str] = None
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
    resolved = _render_template(token, context=context, inputs=inputs)
    if resolved.startswith("/"):
        resolved = posixpath.normpath(resolved)
    return resolved or None


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
    if "memory_profile_id" in raw:
        data["memory_profile_id"] = _optional_token(raw.get("memory_profile_id"))
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


def _metadata_requirement_variant(
    metadata: Mapping[str, Any],
    *,
    inputs: Mapping[str, Any],
) -> dict[str, Any]:
    raw_variants = metadata.get("resource_requirement_variants")
    if raw_variants is None:
        execution_profile = _as_mapping(metadata.get("execution_profile"))
        raw_variants = execution_profile.get("resource_requirement_variants")
    return select_requirement_variant(raw_variants, inputs=inputs)


def _context_execution_profile_requirements(context: Mapping[str, Any]) -> dict[str, Any]:
    execution_profile = _as_mapping(context.get("execution_profile"))
    return _as_mapping(execution_profile.get("resource_requirements"))


def _execution_profile_resource_class(
    metadata: Mapping[str, Any],
    context: Mapping[str, Any],
) -> Optional[str]:
    for raw_value in (
        context.get("resource_class"),
        metadata.get("resource_class"),
    ):
        token = _optional_token(raw_value)
        if token:
            return token.lower()
    for raw_profile in (
        _as_mapping(context.get("execution_profile")),
        _as_mapping(metadata.get("execution_profile")),
    ):
        token = _optional_token(raw_profile.get("resource_class"))
        if token:
            return token.lower()
    return None


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
    sources = (
        _as_mapping(pack_defaults) or _as_mapping(context.get("pack_resource_defaults")),
        _metadata_resource_requirements(metadata),
        _metadata_requirement_variant(metadata, inputs=inputs),
        _context_execution_profile_requirements(context),
        _as_mapping(context.get("resource_requirements"))
        or _as_mapping(context.get("runner_resource_requirements")),
    )
    browser_contexts_declared = any(
        "browser_contexts" in source for source in sources if source
    )
    memory_declared = any("memory_mb" in source for source in sources if source)
    for source in sources:
        if source:
            resolved = _coerce_requirements(
                source,
                base=resolved,
                context=context,
                inputs=inputs,
            )
    resource_class = _execution_profile_resource_class(metadata, context)
    data = resolved.to_dict()
    data["resource_class"] = resource_class
    if (
        resource_class == "browser"
        and not browser_contexts_declared
        and resolved.browser_contexts == 0
    ):
        data["browser_contexts"] = 1
    if memory_declared and resolved.memory_mb > 0:
        data["memory_reservation_source"] = "playbook_profile"
    resolved = ResourceRequirements(**data)
    return resolved
