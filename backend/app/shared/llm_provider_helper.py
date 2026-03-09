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


def _infer_provider_name_from_model(model_name: str) -> Optional[str]:
    """Infer provider from model name when metadata is unavailable."""
    if not model_name:
        return None

    model_lower = model_name.lower()
    if "gemini" in model_lower:
        return "vertex-ai"
    if "gpt" in model_lower or "text-" in model_lower or "o1" in model_lower or "o3" in model_lower:
        return "openai"
    if "claude" in model_lower:
        return "anthropic"
    if any(
        x in model_lower for x in ["llama", "mistral", "gemma", "deepseek", "qwen", "phi"]
    ):
        return "ollama"
    return None


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
    return getattr(workspace, "resolved_executor_runtime", None) or getattr(
        workspace, "executor_runtime", None
    )


def resolve_llm_selection(
    *,
    workspace: Optional[Any] = None,
    executor_runtime: Optional[str] = None,
    model_name: Optional[str] = None,
    provider_name: Optional[str] = None,
    default_model: Optional[str] = None,
    allow_model_inference: bool = True,
    allow_with_executor_runtime: bool = False,
    purpose: str = "general",
) -> ResolvedLLMSelection:
    """
    Resolve model/provider under a runtime-aware governance policy.

    When a workspace is bound to an external executor runtime, managed LLM
    selection is disabled by default so request-paths do not silently fall back
    to server-side providers like Vertex AI.
    """
    from backend.app.services.system_settings_store import SystemSettingsStore

    chat_setting = None
    if model_name is None or provider_name is None:
        settings_store = SystemSettingsStore()
        chat_setting = settings_store.get_setting("chat_model")

    resolved_model_name = model_name
    if not resolved_model_name and chat_setting and chat_setting.value:
        resolved_model_name = str(chat_setting.value)
    if not resolved_model_name and default_model:
        resolved_model_name = default_model
    if not resolved_model_name:
        raise ValueError(
            f"chat_model not configured for purpose '{purpose}'. "
            "Please configure chat_model in Settings."
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
    if not resolved_provider_name and chat_setting:
        metadata = getattr(chat_setting, "metadata", None) or {}
        resolved_provider_name = metadata.get("provider")
    if not resolved_provider_name and allow_model_inference:
        resolved_provider_name = _infer_provider_name_from_model(resolved_model_name)
    if not resolved_provider_name:
        raise ValueError(
            f"Cannot determine LLM provider for model '{resolved_model_name}' "
            f"(purpose='{purpose}'). Configure provider in chat_model metadata."
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
    allow_model_inference: bool = True,
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
        allow_model_inference=allow_model_inference,
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
    default_model: Optional[str] = None,
    allow_model_inference: bool = True,
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
        default_model=default_model,
        allow_model_inference=allow_model_inference,
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
        from backend.app.services.system_settings_store import SystemSettingsStore

        settings_store = SystemSettingsStore()
        chat_setting = settings_store.get_setting("chat_model")
        resolved_model_name = (
            selection.model_name
            or (str(chat_setting.value) if chat_setting and chat_setting.value else "unknown")
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


def get_model_name_from_chat_model(default: Optional[str] = None) -> Optional[str]:
    """
    Get model name from system chat_model setting

    Returns:
        Model name (e.g., 'gemini-2.5-pro', 'gpt-4o-mini') or None if not configured
    """
    from backend.app.services.system_settings_store import SystemSettingsStore

    settings_store = SystemSettingsStore()
    chat_setting = settings_store.get_setting("chat_model")

    if not chat_setting:
        return default

    return str(chat_setting.value)


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
    Create LLMProviderManager with unified configuration from system settings

    This function provides a unified way to create LLMProviderManager across the codebase.
    It reads configuration from system settings first, then falls back to environment variables,
    and finally uses provided parameters.

    Args:
        openai_key: OpenAI API key (optional, will be read from system settings or env if not provided)
        anthropic_key: Anthropic API key (optional, will be read from system settings or env if not provided)
        vertex_api_key: Vertex AI service account JSON or file path (optional)
        vertex_project_id: Vertex AI project ID (optional)
        vertex_location: Vertex AI location (optional, defaults to us-central1)

    Returns:
        LLMProviderManager instance with all available providers configured
    """
    from backend.app.services.agent_runner import LLMProviderManager
    from backend.app.services.system_settings_store import SystemSettingsStore

    settings_store = SystemSettingsStore()

    # Get OpenAI key: parameter > system settings > environment variable
    if provider_name in (None, "openai") and not openai_key:
        openai_setting = settings_store.get_setting("openai_api_key")
        openai_key = openai_setting.value if openai_setting else None
    if provider_name in (None, "openai") and not openai_key:
        openai_key = os.getenv("OPENAI_API_KEY")

    # Get Anthropic key: parameter > system settings > environment variable
    if provider_name in (None, "anthropic") and not anthropic_key:
        anthropic_setting = settings_store.get_setting("anthropic_api_key")
        anthropic_key = anthropic_setting.value if anthropic_setting else None
    if provider_name in (None, "anthropic") and not anthropic_key:
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    # Get Vertex AI config: parameter > system settings > environment variable
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

    # Get Llama model path: parameter > system settings > environment variable
    if provider_name in (None, "llama") and not llama_model_path:
        llama_setting = settings_store.get_setting("llama_model_path")
        llama_model_path = llama_setting.value if llama_setting else None
    if provider_name in (None, "llama") and not llama_model_path:
        llama_model_path = os.getenv("LLAMA_MODEL_PATH")

    # Get Ollama base URL: parameter > system settings > environment variable
    if provider_name in (None, "ollama") and not ollama_base_url:
        ollama_setting = settings_store.get_setting("ollama_base_url")
        ollama_base_url = ollama_setting.value if ollama_setting else None
    if provider_name in (None, "ollama") and not ollama_base_url:
        ollama_base_url = os.getenv("OLLAMA_BASE_URL")

    return LLMProviderManager(
        openai_key=openai_key,
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
    default_model: Optional[str] = None,
    allow_model_inference: bool = True,
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
        default_model=default_model,
        allow_model_inference=allow_model_inference,
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
        default_model=default_model,
        allow_model_inference=allow_model_inference,
        allow_with_executor_runtime=allow_with_executor_runtime,
        purpose=purpose,
    )
    return provider, selection
