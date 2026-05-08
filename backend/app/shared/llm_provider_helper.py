"""
LLM Provider Helper
Utility functions for getting LLM provider based on user settings
"""

from dataclasses import dataclass
import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ManagedLLMDisabledForRuntime(RuntimeError):
    """Raised when a workspace-bound executor runtime should own generation."""


@dataclass(frozen=True)
class ResolvedLLMSelection:
    """Resolved model/provider choice under runtime-aware governance."""

    model_name: str
    provider_name: Optional[str]
    executor_runtime: Optional[str]
    managed_llm_allowed: bool


def resolve_executor_runtime(
    *,
    workspace: Optional[Any] = None,
    executor_runtime: Optional[str] = None,
) -> Optional[str]:
    """Resolve the active executor runtime from explicit arg or workspace contract."""
    if executor_runtime:
        return executor_runtime
    if workspace is None:
        return None
    return getattr(workspace, "resolved_executor_runtime", None)


def resolve_llm_selection(
    *,
    workspace: Optional[Any] = None,
    executor_runtime: Optional[str] = None,
    model_name: Optional[str] = None,
    provider_name: Optional[str] = None,
    allow_with_executor_runtime: bool = False,
    purpose: str = "general",
) -> ResolvedLLMSelection:
    """
    Resolve model/provider under a runtime-aware governance policy.

    When a workspace is bound to an external executor runtime, managed LLM
    selection is disabled by default so request-paths do not silently fall back
    to server-side providers like Vertex AI.
    """
    from backend.app.services.model_routing_policy_service import (
        ModelRoutingPolicyService,
    )

    chat_route = None
    if model_name is None or provider_name is None:
        chat_route = ModelRoutingPolicyService().resolve_chat_default()

    resolved_model_name = model_name
    if not resolved_model_name and chat_route and chat_route.model_name:
        resolved_model_name = chat_route.model_name
    if not resolved_model_name:
        raise ValueError(
            f"chat_model not configured for purpose '{purpose}'. "
            "Configure chat_model in model-routing-registry."
        )

    resolved_runtime = resolve_executor_runtime(
        workspace=workspace,
        executor_runtime=executor_runtime,
    )
    if resolved_runtime and not allow_with_executor_runtime:
        return ResolvedLLMSelection(
            model_name=resolved_model_name,
            provider_name=None,
            executor_runtime=resolved_runtime,
            managed_llm_allowed=False,
        )

    resolved_provider_name = provider_name
    if not resolved_provider_name and model_name:
        from backend.app.models.model_provider import ModelType as ProviderModelType

        model_route = ModelRoutingPolicyService().resolve_registered_model(
            model_name=resolved_model_name,
            model_type=ProviderModelType.CHAT,
            source=f"resolve_llm_selection.{purpose}",
        )
        resolved_provider_name = model_route.provider
    elif not resolved_provider_name and chat_route:
        resolved_provider_name = chat_route.provider
    if not resolved_provider_name:
        raise ValueError(
            f"Cannot determine LLM provider for model '{resolved_model_name}' "
            f"(purpose='{purpose}'). Configure provider in model-routing-registry."
        )

    return ResolvedLLMSelection(
        model_name=resolved_model_name,
        provider_name=resolved_provider_name,
        executor_runtime=resolved_runtime,
        managed_llm_allowed=True,
    )


def get_provider_name_from_chat_model(
    *,
    workspace: Optional[Any] = None,
    executor_runtime: Optional[str] = None,
    model_name: Optional[str] = None,
    allow_with_executor_runtime: bool = False,
    purpose: str = "general",
) -> Optional[str]:
    """
    Get provider name from system chat_model setting

    Returns:
        Provider name (openai, anthropic, vertex-ai) or None if not configured

    Raises:
        ValueError: If chat_model is not configured or cannot determine provider
    """
    selection = resolve_llm_selection(
        workspace=workspace,
        executor_runtime=executor_runtime,
        model_name=model_name,
        allow_with_executor_runtime=allow_with_executor_runtime,
        purpose=purpose,
    )
    if not selection.managed_llm_allowed:
        raise ManagedLLMDisabledForRuntime(
            f"Managed LLM disabled for purpose '{purpose}' because workspace is "
            f"bound to executor runtime '{selection.executor_runtime}'."
        )
    return selection.provider_name


def get_llm_provider_from_settings(
    llm_manager,
    *,
    workspace: Optional[Any] = None,
    executor_runtime: Optional[str] = None,
    model_name: Optional[str] = None,
    provider_name: Optional[str] = None,
    allow_with_executor_runtime: bool = False,
    purpose: str = "general",
) -> Optional[object]:
    """
    Get LLM provider from user's chat_model setting

    Args:
        llm_manager: LLMProviderManager instance

    Returns:
        LLMProvider instance

    Raises:
        ValueError: If chat_model is not configured or provider is not available
    """
    selection = resolve_llm_selection(
        workspace=workspace,
        executor_runtime=executor_runtime,
        model_name=model_name,
        provider_name=provider_name,
        allow_with_executor_runtime=allow_with_executor_runtime,
        purpose=purpose,
    )
    if not selection.managed_llm_allowed:
        raise ManagedLLMDisabledForRuntime(
            f"Managed LLM disabled for purpose '{purpose}' because workspace is "
            f"bound to executor runtime '{selection.executor_runtime}'."
        )

    provider = llm_manager.get_provider(selection.provider_name)

    if not provider:
        available_providers = llm_manager.get_available_providers()
        resolved_model_name = (
            selection.model_name
            or "unknown"
        )

        # Provide specific error message based on provider type
        if selection.provider_name == "vertex-ai":
            error_msg = (
                f"Selected provider 'vertex-ai' (from chat_model '{resolved_model_name}') is not available. "
                f"Available providers: {', '.join(available_providers) if available_providers else 'none'}. "
                f"Please configure the Service Account JSON and Project ID for 'vertex-ai' in Settings."
            )
        elif selection.provider_name in ["openai", "anthropic"]:
            error_msg = (
                f"Selected provider '{selection.provider_name}' (from chat_model '{resolved_model_name}') is not available. "
                f"Available providers: {', '.join(available_providers) if available_providers else 'none'}. "
                f"Please configure the API key for '{selection.provider_name}' in Settings."
            )
        elif selection.provider_name == "ollama":
            error_msg = (
                f"Selected provider 'ollama' (from chat_model '{resolved_model_name}') is not available. "
                "Please ensure Ollama is running (default: http://localhost:11434) or configure the URL in Settings."
            )
        else:
            error_msg = (
                f"Selected provider '{selection.provider_name}' (from chat_model '{resolved_model_name}') is not available. "
                f"Available providers: {', '.join(available_providers) if available_providers else 'none'}. "
                f"Please configure the credentials for '{selection.provider_name}' in Settings."
            )
        raise ValueError(error_msg)

    logger.info(
        "Using LLM provider '%s' (from chat_model '%s') for purpose '%s'",
        selection.provider_name,
        selection.model_name,
        purpose,
    )
    return provider


def get_model_name_from_chat_model() -> Optional[str]:
    """
    Get model name from system chat_model setting

    Returns:
        Model name from model-routing-registry, or None if not configured
    """
    from backend.app.services.model_routing_policy_service import (
        ModelRoutingPolicyService,
    )

    return ModelRoutingPolicyService().resolve_chat_default().model_name


import functools

@functools.lru_cache(maxsize=4)
def _get_cached_llm_provider_manager(
    openai_key: Optional[str] = None,
    openai_base_url: Optional[str] = None,
    anthropic_key: Optional[str] = None,
    vertex_api_key: Optional[str] = None,
    vertex_project_id: Optional[str] = None,
    vertex_location: Optional[str] = None,
    llama_model_path: Optional[str] = None,
    ollama_base_url: Optional[str] = None,
):
    from backend.app.services.agent_runner import LLMProviderManager
    return LLMProviderManager(
        openai_key=openai_key,
        openai_base_url=openai_base_url,
        anthropic_key=anthropic_key,
        vertex_api_key=vertex_api_key,
        vertex_project_id=vertex_project_id,
        vertex_location=vertex_location,
        llama_model_path=llama_model_path,
        ollama_base_url=ollama_base_url,
    )

def create_llm_provider_manager(
    openai_key: Optional[str] = None,
    anthropic_key: Optional[str] = None,
    vertex_api_key: Optional[str] = None,
    vertex_project_id: Optional[str] = None,
    vertex_location: Optional[str] = None,
    llama_model_path: Optional[str] = None,
    ollama_base_url: Optional[str] = None,
    provider_name: Optional[str] = None,
):
    """
    Create LLMProviderManager with registry-selected provider credentials.

    This function provides a unified way to create LLMProviderManager across the codebase.
    Provider selection must already be resolved by model-routing-registry; this helper
    only loads credentials for that selected provider.

    Args:
        openai_key: OpenAI API key (optional credential input)
        anthropic_key: Anthropic API key (optional credential input)
        vertex_api_key: Vertex AI service account JSON or file path (optional)
        vertex_project_id: Vertex AI project ID (optional)
        vertex_location: Vertex AI location (optional, defaults to us-central1)

    Returns:
        LLMProviderManager instance with all available providers configured
    """
    from backend.app.services.system_settings_store import SystemSettingsStore

    settings_store = SystemSettingsStore()

    # Load OpenAI credentials only when the registry-selected provider needs them.
    if provider_name in (None, "openai") and not openai_key:
        openai_setting = settings_store.get_setting("openai_api_key")
        openai_key = openai_setting.value if openai_setting else None
    if provider_name in (None, "openai") and not openai_key:
        openai_key = os.getenv("OPENAI_API_KEY")

    openai_base_url = None
    if provider_name in (None, "openai"):
        base_setting = settings_store.get_setting("openai_api_base")
        openai_base_url = base_setting.value if base_setting else os.getenv("OPENAI_API_BASE")
        if openai_base_url and not openai_key:
            openai_key = "dummy-key-for-local-endpoint"

    # Load Anthropic credentials only when the registry-selected provider needs them.
    if provider_name in (None, "anthropic") and not anthropic_key:
        anthropic_setting = settings_store.get_setting("anthropic_api_key")
        anthropic_key = anthropic_setting.value if anthropic_setting else None
    if provider_name in (None, "anthropic") and not anthropic_key:
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    # Load Vertex AI credentials only when the registry-selected provider needs them.
    if provider_name in (None, "vertex-ai") and not vertex_api_key:
        # UI / settings route writes the JSON credential to vertex_ai_service_account_json
        vertex_service_account = settings_store.get_setting(
            "vertex_ai_service_account_json"
        )
        vertex_api_key = (
            vertex_service_account.value if vertex_service_account else None
        )
    if provider_name in (None, "vertex-ai") and not vertex_api_key:
        vertex_api_key = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if provider_name in (None, "vertex-ai") and not vertex_project_id:
        vertex_project_setting = settings_store.get_setting("vertex_ai_project_id")
        vertex_project_id = (
            vertex_project_setting.value if vertex_project_setting else None
        )
    if provider_name in (None, "vertex-ai") and not vertex_project_id:
        vertex_project_id = os.getenv("GOOGLE_CLOUD_PROJECT")

    if provider_name in (None, "vertex-ai") and not vertex_location:
        vertex_location = os.getenv("VERTEX_LOCATION", "us-central1")

    # Load Llama credentials only when the registry-selected provider needs them.
    if provider_name in (None, "llama") and not llama_model_path:
        llama_setting = settings_store.get_setting("llama_model_path")
        llama_model_path = llama_setting.value if llama_setting else None
    if provider_name in (None, "llama") and not llama_model_path:
        llama_model_path = os.getenv("LLAMA_MODEL_PATH")

    # Load Ollama endpoint only when the registry-selected provider needs it.
    if provider_name in (None, "ollama") and not ollama_base_url:
        ollama_setting = settings_store.get_setting("ollama_base_url")
        ollama_base_url = ollama_setting.value if ollama_setting else None
    if provider_name in (None, "ollama") and not ollama_base_url:
        ollama_base_url = os.getenv("OLLAMA_BASE_URL")

    return _get_cached_llm_provider_manager(
        openai_key=openai_key,
        openai_base_url=openai_base_url,
        anthropic_key=anthropic_key,
        vertex_api_key=vertex_api_key,
        vertex_project_id=vertex_project_id,
        vertex_location=vertex_location,
        llama_model_path=llama_model_path,
        ollama_base_url=ollama_base_url,
    )


def build_managed_llm_provider(
    *,
    workspace: Optional[Any] = None,
    executor_runtime: Optional[str] = None,
    model_name: Optional[str] = None,
    provider_name: Optional[str] = None,
    allow_with_executor_runtime: bool = False,
    purpose: str = "general",
):
    """
    Resolve selection, build a scoped manager, and return the provider + selection.

    This is the preferred entry point for managed LLM use so call sites do not
    need to manually wire ``resolve_llm_selection`` + ``create_llm_provider_manager``
    + ``get_llm_provider_from_settings``.
    """
    selection = resolve_llm_selection(
        workspace=workspace,
        executor_runtime=executor_runtime,
        model_name=model_name,
        provider_name=provider_name,
        allow_with_executor_runtime=allow_with_executor_runtime,
        purpose=purpose,
    )
    if not selection.managed_llm_allowed:
        raise ManagedLLMDisabledForRuntime(
            f"Managed LLM disabled for purpose '{purpose}' because workspace is "
            f"bound to executor runtime '{selection.executor_runtime}'."
        )

    manager = create_llm_provider_manager(provider_name=selection.provider_name)
    provider = get_llm_provider_from_settings(
        manager,
        workspace=workspace,
        executor_runtime=executor_runtime,
        model_name=selection.model_name,
        provider_name=selection.provider_name,
        allow_with_executor_runtime=allow_with_executor_runtime,
        purpose=purpose,
    )
    return provider, selection
