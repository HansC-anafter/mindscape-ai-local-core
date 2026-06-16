from __future__ import annotations

import json
import logging
import os
import urllib.request
from typing import Any, Dict, List, Optional

from backend.app.services.system_health_models import HealthIssue, HealthIssueSeverity

logger = logging.getLogger("backend.app.services.system_health_checker")


class SystemHealthLlmMixin:
    @staticmethod
    def _normalize_ollama_model_name(model_name: Optional[str]) -> str:
        if not model_name:
            return ""
        normalized = str(model_name).strip()
        if normalized.startswith("ollama/"):
            normalized = normalized.split("/", 1)[1]
        return normalized

    def _check_ollama_configuration(
        self,
        base_url: Optional[str],
        model_name: Optional[str],
        issues: List[HealthIssue],
    ) -> Dict[str, Any]:
        resolved_base_url = (base_url or "").strip().rstrip("/")
        if not resolved_base_url:
            issues.append(HealthIssue(
                issue_type="ollama_not_configured",
                severity=HealthIssueSeverity.WARNING,
                message="Ollama base URL is not configured. Local LLM features may be unavailable.",
                action_url="/settings?tab=llm",
            ))
            return {
                "configured": False,
                "provider": "ollama",
                "available": False,
            }

        try:
            with urllib.request.urlopen(
                f"{resolved_base_url}/api/tags",
                timeout=5,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            logger.warning("Ollama health check failed: %s", exc)
            issues.append(HealthIssue(
                issue_type="ollama_unavailable",
                severity=HealthIssueSeverity.WARNING,
                message=f"Ollama is unavailable at {resolved_base_url}: {exc}",
                action_url="/settings?tab=llm",
            ))
            return {
                "configured": True,
                "provider": "ollama",
                "available": False,
            }

        models = payload.get("models", []) if isinstance(payload, dict) else []
        available_model_names = {
            str(value).strip()
            for model in models
            if isinstance(model, dict)
            for value in (model.get("name"), model.get("model"))
            if value
        }
        normalized_model_name = self._normalize_ollama_model_name(model_name)
        if normalized_model_name and normalized_model_name not in available_model_names:
            issues.append(HealthIssue(
                issue_type="ollama_model_missing",
                severity=HealthIssueSeverity.WARNING,
                message=(
                    f"Ollama model '{normalized_model_name}' is not installed at "
                    f"{resolved_base_url}. Local LLM features may be unavailable."
                ),
                action_url="/settings?tab=llm",
            ))
            return {
                "configured": True,
                "provider": "ollama",
                "available": False,
                "model": normalized_model_name,
            }

        return {
            "configured": True,
            "provider": "ollama",
            "available": bool(available_model_names),
            "model": normalized_model_name,
        }

    async def _check_llm_configuration(
        self,
        profile_id: str,
        issues: List[HealthIssue]
    ) -> Dict[str, Any]:
        """Check LLM API key configuration by actually testing the connection"""
        try:
            if profile_id == "default-user":
                from backend.app.services.mindscape_store import MindscapeStore
                MindscapeStore().ensure_default_profile()

            config = self.config_store.get_or_create_config(profile_id)
            available_backends = self.backend_manager.get_available_backends()

            current_mode = config.agent_backend.mode
            current_backend = available_backends.get(current_mode, {})

            provider = current_mode

            # Actually test the connection instead of just checking if backend is available
            # Test LLM connection by making an actual API call
            configured = False
            available = False

            try:
                import os
                from backend.app.services.system_settings_store import SystemSettingsStore
                from backend.app.services.model_routing_policy_service import (
                    ModelRoutingPolicyService,
                )

                settings_store = SystemSettingsStore()
                resolved_route = ModelRoutingPolicyService(
                    settings_store=settings_store
                ).resolve_chat_default()

                if resolved_route.model_name:
                    model_name = str(resolved_route.model_name)
                    provider = resolved_route.provider or "openai"

                    # Get API key, local endpoint, or Vertex AI configuration.
                    if provider == "openai":
                        api_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
                        # Fallback: read from SystemSettingsStore (where the UI saves it)
                        if not api_key:
                            openai_key_setting = settings_store.get_setting("openai_api_key")
                            if openai_key_setting and openai_key_setting.value:
                                api_key = openai_key_setting.value
                        try:
                            base_url_setting = settings_store.get_setting("openai_api_base")
                            base_url = base_url_setting.value if base_url_setting else os.getenv("OPENAI_API_BASE")
                        except Exception:
                            base_url = os.getenv("OPENAI_API_BASE")
                        if base_url and not api_key:
                            api_key = "dummy-key-for-local-endpoint"
                        vertex_ai_configured = False
                    elif provider == "anthropic":
                        api_key = config.agent_backend.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
                        # Fallback: read from SystemSettingsStore (where the UI saves it)
                        if not api_key:
                            anthropic_key_setting = settings_store.get_setting("anthropic_api_key")
                            if anthropic_key_setting and anthropic_key_setting.value:
                                api_key = anthropic_key_setting.value
                        vertex_ai_configured = False
                    elif provider == "vertex-ai":
                        # Check Vertex AI configuration
                        vertex_ai_service_account = settings_store.get_setting("vertex_ai_service_account_json")
                        vertex_ai_project_id = settings_store.get_setting("vertex_ai_project_id")
                        vertex_ai_location = settings_store.get_setting("vertex_ai_location")
                        vertex_ai_configured = bool(
                            vertex_ai_service_account and
                            vertex_ai_service_account.value and
                            vertex_ai_project_id and
                            vertex_ai_project_id.value
                        )
                        api_key = None  # Vertex AI doesn't use API key
                    elif provider == "ollama":
                        try:
                            ollama_setting = settings_store.get_setting("ollama_base_url")
                            ollama_base_url = ollama_setting.value if ollama_setting else None
                        except Exception:
                            ollama_base_url = None
                        ollama_base_url = (
                            ollama_base_url
                            or os.getenv("OLLAMA_BASE_URL")
                            or os.getenv("OLLAMA_HOST")
                            or "http://localhost:11434"
                        )
                        ollama_status = self._check_ollama_configuration(
                            ollama_base_url,
                            model_name,
                            issues,
                        )
                        configured = ollama_status["configured"]
                        available = ollama_status["available"]
                        api_key = None
                        vertex_ai_configured = False
                    else:
                        api_key = None
                        vertex_ai_configured = False

                    if provider == "ollama":
                        pass
                    elif api_key or vertex_ai_configured:
                        # Test connection with a simple API call
                        try:
                            if provider == "openai":
                                import openai
                                client_kwargs = {"api_key": api_key}
                                if 'base_url' in locals() and base_url:
                                    client_kwargs["base_url"] = base_url
                                client = openai.OpenAI(**client_kwargs)
                                create_params = {
                                    "model": model_name,
                                    "messages": [{"role": "user", "content": "Hi"}]
                                }
                                if not (model_name.startswith("gpt-5") or "gpt-5" in model_name):
                                    create_params["max_tokens"] = 10
                                response = client.chat.completions.create(**create_params)
                                configured = bool(response.choices and len(response.choices) > 0)
                                available = configured
                            elif provider == "anthropic":
                                import anthropic
                                client = anthropic.Anthropic(api_key=api_key)
                                response = client.messages.create(
                                    model=model_name,
                                    max_tokens=10,
                                    messages=[{"role": "user", "content": "Hello"}]
                                )
                                configured = bool(response.content)
                                available = configured
                            elif provider == "vertex-ai":
                                # For Vertex AI, if configuration exists, consider it configured
                                # Actual connection test would require GCP credentials setup
                                configured = vertex_ai_configured
                                available = configured
                        except Exception as api_error:
                            logger.warning(f"LLM connection test failed: {api_error}")
                            configured = False
                            available = False

                            if current_mode == "local":
                                error_msg = str(api_error)
                                issues.append(HealthIssue(
                                    issue_type="api_key_invalid",
                                    severity=HealthIssueSeverity.ERROR,
                                    message=f"LLM API key may be invalid or expired: {error_msg}",
                                    action_url="/settings?tab=llm"
                                ))
                    else:
                        if current_mode == "local":
                            if provider == "vertex-ai":
                                issues.append(HealthIssue(
                                    issue_type="vertex_ai_not_configured",
                                    severity=HealthIssueSeverity.ERROR,
                                    message="Vertex AI is not configured (service account JSON and project ID required)",
                                    action_url="/settings?tab=llm"
                                ))
                            else:
                                # Missing API key is a WARNING, not ERROR, to allow system startup
                                # Some features may be unavailable, but core functionality should work
                                issues.append(HealthIssue(
                                    issue_type="api_key_missing",
                                    severity=HealthIssueSeverity.WARNING,
                                    message="LLM API key not configured (OpenAI or Anthropic). Some AI features may be unavailable.",
                                    action_url="/settings?tab=llm"
                                ))
                else:
                    # No chat model configured, check if API keys exist
                    if current_mode == "local":
                        if config.agent_backend.openai_api_key or config.agent_backend.anthropic_api_key:
                            # Has keys but no model configured
                            configured = current_backend.get("available", False)
                            available = configured
                        else:
                            # Missing API key is a WARNING, not ERROR, to allow system startup
                            # Some features may be unavailable, but core functionality should work
                            issues.append(HealthIssue(
                                issue_type="api_key_missing",
                                severity=HealthIssueSeverity.WARNING,
                                message="LLM API key not configured (OpenAI or Anthropic). Some AI features may be unavailable.",
                                action_url="/settings?tab=llm"
                            ))
                            configured = False
                            available = False
                    elif current_mode == "remote_crs":
                        if not config.agent_backend.remote_crs_url or not config.agent_backend.remote_crs_token:
                            issues.append(HealthIssue(
                                issue_type="remote_crs_not_configured",
                                severity=HealthIssueSeverity.ERROR,
                                message="Remote CRS is not configured",
                                action_url="/settings?tab=backend"
                            ))
                            configured = False
                            available = False
                        else:
                            configured = current_backend.get("available", False)
                            available = configured
            except Exception as test_error:
                logger.warning(f"LLM connection test error: {test_error}")
                # Fallback to old method
                configured = current_backend.get("available", False)
                available = configured

                if not configured and current_mode == "local":
                    if not config.agent_backend.openai_api_key and not config.agent_backend.anthropic_api_key:
                        # Missing API key is a WARNING, not ERROR, to allow system startup
                        # Some features may be unavailable, but core functionality should work
                        issues.append(HealthIssue(
                            issue_type="api_key_missing",
                            severity=HealthIssueSeverity.WARNING,
                            message="LLM API key not configured (OpenAI or Anthropic). Some AI features may be unavailable.",
                            action_url="/settings?tab=llm"
                        ))

            # Normalize provider name for consistent display
            provider_display = provider
            if provider == "vertex-ai" or provider == "vertex_ai":
                provider_display = "vertex-ai"
            elif provider == "anthropic":
                provider_display = "anthropic"
            elif provider == "openai":
                provider_display = "openai"

            return {
                "configured": configured,
                "provider": provider_display,
                "available": available
            }
        except Exception as e:
            logger.error(f"Failed to check LLM configuration: {e}", exc_info=True)
            issues.append(HealthIssue(
                issue_type="llm_check_failed",
                severity=HealthIssueSeverity.ERROR,
                message=f"Error checking LLM configuration: {str(e)}",
                action_url="/settings"
            ))
            return {
                "configured": False,
                "provider": None,
                "available": False
            }
