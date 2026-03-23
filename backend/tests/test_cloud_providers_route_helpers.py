import logging
from types import SimpleNamespace

from backend.app.routes.core.cloud_providers_core.helpers import (
    build_provider_response,
    create_provider_instance,
    get_provider_settings,
    parse_action_required,
    sync_enabled_providers,
)


LOGGER = logging.getLogger(__name__)


def test_get_provider_settings_resets_non_list_config():
    settings_store = SimpleNamespace(get=lambda key, default=None: {"bad": "shape"})

    providers = get_provider_settings(settings_store, LOGGER)

    assert providers == []


def test_build_provider_response_uses_provider_metadata():
    provider = SimpleNamespace(
        is_configured=lambda: True,
        get_provider_name=lambda: "Cloud Demo",
        get_provider_description=lambda: "Demo provider",
    )

    response = build_provider_response(
        provider_id="demo",
        provider_type="generic_http",
        enabled=True,
        config={"api_url": "https://example.com"},
        provider=provider,
    )

    assert response["configured"] is True
    assert response["name"] == "Cloud Demo"
    assert response["description"] == "Demo provider"


def test_create_provider_instance_builds_generic_http_auth_config(monkeypatch):
    class _Provider:
        def __init__(self, **kwargs):
            self.provider_id = kwargs["provider_id"]
            self.auth_config = kwargs["auth_config"]

    monkeypatch.setattr(
        "backend.app.routes.core.cloud_providers_core.helpers.GenericHttpProvider",
        _Provider,
    )

    provider = create_provider_instance(
        "demo",
        "generic_http",
        {
            "name": "Demo Provider",
            "api_url": "https://example.com",
            "auth_type": "api_key",
            "api_key": "secret",
        },
        LOGGER,
    )

    assert provider is not None
    assert provider.provider_id == "demo"
    assert provider.auth_config["auth_type"] == "api_key"
    assert provider.auth_config["api_key"] == "secret"


def test_sync_enabled_providers_registers_only_missing_enabled_providers(monkeypatch):
    class _Provider:
        def __init__(self, **kwargs):
            self.provider_id = kwargs["provider_id"]

    monkeypatch.setattr(
        "backend.app.routes.core.cloud_providers_core.helpers.GenericHttpProvider",
        _Provider,
    )

    registered = []
    manager = SimpleNamespace(
        providers={"already": object()},
        register_provider=lambda provider: registered.append(provider.provider_id),
    )
    settings_store = SimpleNamespace(
        get=lambda key, default=None: [
            {
                "provider_id": "already",
                "provider_type": "generic_http",
                "enabled": True,
                "config": {"api_url": "https://example.com", "auth": {"auth_type": "bearer", "token": "x"}},
            },
            {
                "provider_id": "new-provider",
                "provider_type": "generic_http",
                "enabled": True,
                "config": {"api_url": "https://example.com", "auth": {"auth_type": "bearer", "token": "x"}},
            },
            {
                "provider_id": "disabled-provider",
                "provider_type": "generic_http",
                "enabled": False,
                "config": {"api_url": "https://example.com"},
            },
        ]
    )

    sync_enabled_providers(
        manager=manager,
        settings_store=settings_store,
        logger=LOGGER,
    )

    assert registered == ["new-provider"]


def test_parse_action_required_converts_actions_to_schema():
    action_required = parse_action_required(
        {
            "state": "ACTION_REQUIRED",
            "reason": "ENTITLEMENT_REQUIRED",
            "retry_after_sec": 5,
            "actions": [
                {
                    "type": "BROWSER_AUTH",
                    "label": "Login / Purchase",
                    "rel": "purchase",
                    "url": "https://example.com/login",
                }
            ],
        }
    )

    assert action_required is not None
    assert action_required.reason == "ENTITLEMENT_REQUIRED"
    assert action_required.actions[0].url == "https://example.com/login"
