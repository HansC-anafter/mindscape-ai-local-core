"""Validated in-process registry for installed pack task projection adapters."""

from __future__ import annotations

import fnmatch
import threading
from pathlib import Path
from typing import Any, Mapping, Optional

from .models import TaskProjectionAdapterDefinition


_LOCK = threading.RLock()
_DEFINITIONS: dict[str, TaskProjectionAdapterDefinition] = {}


def register_definition(definition: TaskProjectionAdapterDefinition) -> None:
    definition.validate()
    with _LOCK:
        _DEFINITIONS[definition.capability_code] = definition


def unregister_definition(capability_code: str) -> None:
    with _LOCK:
        _DEFINITIONS.pop(str(capability_code), None)


def register_manifest(
    capability_code: str,
    manifest: Mapping[str, Any],
    capability_dir: Path,
) -> Optional[TaskProjectionAdapterDefinition]:
    raw = manifest.get("task_projection_adapter")
    unregister_definition(capability_code)
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        raise ValueError("task_projection_adapter_manifest_must_be_mapping")
    definition = TaskProjectionAdapterDefinition(
        capability_code=str(capability_code),
        pack_id_patterns=tuple(str(item) for item in raw.get("pack_id_patterns", ())),
        backend_path=str(raw.get("backend") or ""),
        table=str(raw.get("table") or ""),
        identity_fields=tuple(str(item) for item in raw.get("identity_fields", ())),
        indexes=tuple(str(item) for item in raw.get("indexes", ())),
        display_backend_path=str(raw.get("display_backend") or ""),
        display_bulk_backend_path=str(raw.get("display_bulk_backend") or ""),
        capability_dir=Path(capability_dir),
    )
    register_definition(definition)
    return definition


def resolve_definition(pack_id: str) -> Optional[TaskProjectionAdapterDefinition]:
    normalized = str(pack_id or "").strip()
    if not normalized:
        return None
    with _LOCK:
        definitions = tuple(_DEFINITIONS.values())
    matches = [
        definition
        for definition in definitions
        if any(
            fnmatch.fnmatchcase(normalized, pattern)
            for pattern in definition.pack_id_patterns
        )
    ]
    if len(matches) > 1:
        owners = ",".join(sorted(item.capability_code for item in matches))
        raise RuntimeError(f"task_projection_adapter_ambiguous_owner:{owners}")
    return matches[0] if matches else None


def reset_registry_for_tests() -> None:
    with _LOCK:
        _DEFINITIONS.clear()
