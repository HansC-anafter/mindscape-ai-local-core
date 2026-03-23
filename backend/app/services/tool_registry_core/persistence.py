"""Persistence helpers for ToolRegistryService."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from sqlalchemy import text

from backend.app.models.tool_registry import RegisteredTool, ToolConnectionModel


ConnectionKey = Tuple[str, str]


def _coerce_datetime(
    value: Optional[Any],
    *,
    from_isoformat: Callable[[Any], datetime],
) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return from_isoformat(value)


def load_registry_from_database(
    *,
    factory,
    db_role: str,
    deserialize_json: Callable[[Any, Any], Any],
    from_isoformat: Callable[[Any], datetime],
    tools_by_id: Dict[str, RegisteredTool],
    connections_by_key: Dict[ConnectionKey, ToolConnectionModel],
    utc_now: Callable[[], datetime],
    logger: logging.Logger,
) -> None:
    """Load tools and connections from PostgreSQL into in-memory caches."""
    with factory.get_connection(role=db_role) as conn:
        rows = conn.execute(text("SELECT * FROM tool_registry")).fetchall()
        for row in rows:
            try:
                tool_data = {
                    "tool_id": row.tool_id,
                    "site_id": row.site_id,
                    "provider": row.provider,
                    "display_name": row.display_name,
                    "origin_capability_id": row.origin_capability_id,
                    "category": row.category,
                    "description": row.description,
                    "endpoint": row.endpoint,
                    "methods": deserialize_json(row.methods, []),
                    "danger_level": row.danger_level,
                    "input_schema": deserialize_json(row.input_schema, {}),
                    "enabled": bool(row.enabled) if row.enabled is not None else True,
                    "read_only": (
                        bool(row.read_only) if row.read_only is not None else False
                    ),
                    "allowed_agent_roles": deserialize_json(
                        row.allowed_agent_roles, []
                    ),
                    "side_effect_level": row.side_effect_level,
                    "capability_code": row.capability_code or "",
                    "risk_class": row.risk_class or "readonly",
                    "created_at": _coerce_datetime(
                        row.created_at,
                        from_isoformat=from_isoformat,
                    )
                    or utc_now(),
                    "updated_at": _coerce_datetime(
                        row.updated_at,
                        from_isoformat=from_isoformat,
                    )
                    or utc_now(),
                    "scope": row.scope or "profile",
                    "tenant_id": row.tenant_id,
                    "owner_profile_id": row.owner_profile_id,
                }
                tools_by_id[row.tool_id] = RegisteredTool(**tool_data)
            except Exception as exc:
                logger.warning("Error loading tool %s: %s", row.tool_id, exc)

    with factory.get_connection(role=db_role) as conn:
        rows = conn.execute(text("SELECT * FROM tool_connections")).fetchall()
        for row in rows:
            try:
                connection_data = {
                    "id": row.id,
                    "profile_id": row.profile_id,
                    "tool_type": row.tool_type,
                    "connection_type": row.connection_type,
                    "name": row.name,
                    "description": row.description,
                    "icon": row.icon,
                    "api_key": row.api_key,
                    "api_secret": row.api_secret,
                    "oauth_token": row.oauth_token,
                    "oauth_refresh_token": row.oauth_refresh_token,
                    "base_url": row.base_url,
                    "wp_url": getattr(row, "wp_url", None),
                    "wp_username": getattr(row, "wp_username", None),
                    "wp_application_password": getattr(
                        row, "wp_application_password", None
                    ),
                    "remote_cluster_url": row.remote_cluster_url,
                    "remote_connection_id": row.remote_connection_id,
                    "config": deserialize_json(row.config, {}),
                    "associated_roles": deserialize_json(row.associated_roles, []),
                    "enabled": bool(row.enabled) if row.enabled is not None else True,
                    "is_active": (
                        bool(row.is_active) if row.is_active is not None else True
                    ),
                    "is_validated": (
                        bool(row.is_validated) if row.is_validated is not None else False
                    ),
                    "last_validated_at": _coerce_datetime(
                        row.last_validated_at,
                        from_isoformat=from_isoformat,
                    ),
                    "validation_error": row.validation_error,
                    "usage_count": row.usage_count or 0,
                    "last_used_at": _coerce_datetime(
                        row.last_used_at,
                        from_isoformat=from_isoformat,
                    ),
                    "last_discovery": _coerce_datetime(
                        getattr(row, "last_discovery", None),
                        from_isoformat=from_isoformat,
                    ),
                    "discovery_method": getattr(row, "discovery_method", None),
                    "x_platform": deserialize_json(
                        getattr(row, "x_platform", None),
                        None,
                    ),
                    "created_at": _coerce_datetime(
                        row.created_at,
                        from_isoformat=from_isoformat,
                    )
                    or utc_now(),
                    "updated_at": _coerce_datetime(
                        row.updated_at,
                        from_isoformat=from_isoformat,
                    )
                    or utc_now(),
                }
                connection = ToolConnectionModel(**connection_data)
                connections_by_key[(row.profile_id, row.id)] = connection
            except Exception as exc:
                logger.warning("Error loading connection %s: %s", row.id, exc)


def load_registry_from_json(
    *,
    registry_file: Path,
    connections_file: Path,
    tools_by_id: Dict[str, RegisteredTool],
    connections_by_key: Dict[ConnectionKey, ToolConnectionModel],
    logger: logging.Logger,
) -> None:
    """Load tool registry fallback data from JSON files."""
    tools_by_id.clear()
    connections_by_key.clear()

    if registry_file.exists():
        try:
            with open(registry_file, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            tools_by_id.update(
                {
                    tool_id: RegisteredTool(**tool_data)
                    for tool_id, tool_data in data.items()
                }
            )
        except Exception as exc:
            logger.error("Error loading tool registry from JSON: %s", exc)

    if not connections_file.exists():
        return

    try:
        with open(connections_file, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        for key, connection_data in data.items():
            try:
                connection = ToolConnectionModel(**connection_data)
                profile_id = (
                    connection.profile_id
                    if hasattr(connection, "profile_id") and connection.profile_id
                    else "default-user"
                )
                connections_by_key[(profile_id, connection.id)] = connection
            except Exception as exc:
                logger.warning("Error loading connection %s: %s", key, exc)
    except Exception as exc:
        logger.error("Error loading connections from JSON: %s", exc)


def save_registry_to_database(
    *,
    transaction: Callable[[], Any],
    serialize_json: Callable[[Any], Any],
    tools_by_id: Dict[str, RegisteredTool],
    connections_by_key: Dict[ConnectionKey, ToolConnectionModel],
) -> None:
    """Persist tools and connections to PostgreSQL."""
    with transaction() as conn:
        for _, tool in tools_by_id.items():
            conn.execute(
                text(
                    """
                    INSERT INTO tool_registry (
                        tool_id, site_id, provider, display_name, origin_capability_id,
                        category, description, endpoint, methods, danger_level,
                        input_schema, enabled, read_only, allowed_agent_roles,
                        side_effect_level, scope, tenant_id, owner_profile_id,
                        capability_code, risk_class, created_at, updated_at
                    ) VALUES (
                        :tool_id, :site_id, :provider, :display_name, :origin_capability_id,
                        :category, :description, :endpoint, :methods, :danger_level,
                        :input_schema, :enabled, :read_only, :allowed_agent_roles,
                        :side_effect_level, :scope, :tenant_id, :owner_profile_id,
                        :capability_code, :risk_class, :created_at, :updated_at
                    )
                    ON CONFLICT (tool_id) DO UPDATE SET
                        site_id = EXCLUDED.site_id,
                        provider = EXCLUDED.provider,
                        display_name = EXCLUDED.display_name,
                        origin_capability_id = EXCLUDED.origin_capability_id,
                        category = EXCLUDED.category,
                        description = EXCLUDED.description,
                        endpoint = EXCLUDED.endpoint,
                        methods = EXCLUDED.methods,
                        danger_level = EXCLUDED.danger_level,
                        input_schema = EXCLUDED.input_schema,
                        enabled = EXCLUDED.enabled,
                        read_only = EXCLUDED.read_only,
                        allowed_agent_roles = EXCLUDED.allowed_agent_roles,
                        side_effect_level = EXCLUDED.side_effect_level,
                        scope = EXCLUDED.scope,
                        tenant_id = EXCLUDED.tenant_id,
                        owner_profile_id = EXCLUDED.owner_profile_id,
                        capability_code = EXCLUDED.capability_code,
                        risk_class = EXCLUDED.risk_class,
                        created_at = EXCLUDED.created_at,
                        updated_at = EXCLUDED.updated_at
                """
                ),
                {
                    "tool_id": tool.tool_id,
                    "site_id": tool.site_id,
                    "provider": tool.provider,
                    "display_name": tool.display_name,
                    "origin_capability_id": tool.origin_capability_id,
                    "category": tool.category,
                    "description": tool.description,
                    "endpoint": tool.endpoint,
                    "methods": serialize_json(tool.methods),
                    "danger_level": tool.danger_level,
                    "input_schema": serialize_json(tool.input_schema.model_dump()),
                    "enabled": tool.enabled,
                    "read_only": tool.read_only,
                    "allowed_agent_roles": serialize_json(tool.allowed_agent_roles),
                    "side_effect_level": tool.side_effect_level,
                    "scope": tool.scope or "profile",
                    "tenant_id": tool.tenant_id,
                    "owner_profile_id": tool.owner_profile_id,
                    "capability_code": tool.capability_code,
                    "risk_class": tool.risk_class,
                    "created_at": tool.created_at,
                    "updated_at": tool.updated_at,
                },
            )

        for (_, _), connection in connections_by_key.items():
            conn.execute(
                text(
                    """
                    INSERT INTO tool_connections (
                        id, profile_id, tool_type, connection_type, name, description, icon,
                        api_key, api_secret, oauth_token, oauth_refresh_token, base_url,
                        wp_url, wp_username, wp_application_password,
                        remote_cluster_url, remote_connection_id, config, associated_roles,
                        enabled, is_active, is_validated, last_validated_at, validation_error,
                        usage_count, last_used_at, last_discovery, discovery_method,
                        x_platform, created_at, updated_at
                    ) VALUES (
                        :id, :profile_id, :tool_type, :connection_type, :name, :description, :icon,
                        :api_key, :api_secret, :oauth_token, :oauth_refresh_token, :base_url,
                        :wp_url, :wp_username, :wp_application_password,
                        :remote_cluster_url, :remote_connection_id, :config, :associated_roles,
                        :enabled, :is_active, :is_validated, :last_validated_at, :validation_error,
                        :usage_count, :last_used_at, :last_discovery, :discovery_method,
                        :x_platform, :created_at, :updated_at
                    )
                    ON CONFLICT (profile_id, id) DO UPDATE SET
                        tool_type = EXCLUDED.tool_type,
                        connection_type = EXCLUDED.connection_type,
                        name = EXCLUDED.name,
                        description = EXCLUDED.description,
                        icon = EXCLUDED.icon,
                        api_key = EXCLUDED.api_key,
                        api_secret = EXCLUDED.api_secret,
                        oauth_token = EXCLUDED.oauth_token,
                        oauth_refresh_token = EXCLUDED.oauth_refresh_token,
                        base_url = EXCLUDED.base_url,
                        wp_url = EXCLUDED.wp_url,
                        wp_username = EXCLUDED.wp_username,
                        wp_application_password = EXCLUDED.wp_application_password,
                        remote_cluster_url = EXCLUDED.remote_cluster_url,
                        remote_connection_id = EXCLUDED.remote_connection_id,
                        config = EXCLUDED.config,
                        associated_roles = EXCLUDED.associated_roles,
                        enabled = EXCLUDED.enabled,
                        is_active = EXCLUDED.is_active,
                        is_validated = EXCLUDED.is_validated,
                        last_validated_at = EXCLUDED.last_validated_at,
                        validation_error = EXCLUDED.validation_error,
                        usage_count = EXCLUDED.usage_count,
                        last_used_at = EXCLUDED.last_used_at,
                        last_discovery = EXCLUDED.last_discovery,
                        discovery_method = EXCLUDED.discovery_method,
                        x_platform = EXCLUDED.x_platform,
                        created_at = EXCLUDED.created_at,
                        updated_at = EXCLUDED.updated_at
                """
                ),
                {
                    "id": connection.id,
                    "profile_id": connection.profile_id,
                    "tool_type": connection.tool_type,
                    "connection_type": connection.connection_type,
                    "name": connection.name,
                    "description": connection.description,
                    "icon": connection.icon,
                    "api_key": connection.api_key,
                    "api_secret": connection.api_secret,
                    "oauth_token": connection.oauth_token,
                    "oauth_refresh_token": connection.oauth_refresh_token,
                    "base_url": connection.base_url,
                    "wp_url": connection.wp_url,
                    "wp_username": connection.wp_username,
                    "wp_application_password": connection.wp_application_password,
                    "remote_cluster_url": connection.remote_cluster_url,
                    "remote_connection_id": connection.remote_connection_id,
                    "config": serialize_json(connection.config),
                    "associated_roles": serialize_json(connection.associated_roles),
                    "enabled": connection.enabled,
                    "is_active": connection.is_active,
                    "is_validated": connection.is_validated,
                    "last_validated_at": connection.last_validated_at,
                    "validation_error": connection.validation_error,
                    "usage_count": connection.usage_count,
                    "last_used_at": connection.last_used_at,
                    "last_discovery": connection.last_discovery,
                    "discovery_method": connection.discovery_method,
                    "x_platform": serialize_json(connection.x_platform),
                    "created_at": connection.created_at,
                    "updated_at": connection.updated_at,
                },
            )


def save_registry_to_json(
    *,
    registry_file: Path,
    connections_file: Path,
    tools_by_id: Dict[str, RegisteredTool],
    connections_by_key: Dict[ConnectionKey, ToolConnectionModel],
    logger: logging.Logger,
) -> None:
    """Persist tools and connections to JSON fallback files."""
    try:
        with open(registry_file, "w", encoding="utf-8") as handle:
            json.dump(
                {tool_id: tool.model_dump() for tool_id, tool in tools_by_id.items()},
                handle,
                indent=2,
                ensure_ascii=False,
                default=str,
            )
    except Exception as exc:
        logger.error("Error saving tool registry to JSON: %s", exc)

    try:
        with open(connections_file, "w", encoding="utf-8") as handle:
            payload = {
                f"{profile_id}:{connection_id}": connection.model_dump()
                for (profile_id, connection_id), connection in connections_by_key.items()
            }
            json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
    except Exception as exc:
        logger.error("Error saving connections to JSON: %s", exc)
