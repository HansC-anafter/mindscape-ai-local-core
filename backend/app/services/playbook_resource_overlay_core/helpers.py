import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Mapping, Optional, Tuple


def _workspace_base_path(workspace: Any) -> Path:
    storage_base_path = getattr(workspace, "storage_base_path", None)
    if storage_base_path:
        return Path(storage_base_path)
    return Path(os.path.expanduser("~/Documents/Mindscape"))


def build_shared_resource_path(
    base_dir: Path,
    playbook: Any,
    resource_type: str,
    workspace: Optional[Any] = None,
) -> Optional[Path]:
    metadata = playbook.metadata
    scope_level = metadata.get_scope_level()
    playbook_code = metadata.playbook_code

    if scope_level == "workspace":
        return None

    if scope_level == "system":
        return (
            base_dir
            / "data"
            / "shared"
            / "playbooks"
            / playbook_code
            / "resources"
            / resource_type
        )

    if scope_level == "tenant" and workspace:
        tenant_id = getattr(workspace, "tenant_id", None)
        if tenant_id:
            return (
                base_dir
                / "data"
                / "tenants"
                / tenant_id
                / "playbooks"
                / playbook_code
                / "resources"
                / resource_type
            )

    if scope_level == "profile" and workspace:
        profile_id = getattr(workspace, "profile_id", None)
        if profile_id:
            return (
                base_dir
                / "data"
                / "profiles"
                / profile_id
                / "playbooks"
                / playbook_code
                / "resources"
                / resource_type
            )

    return None


def build_workspace_resource_path(
    workspace: Any, playbook_code: str, resource_type: str
) -> Path:
    return _workspace_base_path(workspace) / "playbooks" / playbook_code / "resources" / resource_type


def build_overlay_resource_path(
    workspace: Any, playbook_code: str, resource_type: str
) -> Path:
    return (
        _workspace_base_path(workspace)
        / "workspace_overlays"
        / "playbooks"
        / playbook_code
        / "resources"
        / resource_type
    )


def merge_resource_with_overlay(
    base_resource: Mapping[str, Any], overlay: Mapping[str, Any]
) -> Dict[str, Any]:
    merged = dict(base_resource)

    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_resource_with_overlay(merged[key], value)
        else:
            merged[key] = value

    return merged


def get_binding_resource_overlay(
    binding: Any, resource_type: str, resource_id: str
) -> Mapping[str, Any]:
    overrides = getattr(binding, "overrides", None) or {}
    return (
        overrides.get("resources", {})
        .get(resource_type, {})
        .get(resource_id, {})
    )


def iter_binding_resource_overlays(
    binding: Any, resource_type: str
) -> Iterator[Tuple[str, Mapping[str, Any]]]:
    overrides = getattr(binding, "overrides", None) or {}
    resource_overlays = overrides.get("resources", {}).get(resource_type, {})
    return iter(resource_overlays.items())


def sort_resources_by_created_at(
    resources: Iterable[Mapping[str, Any]]
) -> list[Mapping[str, Any]]:
    return sorted(resources, key=lambda item: item.get("created_at", ""), reverse=True)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
