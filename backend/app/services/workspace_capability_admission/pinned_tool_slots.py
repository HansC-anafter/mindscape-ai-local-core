"""Admission-time tool-slot pinning for durable playbook execution."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from backend.app.services.capability_registry import get_registry, reload_capability
from backend.app.services.playbook_loaders.json_loader import PlaybookJsonLoader
from backend.app.services.tool_slot_resolver import (
    ToolSlotResolution,
    get_tool_slot_resolver,
)

PIN_SCHEMA_VERSION = "mindscape.execution-tool-slot-pins.v1"


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def declared_pinned_tool_slots(playbook_code: str) -> tuple[str, ...]:
    """Load and normalize the slots declared by the installed playbook spec."""
    playbook = PlaybookJsonLoader.load_playbook_json(playbook_code)
    profile = getattr(playbook, "execution_profile", None) if playbook else None
    if not isinstance(profile, dict):
        return ()
    declared = profile.get("admission_pinned_tool_slots")
    if declared is None:
        return ()
    if not isinstance(declared, list):
        raise ValueError("admission_pinned_tool_slots_must_be_list")
    normalized: list[str] = []
    for raw_slot in declared:
        slot = str(raw_slot or "").strip()
        if not slot:
            raise ValueError("admission_pinned_tool_slot_empty")
        if slot in normalized:
            raise ValueError(
                f"admission_pinned_tool_slot_duplicate:{slot}"
            )
        normalized.append(slot)
    return tuple(normalized)


def _provider_evidence(resolution: ToolSlotResolution) -> dict[str, Any]:
    tool_id = resolution.tool_id
    capability_code = tool_id.split(".", 1)[0]
    registry = get_registry()
    tool_info = registry.get_tool(tool_id)
    capability_info = registry.get_capability(capability_code)
    if tool_info is None or capability_info is None:
        if reload_capability(capability_code):
            registry = get_registry()
            tool_info = registry.get_tool(tool_id)
            capability_info = registry.get_capability(capability_code)
    if tool_info is None or capability_info is None:
        raise ValueError(f"pinned_tool_provider_not_installed:{tool_id}")

    capability_dir = Path(capability_info["directory"])
    manifest_path = capability_dir / "manifest.yaml"
    if not manifest_path.is_file():
        raise ValueError(
            f"pinned_tool_provider_manifest_missing:{capability_code}"
        )
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    manifest = capability_info.get("manifest")
    version = (
        str(manifest.get("version") or "").strip()
        if isinstance(manifest, dict)
        else ""
    )
    backend = str(tool_info.get("backend") or "").strip()
    if not version or not backend:
        raise ValueError(f"pinned_tool_provider_metadata_incomplete:{tool_id}")
    backend_module = backend.split(":", 1)[0]
    module_parts = backend_module.split(".")
    try:
        capability_index = module_parts.index(capability_code)
    except ValueError as exc:
        raise ValueError(
            f"pinned_tool_provider_backend_outside_pack:{tool_id}"
        ) from exc
    relative_parts = module_parts[capability_index + 1 :]
    backend_path = capability_dir.joinpath(*relative_parts)
    backend_file = backend_path.with_suffix(".py")
    if not backend_file.is_file():
        backend_file = backend_path / "__init__.py"
    try:
        backend_file = backend_file.resolve(strict=True)
        backend_file.relative_to(capability_dir.resolve(strict=True))
    except (FileNotFoundError, ValueError) as exc:
        raise ValueError(
            f"pinned_tool_provider_artifact_missing:{tool_id}"
        ) from exc
    return {
        "provider_pack": capability_code,
        "provider_version": version,
        "provider_manifest_sha256": manifest_sha256,
        "tool_backend": backend,
        "tool_artifact_sha256": hashlib.sha256(
            backend_file.read_bytes()
        ).hexdigest(),
    }


def _build_pin(resolution: ToolSlotResolution) -> dict[str, Any]:
    mapping = {
        "kind": resolution.mapping_kind,
        "id": resolution.mapping_id,
        "updated_at": resolution.mapping_updated_at,
        "project_id": resolution.project_id,
    }
    return {
        "slot": resolution.slot,
        "tool_id": resolution.tool_id,
        "mapping": mapping,
        "mapping_revision_sha256": _canonical_sha256(mapping),
        **_provider_evidence(resolution),
    }


def _validate_existing_pins(
    *,
    normalized_inputs: Mapping[str, Any],
    declared_slots: Sequence[str],
    playbook_code: str | None = None,
    workspace_id: str | None = None,
    project_id: str | None = None,
) -> None:
    payload = normalized_inputs.get("pinned_tool_slots")
    digest = normalized_inputs.get("pinned_tool_slots_sha256")
    declared_payload = normalized_inputs.get("admission_pinned_tool_slots")
    if not isinstance(payload, dict) or not isinstance(digest, str):
        raise ValueError("pinned_tool_slots_missing")
    if declared_payload != list(declared_slots):
        raise ValueError("pinned_tool_slot_declaration_mismatch")
    if payload.get("schema_version") != PIN_SCHEMA_VERSION:
        raise ValueError("pinned_tool_slots_schema_mismatch")
    if playbook_code is not None and payload.get("playbook_code") != playbook_code:
        raise ValueError("pinned_tool_slots_playbook_mismatch")
    if workspace_id is not None and payload.get("workspace_id") != workspace_id:
        raise ValueError("pinned_tool_slots_workspace_mismatch")
    if project_id is not None and payload.get("project_id") != project_id:
        raise ValueError("pinned_tool_slots_project_mismatch")
    root_execution_id = str(
        normalized_inputs.get("execution_id")
        or normalized_inputs.get("root_execution_id")
        or ""
    )
    if root_execution_id and payload.get("root_execution_id") != root_execution_id:
        raise ValueError("pinned_tool_slots_execution_mismatch")
    pins = payload.get("pins")
    if not isinstance(pins, dict) or sorted(pins) != sorted(declared_slots):
        raise ValueError("pinned_tool_slots_scope_mismatch")
    if _canonical_sha256(payload) != digest:
        raise ValueError("pinned_tool_slots_hash_mismatch")


async def prepare_pinned_tool_slots(
    *,
    normalized_inputs: dict[str, Any],
    declared_slots: Sequence[str],
    playbook_code: str,
    workspace_id: str,
    project_id: str | None,
    resolver: Any | None = None,
) -> dict[str, Any]:
    """Create pins at root admission or verify the carried pins for a child."""
    if not declared_slots:
        return normalized_inputs
    if not workspace_id:
        raise ValueError("admission_pinned_tool_slots_require_workspace")

    existing = normalized_inputs.get("pinned_tool_slots")
    if existing is not None:
        _validate_existing_pins(
            normalized_inputs=normalized_inputs,
            declared_slots=declared_slots,
            playbook_code=playbook_code,
            workspace_id=workspace_id,
            project_id=project_id,
        )
        return normalized_inputs

    slot_resolver = resolver or get_tool_slot_resolver()
    pins: dict[str, Any] = {}
    for slot in declared_slots:
        resolution = await slot_resolver.resolve_with_evidence(
            slot=slot,
            workspace_id=workspace_id,
            project_id=project_id,
        )
        pins[slot] = _build_pin(resolution)

    payload = {
        "schema_version": PIN_SCHEMA_VERSION,
        "playbook_code": playbook_code,
        "root_execution_id": str(
            normalized_inputs.get("execution_id")
            or normalized_inputs.get("root_execution_id")
            or ""
        ),
        "workspace_id": workspace_id,
        "project_id": project_id,
        "pins": pins,
    }
    normalized_inputs["admission_pinned_tool_slots"] = list(declared_slots)
    normalized_inputs["pinned_tool_slots"] = payload
    normalized_inputs["pinned_tool_slots_sha256"] = _canonical_sha256(payload)
    return normalized_inputs


def resolve_pinned_tool_id(
    *,
    slot: str,
    playbook_inputs: Mapping[str, Any],
) -> str | None:
    """Return a verified pinned tool id, or None for an unpinned legacy slot."""
    declared = playbook_inputs.get("admission_pinned_tool_slots")
    if not isinstance(declared, list) or slot not in declared:
        return None
    _validate_existing_pins(
        normalized_inputs=playbook_inputs,
        declared_slots=tuple(str(value) for value in declared),
    )
    payload = playbook_inputs["pinned_tool_slots"]
    pin = payload["pins"].get(slot)
    tool_id = str(pin.get("tool_id") or "").strip() if isinstance(pin, dict) else ""
    if not tool_id:
        raise ValueError(f"pinned_tool_id_missing:{slot}")
    return tool_id
