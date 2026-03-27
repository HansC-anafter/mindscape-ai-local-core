import logging
from pathlib import Path
from types import SimpleNamespace

from backend.app.models.tool_registry import (
    RegisteredTool,
    ToolConnectionModel,
    ToolInputSchema,
)
from backend.app.services.tool_registry_core.connections import (
    delete_connection,
    export_as_templates,
)
from backend.app.services.tool_registry_core.discovery import (
    build_registered_tool,
    upsert_discovery_connection,
)
from backend.app.services.tool_registry_core.persistence import (
    load_registry_from_json,
    save_registry_to_json,
)
from backend.app.services.tool_registry_core.tools import (
    get_tools,
    infer_side_effect_level,
)


LOGGER = logging.getLogger(__name__)
FIXTURE_API_CREDENTIAL = "fixture-api-credential-value"


def _make_tool(
    *,
    tool_id: str,
    scope: str = "system",
    tenant_id: str | None = None,
    owner_profile_id: str | None = None,
    enabled: bool = True,
    category: str = "content",
):
    return RegisteredTool(
        tool_id=tool_id,
        site_id="site-1",
        provider="wordpress",
        display_name=tool_id,
        origin_capability_id="wp.posts",
        category=category,
        description="Tool description",
        endpoint="/tools/demo",
        methods=["GET"],
        enabled=enabled,
        scope=scope,
        tenant_id=tenant_id,
        owner_profile_id=owner_profile_id,
        input_schema=ToolInputSchema(),
    )


def _make_connection(
    *,
    connection_id: str,
    profile_id: str = "profile-1",
    tool_type: str = "wordpress",
    usage_count: int = 0,
    name: str = "Demo Connection",
):
    return ToolConnectionModel(
        id=connection_id,
        profile_id=profile_id,
        name=name,
        tool_type=tool_type,
        connection_type="local",
        base_url="https://example.com",
        api_key="user",
        api_secret=FIXTURE_API_CREDENTIAL,
        usage_count=usage_count,
        config={"required_permissions": ["write:posts"]},
        associated_roles=["operator"],
    )


def test_get_tools_filters_enabled_scope_and_profile_access():
    tools_by_id = {
        "system": _make_tool(tool_id="system", scope="system"),
        "tenant": _make_tool(
            tool_id="tenant",
            scope="tenant",
            tenant_id="tenant-1",
        ),
        "profile": _make_tool(
            tool_id="profile",
            scope="profile",
            owner_profile_id="profile-1",
        ),
        "disabled": _make_tool(
            tool_id="disabled",
            scope="profile",
            owner_profile_id="profile-1",
            enabled=False,
        ),
    }

    result = get_tools(
        tools_by_id,
        enabled_only=True,
        profile_id="profile-1",
    )

    assert [tool.tool_id for tool in result] == ["system", "profile"]


def test_delete_connection_unregisters_attached_tools():
    connections_by_key = {("profile-1", "conn-1"): _make_connection(connection_id="conn-1")}
    tools_by_id = {
        "tool-1": _make_tool(tool_id="tool-1"),
        "tool-2": _make_tool(tool_id="tool-2"),
    }
    tools_by_id["tool-1"].site_id = "conn-1"
    tools_by_id["tool-2"].site_id = "other"
    unregistered = []
    saved = []

    deleted = delete_connection(
        connections_by_key,
        tools_by_id,
        connection_id="conn-1",
        profile_id="profile-1",
        save_registry=lambda: saved.append(True),
        unregister_dynamic_tool_fn=unregistered.append,
    )

    assert deleted is True
    assert ("profile-1", "conn-1") not in connections_by_key
    assert "tool-1" not in tools_by_id
    assert unregistered == ["tool-1"]
    assert saved == [True]


def test_export_as_templates_redacts_sensitive_values():
    connection = _make_connection(connection_id="conn-1")

    templates = export_as_templates(
        get_connections_by_profile_fn=lambda profile_id, active_only=True: [connection],
        profile_id="profile-1",
    )

    template = templates[0]
    assert template["tool_type"] == "wordpress"
    assert template["config_schema"]["fields"]["api_key"]["sensitive"] is True
    assert template["config_schema"]["fields"]["base_url"]["example"] == "https://example.com"
    assert FIXTURE_API_CREDENTIAL not in str(template)


def test_build_registered_tool_maps_capability_code_and_risk_class():
    discovered_tool = SimpleNamespace(
        tool_id="wp.posts.create",
        display_name="Create Post",
        category="content",
        description="Create a post",
        endpoint="/posts",
        methods=["POST"],
        danger_level="medium",
        input_schema=ToolInputSchema(),
    )

    tool = build_registered_tool(
        tool_id="wp.site-1.create_post",
        connection_id="site-1",
        provider_name="wordpress",
        discovered_tool=discovered_tool,
        side_effect_level="external_write",
        tool_scope="profile",
        tool_tenant_id=None,
        tool_owner_profile_id="profile-1",
    )

    assert tool.capability_code == "wp"
    assert tool.risk_class == "external_write"
    assert tool.owner_profile_id == "profile-1"


def test_upsert_discovery_connection_updates_existing_config():
    connection = _make_connection(connection_id="conn-1")
    connections_by_key = {("profile-1", "conn-1"): connection}
    config = SimpleNamespace(
        tool_type="wordpress",
        connection_type="http_api",
        base_url="https://example.com",
        api_key="user",
        api_secret=FIXTURE_API_CREDENTIAL,
        custom_config={"workspace_id": "ws-1"},
    )

    upsert_discovery_connection(
        connections_by_key,
        profile_id="profile-1",
        connection_id="conn-1",
        provider_name="wordpress",
        config=config,
        utc_now=lambda: connection.updated_at,
    )

    assert connections_by_key[("profile-1", "conn-1")].config["workspace_id"] == "ws-1"


def test_json_fallback_round_trip(tmp_path):
    registry_file = tmp_path / "tool_registry.json"
    connections_file = tmp_path / "tool_connections.json"
    tools_by_id = {"tool-1": _make_tool(tool_id="tool-1")}
    connections_by_key = {("profile-1", "conn-1"): _make_connection(connection_id="conn-1")}

    save_registry_to_json(
        registry_file=registry_file,
        connections_file=connections_file,
        tools_by_id=tools_by_id,
        connections_by_key=connections_by_key,
        logger=LOGGER,
    )

    loaded_tools = {}
    loaded_connections = {}
    load_registry_from_json(
        registry_file=registry_file,
        connections_file=connections_file,
        tools_by_id=loaded_tools,
        connections_by_key=loaded_connections,
        logger=LOGGER,
    )

    assert "tool-1" in loaded_tools
    assert ("profile-1", "conn-1") in loaded_connections
    assert loaded_connections[("profile-1", "conn-1")].name == "Demo Connection"


def test_infer_side_effect_level_classifies_external_write():
    assert infer_side_effect_level("wordpress", "medium", "wp.posts.create", ["POST"]) == "external_write"
    assert infer_side_effect_level("generic_http", "low", "http.read", ["GET"]) == "readonly"
