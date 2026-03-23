"""Connection helpers for ToolRegistryService."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.app.models.tool_registry import RegisteredTool, ToolConnectionModel


ConnectionKey = Tuple[str, str]


def get_connections(
    connections_by_key: Dict[ConnectionKey, ToolConnectionModel],
    profile_id: Optional[str] = None,
) -> List[ToolConnectionModel]:
    """Return all connections, optionally filtered by profile."""
    if profile_id:
        return [
            connection
            for (current_profile_id, _), connection in connections_by_key.items()
            if current_profile_id == profile_id
        ]
    return list(connections_by_key.values())


def get_connection(
    connections_by_key: Dict[ConnectionKey, ToolConnectionModel],
    *,
    connection_id: Optional[str],
    profile_id: Optional[str],
    get_db_connection: Callable[[], Any],
) -> Any:
    """Return a single connection or the underlying DB connection accessor."""
    if connection_id is None:
        return get_db_connection()

    if profile_id:
        return connections_by_key.get((profile_id, connection_id))

    for (_, current_connection_id), connection in connections_by_key.items():
        if current_connection_id == connection_id:
            return connection
    return None


def create_connection(
    connections_by_key: Dict[ConnectionKey, ToolConnectionModel],
    *,
    connection: ToolConnectionModel,
    save_registry: Callable[[], None],
    utc_now: Callable[[], Any],
) -> ToolConnectionModel:
    """Store a connection and persist the registry."""
    connection.updated_at = utc_now()
    if not connection.created_at:
        connection.created_at = utc_now()

    connections_by_key[(connection.profile_id, connection.id)] = connection
    save_registry()
    return connection


def create_connection_legacy(
    *,
    create_connection_fn: Callable[[ToolConnectionModel], ToolConnectionModel],
    connection_id: str,
    name: str,
    wp_url: str,
    wp_username: str,
    wp_application_password: str,
    profile_id: str = "default-user",
) -> ToolConnectionModel:
    """Create a WordPress connection using the legacy argument shape."""
    connection = ToolConnectionModel(
        id=connection_id,
        profile_id=profile_id,
        name=name,
        tool_type="wordpress",
        connection_type="local",
        wp_url=wp_url,
        wp_username=wp_username,
        wp_application_password=wp_application_password,
        base_url=wp_url,
        api_key=wp_username,
        api_secret=wp_application_password,
    )
    return create_connection_fn(connection)


def delete_connection(
    connections_by_key: Dict[ConnectionKey, ToolConnectionModel],
    tools_by_id: Dict[str, RegisteredTool],
    *,
    connection_id: str,
    profile_id: Optional[str],
    save_registry: Callable[[], None],
    unregister_dynamic_tool_fn: Callable[[str], None],
) -> bool:
    """Delete a connection and unregister all tools attached to it."""
    deleted = False

    if profile_id:
        keys_to_delete = [(profile_id, connection_id)]
    else:
        keys_to_delete = [
            key
            for key, connection in connections_by_key.items()
            if connection.id == connection_id
        ]

    for key in keys_to_delete:
        if key not in connections_by_key:
            continue

        tool_ids_to_remove = [
            tool_id
            for tool_id, tool in tools_by_id.items()
            if tool.site_id == connection_id
        ]
        for tool_id in tool_ids_to_remove:
            del tools_by_id[tool_id]
            unregister_dynamic_tool_fn(tool_id)

        del connections_by_key[key]
        deleted = True

    if deleted:
        save_registry()

    return deleted


def get_connections_by_profile(
    connections_by_key: Dict[ConnectionKey, ToolConnectionModel],
    *,
    profile_id: str,
    active_only: bool = True,
) -> List[ToolConnectionModel]:
    """Return connections for a profile sorted by usage and name."""
    connections = [
        connection
        for (current_profile_id, _), connection in connections_by_key.items()
        if current_profile_id == profile_id
    ]
    if active_only:
        connections = [connection for connection in connections if connection.is_active]
    connections.sort(key=lambda connection: (-connection.usage_count, connection.name))
    return connections


def get_connections_by_tool_type(
    connections_by_key: Dict[ConnectionKey, ToolConnectionModel],
    *,
    profile_id: str,
    tool_type: str,
) -> List[ToolConnectionModel]:
    """Return active connections for a profile and tool type."""
    connections = [
        connection
        for (current_profile_id, _), connection in connections_by_key.items()
        if (
            current_profile_id == profile_id
            and connection.tool_type == tool_type
            and connection.is_active
        )
    ]
    connections.sort(key=lambda connection: (-connection.usage_count, connection.name))
    return connections


def get_connections_by_role(
    *,
    get_connections_by_profile_fn: Callable[..., List[ToolConnectionModel]],
    profile_id: str,
    role_id: str,
) -> List[ToolConnectionModel]:
    """Return active connections associated with an agent role."""
    connections = get_connections_by_profile_fn(profile_id, active_only=True)
    return [connection for connection in connections if role_id in connection.associated_roles]


def update_connection(
    connections_by_key: Dict[ConnectionKey, ToolConnectionModel],
    *,
    connection: ToolConnectionModel,
    save_registry: Callable[[], None],
    utc_now: Callable[[], Any],
) -> ToolConnectionModel:
    """Update a connection entry and persist the registry."""
    connection.updated_at = utc_now()
    connections_by_key[(connection.profile_id, connection.id)] = connection
    save_registry()
    return connection


def record_connection_usage(
    connections_by_key: Dict[ConnectionKey, ToolConnectionModel],
    *,
    connection_id: str,
    profile_id: str,
    save_registry: Callable[[], None],
    utc_now: Callable[[], Any],
) -> None:
    """Increment usage metadata for a connection."""
    key = (profile_id, connection_id)
    if key not in connections_by_key:
        return

    connection = connections_by_key[key]
    connection.usage_count += 1
    connection.last_used_at = utc_now()
    connection.updated_at = utc_now()
    save_registry()


def update_validation_status(
    connections_by_key: Dict[ConnectionKey, ToolConnectionModel],
    *,
    connection_id: str,
    profile_id: str,
    is_valid: bool,
    error_message: Optional[str],
    save_registry: Callable[[], None],
    utc_now: Callable[[], Any],
) -> None:
    """Persist validation state for a connection."""
    key = (profile_id, connection_id)
    if key not in connections_by_key:
        return

    connection = connections_by_key[key]
    connection.is_validated = is_valid
    connection.last_validated_at = utc_now()
    connection.validation_error = error_message
    connection.updated_at = utc_now()
    save_registry()


def export_as_templates(
    *,
    get_connections_by_profile_fn: Callable[..., List[ToolConnectionModel]],
    profile_id: str,
) -> List[Dict[str, Any]]:
    """Export connection templates without sensitive values."""
    from backend.app.models.tool_connection import ToolConnectionTemplate

    connections = get_connections_by_profile_fn(profile_id, active_only=True)
    templates = []

    for connection in connections:
        config_schema = {"connection_type": connection.connection_type, "fields": {}}

        if connection.connection_type == "local":
            if connection.api_key:
                config_schema["fields"]["api_key"] = {
                    "type": "string",
                    "required": True,
                    "sensitive": True,
                }
            if connection.api_secret:
                config_schema["fields"]["api_secret"] = {
                    "type": "string",
                    "required": True,
                    "sensitive": True,
                }
            if connection.oauth_token:
                config_schema["fields"]["oauth_token"] = {
                    "type": "string",
                    "required": True,
                    "sensitive": True,
                }
            if connection.base_url:
                config_schema["fields"]["base_url"] = {
                    "type": "string",
                    "required": True,
                    "example": connection.base_url,
                }

        template = ToolConnectionTemplate(
            tool_type=connection.tool_type,
            name=connection.name,
            description=connection.description,
            icon=connection.icon,
            config_schema=config_schema,
            required_permissions=connection.config.get("required_permissions", []),
            associated_roles=connection.associated_roles,
        )
        templates.append(template.model_dump())

    return templates
