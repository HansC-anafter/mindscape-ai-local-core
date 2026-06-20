"""Discovery helpers for ToolRegistryService."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Tuple

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


async def discover_tool_capabilities_for_service(
    service: Any,
    *,
    provider_name: str,
    config: ToolConfig,
    connection_id: Optional[str],
    profile_id: str,
    register_dynamic_tool_fn,
    utc_now_fn,
    logger,
) -> Dict[str, Any]:
    """Run discovery through the canonical ToolRegistryService facade state."""
    provider = service._discovery_providers.get(provider_name)
    if not provider:
        available = list(service._discovery_providers.keys())
        raise ValueError(
            f"Unknown discovery provider: '{provider_name}'. "
            f"Available providers: {available}"
        )

    logger.info("Validating config for provider '%s'...", provider_name)
    is_valid = await provider.validate(config)
    if not is_valid:
        raise ValueError(f"Invalid configuration for provider '{provider_name}'")

    logger.info("Discovering tools using provider '%s'...", provider_name)
    discovered_tools = await provider.discover(config)

    if not connection_id:
        connection_id = f"{provider_name}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

    tool_ids_to_remove = [
        tool_id
        for tool_id, tool in service._tools.items()
        if tool.site_id == connection_id and tool.provider == provider_name
    ]
    for tool_id in tool_ids_to_remove:
        del service._tools[tool_id]
        try:
            from backend.app.shared.tool_executor import unregister_dynamic_tool

            unregister_dynamic_tool(tool_id)
        except Exception as exc:
            logger.warning("Failed to unregister dynamic tool %s: %s", tool_id, exc)

    if tool_ids_to_remove:
        logger.info(
            "Removed %s old tools for connection %s",
            len(tool_ids_to_remove),
            connection_id,
        )

    registered_tools = []
    for discovered_tool in discovered_tools:
        tool_id = f"{connection_id}.{discovered_tool.tool_id}"
        side_effect_level = service._infer_side_effect_level(
            provider_name=provider_name,
            danger_level=discovered_tool.danger_level,
            tool_id=discovered_tool.tool_id,
            methods=discovered_tool.methods,
        )

        connection_model = service.get_connection(
            connection_id, profile_id=profile_id
        )
        tool_scope = "profile"
        tool_tenant_id = None
        tool_owner_profile_id = profile_id
        if connection_model:
            tool_owner_profile_id = connection_model.profile_id

        registered_tool = build_registered_tool(
            tool_id=tool_id,
            connection_id=connection_id,
            provider_name=provider_name,
            discovered_tool=discovered_tool,
            side_effect_level=side_effect_level,
            tool_scope=tool_scope,
            tool_tenant_id=tool_tenant_id,
            tool_owner_profile_id=tool_owner_profile_id,
        )
        service._tools[tool_id] = registered_tool

        tool_connection = build_dynamic_tool_connection(
            connection_id=connection_id,
            config=config,
            display_name=discovered_tool.display_name,
        )
        register_dynamic_tool_fn(tool_id, tool_connection)
        registered_tools.append(registered_tool.model_dump())

    upsert_discovery_connection(
        service._connections,
        profile_id=profile_id,
        connection_id=connection_id,
        provider_name=provider_name,
        config=config,
        utc_now=utc_now_fn,
    )

    service._save_registry()
    logger.info(
        "Successfully discovered %s tools using provider '%s'",
        len(registered_tools),
        provider_name,
    )

    return {
        "provider": provider_name,
        "connection_id": connection_id,
        "discovered_tools": registered_tools,
        "discovery_metadata": provider.get_discovery_metadata(),
    }


async def discover_wordpress_capabilities_for_service(
    service: Any,
    *,
    connection_id: str,
    wp_url: str,
    wp_username: str,
    wp_password: str,
    logger,
) -> Dict[str, Any]:
    """Legacy WordPress discovery wrapper."""
    from backend.app.services.tools.discovery_provider import ToolConfig

    if "wordpress" not in service._discovery_providers:
        try:
            from backend.app.extensions.console_kit import register_console_kit_tools

            register_console_kit_tools(service)
        except ImportError:
            logger.warning(
                "WordPress provider not available (external extension not installed)"
            )

    config = ToolConfig(
        tool_type="wordpress",
        connection_type="http_api",
        base_url=wp_url,
        api_key=wp_username,
        api_secret=wp_password,
    )

    return await service.discover_tool_capabilities(
        provider_name="wordpress",
        config=config,
        connection_id=connection_id,
    )
