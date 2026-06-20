"""Default provider registration helpers for ToolRegistryService."""

from __future__ import annotations

import importlib
import logging
from typing import Callable

from backend.app.services.tools.discovery_provider import (
    GenericHTTPToolProvider,
    ToolDiscoveryProvider,
)


ProviderRegistrar = Callable[[ToolDiscoveryProvider], None]


_OPTIONAL_PROVIDER_SPECS = [
    (
        "backend.app.services.tools.providers.local_filesystem_provider",
        "LocalFilesystemDiscoveryProvider",
        "Local filesystem",
    ),
    (
        "backend.app.services.tools.providers.obsidian_provider",
        "ObsidianDiscoveryProvider",
        "Obsidian",
    ),
    (
        "backend.app.services.tools.providers.notion_provider",
        "NotionDiscoveryProvider",
        "Notion",
    ),
    (
        "backend.app.services.tools.providers.google_drive_provider",
        "GoogleDriveDiscoveryProvider",
        "Google Drive",
    ),
]

_SOCIAL_PROVIDER_SPECS = [
    ("slack_provider", "SlackDiscoveryProvider", "Slack"),
    ("airtable_provider", "AirtableDiscoveryProvider", "Airtable"),
    ("google_sheets_provider", "GoogleSheetsDiscoveryProvider", "Google Sheets"),
    ("github_provider", "GitHubDiscoveryProvider", "GitHub"),
    ("twitter_provider", "TwitterDiscoveryProvider", "Twitter"),
    ("facebook_provider", "FacebookDiscoveryProvider", "Facebook"),
    ("instagram_provider", "InstagramDiscoveryProvider", "Instagram"),
    ("linkedin_provider", "LinkedInDiscoveryProvider", "LinkedIn"),
    ("youtube_provider", "YouTubeDiscoveryProvider", "YouTube"),
    ("line_provider", "LineDiscoveryProvider", "Line"),
]


def register_default_providers(
    register_provider: ProviderRegistrar,
    *,
    logger: logging.Logger,
) -> None:
    """Register built-in discovery providers through the facade callback."""
    register_provider(GenericHTTPToolProvider())

    for module_name, class_name, display_name in _OPTIONAL_PROVIDER_SPECS:
        _register_optional_provider(
            module_name=module_name,
            class_name=class_name,
            display_name=display_name,
            register_provider=register_provider,
            logger=logger,
        )

    for module_leaf, class_name, display_name in _SOCIAL_PROVIDER_SPECS:
        _register_optional_provider(
            module_name=f"backend.app.services.tools.providers.{module_leaf}",
            class_name=class_name,
            display_name=display_name,
            register_provider=register_provider,
            logger=logger,
        )


def _register_optional_provider(
    *,
    module_name: str,
    class_name: str,
    display_name: str,
    register_provider: ProviderRegistrar,
    logger: logging.Logger,
) -> None:
    try:
        module = importlib.import_module(module_name)
        provider_cls = getattr(module, class_name)
        register_provider(provider_cls())
    except ImportError:
        logger.warning("%s provider not available", display_name)
