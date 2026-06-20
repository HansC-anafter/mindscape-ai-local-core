import logging
from datetime import datetime, timezone

import pytest

from backend.app.models.tool_registry import RegisteredTool, ToolInputSchema
from backend.app.services.tool_registry_core.discovery import (
    discover_tool_capabilities_for_service,
    discover_wordpress_capabilities_for_service,
)
from backend.app.services.tool_registry_core.providers import register_default_providers
from backend.app.services.tools.discovery_provider import DiscoveredTool, ToolConfig


LOGGER = logging.getLogger(__name__)
FIXTURE_WP_SECRET = "fixture-password"


class FakeDiscoveryProvider:
    provider_name = "demo"
    supported_connection_types = ["local"]

    async def validate(self, config: ToolConfig) -> bool:
        self.validated_config = config
        return True

    async def discover(self, config: ToolConfig) -> list[DiscoveredTool]:
        self.discovered_config = config
        return [
            DiscoveredTool(
                tool_id="demo.read",
                display_name="Demo Read",
                description="Read demo data",
                category="data",
                endpoint="/demo",
                methods=["GET"],
                input_schema={"type": "object", "properties": {}},
                danger_level="low",
            )
        ]

    def get_discovery_metadata(self) -> dict[str, str]:
        return {"provider": self.provider_name}


class FakeRegistryService:
    def __init__(self):
        self._discovery_providers = {"demo": FakeDiscoveryProvider()}
        self._tools = {
            "conn-1.demo.old": RegisteredTool(
                tool_id="conn-1.demo.old",
                site_id="conn-1",
                provider="demo",
                display_name="Old Demo",
                origin_capability_id="demo.old",
                category="data",
                description="Old demo data",
                endpoint="/old-demo",
                methods=["GET"],
                input_schema=ToolInputSchema(),
            )
        }
        self._connections = {}
        self.save_count = 0

    def _infer_side_effect_level(
        self,
        provider_name: str,
        danger_level: str,
        tool_id: str,
        methods: list[str],
    ) -> str:
        return "readonly"

    def get_connection(self, connection_id: str, profile_id: str | None = None):
        return self._connections.get((profile_id, connection_id))

    def _save_registry(self):
        self.save_count += 1


def test_default_provider_registration_keeps_generic_http_available():
    registered = []

    register_default_providers(registered.append, logger=LOGGER)

    provider_names = [provider.provider_name for provider in registered]
    assert "generic_http" in provider_names


@pytest.mark.asyncio
async def test_discovery_helper_replaces_connection_tools_and_saves(monkeypatch):
    service = FakeRegistryService()
    dynamic_registrations = []
    dynamic_unregistrations = []

    from backend.app.shared import tool_executor

    monkeypatch.setattr(
        tool_executor,
        "unregister_dynamic_tool",
        dynamic_unregistrations.append,
        raising=False,
    )

    result = await discover_tool_capabilities_for_service(
        service,
        provider_name="demo",
        config=ToolConfig(
            tool_type="demo",
            connection_type="local",
            base_url="https://example.test",
        ),
        connection_id="conn-1",
        profile_id="profile-1",
        register_dynamic_tool_fn=lambda tool_id, connection: dynamic_registrations.append(
            (tool_id, connection.id)
        ),
        utc_now_fn=lambda: datetime(2026, 6, 20, tzinfo=timezone.utc),
        logger=LOGGER,
    )

    assert result["provider"] == "demo"
    assert result["connection_id"] == "conn-1"
    assert result["discovery_metadata"] == {"provider": "demo"}
    assert "conn-1.demo.old" not in service._tools
    assert "conn-1.demo.read" in service._tools
    assert dynamic_unregistrations == ["conn-1.demo.old"]
    assert dynamic_registrations == [("conn-1.demo.read", "conn-1")]
    assert ("profile-1", "conn-1") in service._connections
    assert service.save_count == 1


@pytest.mark.asyncio
async def test_wordpress_wrapper_delegates_to_canonical_discovery_path():
    observed = {}

    class WordPressService:
        _discovery_providers = {"wordpress": object()}

        async def discover_tool_capabilities(
            self,
            provider_name: str,
            config: ToolConfig,
            connection_id: str | None = None,
            profile_id: str = "default-user",
        ):
            observed["provider_name"] = provider_name
            observed["config"] = config
            observed["connection_id"] = connection_id
            observed["profile_id"] = profile_id
            return {"ok": True}

    result = await discover_wordpress_capabilities_for_service(
        WordPressService(),
        connection_id="wp-1",
        wp_url="https://wordpress.example.test",
        wp_username="fixture-user",
        wp_password=FIXTURE_WP_SECRET,
        logger=LOGGER,
    )

    assert result == {"ok": True}
    assert observed["provider_name"] == "wordpress"
    assert observed["connection_id"] == "wp-1"
    assert observed["profile_id"] == "default-user"
    assert observed["config"].tool_type == "wordpress"
    assert observed["config"].connection_type == "http_api"
    assert observed["config"].base_url == "https://wordpress.example.test"
