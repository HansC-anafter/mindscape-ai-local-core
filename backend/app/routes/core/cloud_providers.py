"""Cloud provider route compatibility facade."""

from .cloud_providers_core import (
    ProviderAction,
    ProviderActionRequired,
    ProviderConfig,
    ProviderResponse,
    TestConnectionResponse,
    _get_packs_catalog,
    build_provider_response,
    create_provider_instance,
    get_cloud_manager,
    get_provider_settings,
    get_settings_store,
    parse_action_required,
    sync_enabled_providers,
)
from .cloud_providers_core.actions_routes import (
    get_provider_actions,
    install_default_packs,
    list_provider_packs,
    test_provider_connection,
)
from .cloud_providers_core.provider_routes import (
    create_provider,
    delete_provider,
    list_providers,
    update_provider,
)
from .cloud_providers_core.router import router
from .cloud_providers_core.state import logger

__all__ = [
    "ProviderAction",
    "ProviderActionRequired",
    "ProviderConfig",
    "ProviderResponse",
    "TestConnectionResponse",
    "_get_packs_catalog",
    "build_provider_response",
    "create_provider",
    "create_provider_instance",
    "delete_provider",
    "get_cloud_manager",
    "get_provider_actions",
    "get_provider_settings",
    "get_settings_store",
    "install_default_packs",
    "list_provider_packs",
    "list_providers",
    "logger",
    "parse_action_required",
    "router",
    "sync_enabled_providers",
    "test_provider_connection",
    "update_provider",
]
