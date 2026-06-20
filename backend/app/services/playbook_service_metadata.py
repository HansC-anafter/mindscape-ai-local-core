from typing import Any, Dict, List, Optional

from backend.app.models.playbook import (
    PlaybookMetadata,
    PlaybookOwnerType,
    PlaybookVisibility,
)


def filter_playbooks_by_runtime_tier(
    playbooks: List[PlaybookMetadata],
    runtime_tier: Optional[str],
) -> List[PlaybookMetadata]:
    """Filter playbooks by the existing runtime-tier rules."""
    if not runtime_tier:
        return playbooks

    filtered_playbooks = []
    for playbook in playbooks:
        playbook_runtime_tier = getattr(playbook, "runtime_tier", None)
        if runtime_tier == "local":
            if playbook_runtime_tier != "cloud_only":
                filtered_playbooks.append(playbook)
        elif runtime_tier == "cloud_recommended":
            filtered_playbooks.append(playbook)
        elif runtime_tier == "cloud_only":
            if playbook_runtime_tier == "cloud_only":
                filtered_playbooks.append(playbook)
    return filtered_playbooks


async def list_by_owner_type_for_service(
    *,
    service: Any,
    owner_type: PlaybookOwnerType,
    owner_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """List playbooks by owner type using the public service query path."""
    all_playbooks = await service.list_playbooks()
    filtered = []
    for metadata in all_playbooks:
        metadata_owner_type = getattr(metadata, "owner_type", None)
        metadata_owner_id = getattr(metadata, "owner_id", None)

        if metadata_owner_type:
            if metadata_owner_type == owner_type:
                if owner_id is None or metadata_owner_id == owner_id:
                    filtered.append(metadata_to_dict(metadata))
            continue

        legacy_scope = getattr(metadata, "scope", {})
        legacy_owner = getattr(metadata, "owner", {})
        if owner_type == PlaybookOwnerType.SYSTEM:
            if legacy_scope.get("visibility") == "system":
                filtered.append(metadata_to_dict(metadata))
        elif owner_type == PlaybookOwnerType.WORKSPACE:
            if legacy_scope.get("visibility") == "workspace":
                if owner_id is None or legacy_owner.get("workspace_id") == owner_id:
                    filtered.append(metadata_to_dict(metadata))
        elif owner_type == PlaybookOwnerType.USER:
            if legacy_owner.get("type") in ("user", "profile"):
                if owner_id is None or legacy_owner.get("profile_id") == owner_id:
                    filtered.append(metadata_to_dict(metadata))

    return filtered


def metadata_to_dict(metadata: PlaybookMetadata) -> Dict[str, Any]:
    """Convert PlaybookMetadata to PlaybookScopeResolver dict format."""
    result = {
        "playbook_code": metadata.playbook_code,
        "version": metadata.version,
        "name": metadata.name,
        "description": metadata.description,
        "tags": metadata.tags,
        "kind": (
            metadata.kind.value if hasattr(metadata.kind, "value") else metadata.kind
        ),
        "interaction_mode": [
            mode.value if hasattr(mode, "value") else mode
            for mode in metadata.interaction_mode
        ],
        "visible_in": [
            visible.value if hasattr(visible, "value") else visible
            for visible in metadata.visible_in
        ],
    }

    if hasattr(metadata, "owner_type"):
        result["owner_type"] = (
            metadata.owner_type.value
            if hasattr(metadata.owner_type, "value")
            else metadata.owner_type
        )
    else:
        legacy_scope = getattr(metadata, "scope", {})
        if legacy_scope.get("visibility") == "system":
            result["owner_type"] = PlaybookOwnerType.SYSTEM.value
        elif legacy_scope.get("visibility") == "workspace":
            result["owner_type"] = PlaybookOwnerType.WORKSPACE.value
        else:
            result["owner_type"] = PlaybookOwnerType.USER.value

    if hasattr(metadata, "owner_id"):
        result["owner_id"] = metadata.owner_id
    else:
        legacy_owner = getattr(metadata, "owner", {})
        if result["owner_type"] == PlaybookOwnerType.WORKSPACE.value:
            result["owner_id"] = legacy_owner.get("workspace_id", "default_workspace")
        elif result["owner_type"] == PlaybookOwnerType.USER.value:
            result["owner_id"] = legacy_owner.get("profile_id", "default_user")
        else:
            result["owner_id"] = "system"

    if hasattr(metadata, "visibility"):
        result["visibility"] = (
            metadata.visibility.value
            if hasattr(metadata.visibility, "value")
            else metadata.visibility
        )
    else:
        legacy_scope = getattr(metadata, "scope", {})
        if legacy_scope.get("visibility") in ("system", "tenant", "profile"):
            result["visibility"] = PlaybookVisibility.TENANT_SHARED.value
        else:
            result["visibility"] = PlaybookVisibility.WORKSPACE_SHARED.value

    result["capability_tags"] = (
        metadata.capability_tags if hasattr(metadata, "capability_tags") else []
    )
    result["project_types"] = (
        metadata.project_types if hasattr(metadata, "project_types") else None
    )
    result["shared_with_workspaces"] = (
        metadata.shared_with_workspaces
        if hasattr(metadata, "shared_with_workspaces")
        else []
    )
    result["allowed_tools"] = (
        metadata.allowed_tools if hasattr(metadata, "allowed_tools") else None
    )
    return result
