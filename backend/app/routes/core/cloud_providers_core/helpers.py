"""Helper functions for cloud provider routes."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.app.routes.core.cloud_providers_core.schemas import (
    ProviderAction,
    ProviderActionRequired,
)
from backend.app.services.cloud_providers.generic_http import GenericHttpProvider


def get_provider_settings(settings_store, logger: logging.Logger) -> list[dict[str, Any]]:
    """Return the cloud provider settings as a normalized list."""
    providers_config = settings_store.get("cloud_providers", default=[])
    if not isinstance(providers_config, list):
        logger.warning(
            "cloud_providers setting is not a list: %s, resetting to empty list",
            type(providers_config),
        )
        return []
    return providers_config


def build_provider_response(
    *,
    provider_id: str,
    provider_type: str,
    enabled: bool,
    config: Dict[str, Any],
    provider,
) -> dict[str, Any]:
    """Build the response payload for one provider row."""
    if provider:
        return {
            "provider_id": provider_id,
            "provider_type": provider_type,
            "enabled": enabled,
            "configured": provider.is_configured(),
            "name": provider.get_provider_name(),
            "description": provider.get_provider_description(),
            "config": config,
        }
    return {
        "provider_id": provider_id,
        "provider_type": provider_type,
        "enabled": enabled,
        "configured": False,
        "name": provider_id,
        "description": f"{provider_type} provider",
        "config": config,
    }


def _build_auth_config(config: Dict[str, Any]) -> dict[str, Any]:
    """Build auth_config for GenericHttpProvider from flat or nested config."""
    auth_config = config.get("auth", {})
    if auth_config:
        return auth_config

    auth_type = config.get("auth_type", "bearer")
    auth_config = {"auth_type": auth_type}
    if auth_type == "bearer":
        auth_config["token"] = config.get("token")
    elif auth_type == "api_key":
        auth_config["api_key"] = config.get("api_key")
    elif auth_type == "oauth":
        auth_config["client_id"] = config.get("client_id")
        auth_config["client_secret"] = config.get("client_secret")
    return auth_config


def create_provider_instance(
    provider_id: str,
    provider_type: str,
    config: Dict[str, Any],
    logger: logging.Logger,
):
    """Create a provider instance from configuration."""
    try:
        if provider_type == "official":
            logger.warning(
                "Provider type 'official' is deprecated. Converting '%s' to generic_http configuration.",
                provider_id,
            )
            return GenericHttpProvider(
                provider_id=provider_id,
                provider_name=config.get("name", "Mindscape AI Cloud"),
                api_url=config.get("api_url"),
                auth_config={
                    "auth_type": "api_key",
                    "api_key": config.get("license_key"),
                },
                api_path_template=config.get(
                    "api_path_template",
                    "/api/v1/playbooks/{capability_code}/{playbook_code}",
                ),
                pack_download_path=config.get("pack_download_path"),
            )
        if provider_type == "generic_http":
            return GenericHttpProvider(
                provider_id=provider_id,
                provider_name=config.get("name", provider_id),
                api_url=config.get("api_url"),
                auth_config=_build_auth_config(config),
                api_path_template=config.get(
                    "api_path_template",
                    "/api/v1/playbooks/{capability_code}/{playbook_code}",
                ),
                pack_download_path=config.get("pack_download_path"),
            )

        logger.warning(
            "Provider type '%s' not supported for instantiation",
            provider_type,
        )
        return None
    except Exception as exc:
        logger.error("Failed to create provider instance: %s", exc, exc_info=True)
        return None


def sync_enabled_providers(
    *,
    manager,
    settings_store,
    logger: logging.Logger,
    create_provider_instance_fn=create_provider_instance,
) -> None:
    """Load enabled providers from settings into the shared manager."""
    providers_config = get_provider_settings(settings_store, logger)
    registered_ids = set(manager.providers.keys())
    for provider_config in providers_config:
        if not isinstance(provider_config, dict):
            continue
        provider_id = provider_config.get("provider_id")
        provider_type = provider_config.get("provider_type")
        enabled = provider_config.get("enabled", False)
        config = provider_config.get("config", {})
        if not provider_id or not enabled or provider_id in registered_ids:
            continue
        try:
            provider_instance = create_provider_instance_fn(
                provider_id,
                provider_type,
                config,
                logger,
            )
            if provider_instance:
                manager.register_provider(provider_instance)
                logger.info("Loaded provider %s from settings", provider_id)
        except Exception as exc:
            logger.warning(
                "Failed to load provider %s: %s",
                provider_id,
                exc,
                exc_info=True,
            )


def parse_action_required(data: Dict[str, Any]) -> Optional[ProviderActionRequired]:
    """Parse action-required payload into the route contract model."""
    if not isinstance(data, dict) or data.get("state") != "ACTION_REQUIRED":
        return None

    actions = []
    for action_data in data.get("actions", []):
        if not isinstance(action_data, dict):
            continue
        actions.append(
            ProviderAction(
                type=action_data.get("type", "BROWSER_AUTH"),
                label=action_data.get("label", "Action"),
                rel=action_data.get("rel", "purchase"),
                url=action_data.get("url", ""),
                expires_at=action_data.get("expires_at"),
            )
        )

    return ProviderActionRequired(
        state=data.get("state", "ACTION_REQUIRED"),
        reason=data.get("reason", "UNKNOWN"),
        actions=actions,
        retry_after_sec=data.get("retry_after_sec"),
    )
