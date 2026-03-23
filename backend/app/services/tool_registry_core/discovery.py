"""Discovery helpers for ToolRegistryService."""

from __future__ import annotations

from typing import Dict, Tuple

from backend.app.models.tool_registry import RegisteredTool, ToolConnectionModel
from backend.app.services.tools.base import ToolConnection
from backend.app.services.tools.discovery_provider import DiscoveredTool, ToolConfig


def build_registered_tool(
    *,
    tool_id: str,
    connection_id: str,
    provider_name: str,
    discovered_tool: DiscoveredTool,
    side_effect_level: str,
    tool_scope: str,
    tool_tenant_id: str | None,
    tool_owner_profile_id: str | None,
) -> RegisteredTool:
    """Build a RegisteredTool from discovery output."""
    capability_code = (
        discovered_tool.tool_id.split(".")[0]
        if "." in discovered_tool.tool_id
        else discovered_tool.tool_id
    )
    risk_class = {
        "readonly": "readonly",
        "soft_write": "soft_write",
        "external_write": "external_write",
    }.get(side_effect_level, "readonly")

    return RegisteredTool(
        tool_id=tool_id,
        site_id=connection_id,
        provider=provider_name,
        display_name=discovered_tool.display_name,
        origin_capability_id=discovered_tool.tool_id,
        category=discovered_tool.category,
        description=discovered_tool.description,
        endpoint=discovered_tool.endpoint,
        methods=discovered_tool.methods,
        danger_level=discovered_tool.danger_level,
        input_schema=discovered_tool.input_schema,
        enabled=True,
        read_only=(discovered_tool.danger_level == "high"),
        side_effect_level=side_effect_level,
        scope=tool_scope,
        tenant_id=tool_tenant_id,
        owner_profile_id=tool_owner_profile_id,
        capability_code=capability_code,
        risk_class=risk_class,
    )


def build_dynamic_tool_connection(
    *,
    connection_id: str,
    config: ToolConfig,
    display_name: str,
) -> ToolConnection:
    """Build the dynamic tool registry connection payload."""
    return ToolConnection(
        id=connection_id,
        tool_type=config.tool_type,
        connection_type=config.connection_type,
        api_key=config.api_key,
        api_secret=config.api_secret,
        base_url=config.base_url,
        name=display_name,
    )


def upsert_discovery_connection(
    connections_by_key: Dict[Tuple[str, str], ToolConnectionModel],
    *,
    profile_id: str,
    connection_id: str,
    provider_name: str,
    config: ToolConfig,
    utc_now,
) -> None:
    """Create or update the persisted connection row after discovery."""
    key = (profile_id, connection_id)
    if key in connections_by_key:
        connection = connections_by_key[key]
        if config.custom_config:
            connection.config.update(config.custom_config)
        connection.last_discovery = utc_now()
        connection.updated_at = utc_now()
        return

    connections_by_key[key] = ToolConnectionModel(
        id=connection_id,
        profile_id=profile_id,
        name=f"{provider_name} - {connection_id}",
        tool_type=config.tool_type,
        connection_type=config.connection_type,
        base_url=config.base_url,
        api_key=config.api_key,
        api_secret=config.api_secret,
        wp_url=config.base_url if config.tool_type == "wordpress" else None,
        wp_username=config.api_key if config.tool_type == "wordpress" else None,
        wp_application_password=(
            config.api_secret if config.tool_type == "wordpress" else None
        ),
        config=config.custom_config.copy() if config.custom_config else {},
        last_discovery=utc_now(),
        discovery_method=provider_name,
    )
