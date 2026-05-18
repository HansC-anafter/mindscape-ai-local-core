"""Chat model connection test routes."""

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from backend.app.routes.core.system_settings.shared import settings_store

from .state import _utc_now

router = APIRouter()

@router.post("/llm-models/test-chat", response_model=Dict[str, Any])
async def test_chat_model_connection(
    model_name: Optional[str] = Query(
        None, description="Model name to test (uses current setting if not provided)"
    )
):
    """Test chat model connection"""
    try:
        import os
        from backend.app.services.config_store import ConfigStore
        from backend.app.services.model_routing_policy_service import (
            ModelRoutingPolicyService,
        )

        if not model_name:
            resolved_route = ModelRoutingPolicyService(
                settings_store=settings_store
            ).resolve_chat_default()
            if not resolved_route.model_name:
                raise HTTPException(status_code=400, detail="No chat model configured")
            model_name = str(resolved_route.model_name)
            provider = resolved_route.provider or "openai"
        else:
            if model_name.startswith("gpt") or model_name.startswith("text-"):
                provider = "openai"
            elif model_name.startswith("claude"):
                provider = "anthropic"
            else:
                provider = "openai"

        config_store = ConfigStore()
        config = config_store.get_or_create_config("default-user")

        if provider == "openai":
            api_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
            
            # Fallback: read from SystemSettingsStore (where the UI saves it)
            if not api_key:
                import asyncio as _asyncio
                _key_setting = await _asyncio.to_thread(
                    settings_store.get_setting, "openai_api_key"
                )
                if _key_setting and _key_setting.value:
                    api_key = _key_setting.value
            
            # Check for custom base URL
            import asyncio
            base_url_setting = await asyncio.to_thread(
                settings_store.get_setting, "openai_api_base"
            )
            base_url = base_url_setting.value if base_url_setting else os.getenv("OPENAI_API_BASE")
            
            if base_url and not api_key:
                api_key = "dummy-key-for-local-endpoint"
                
            if not api_key:
                raise HTTPException(
                    status_code=400, detail="OpenAI API key not configured"
                )
        elif provider == "anthropic":
            api_key = config.agent_backend.anthropic_api_key or os.getenv(
                "ANTHROPIC_API_KEY"
            )
            # Fallback: read from SystemSettingsStore (where the UI saves it)
            if not api_key:
                import asyncio as _asyncio
                _key_setting = await _asyncio.to_thread(
                    settings_store.get_setting, "anthropic_api_key"
                )
                if _key_setting and _key_setting.value:
                    api_key = _key_setting.value
            if not api_key:
                raise HTTPException(
                    status_code=400, detail="Anthropic API key not configured"
                )
        else:
            raise HTTPException(
                status_code=400, detail=f"Unsupported provider: {provider}"
            )

        try:
            if provider == "openai":
                import openai

                client_kwargs = {"api_key": api_key}
                if base_url:
                    client_kwargs["base_url"] = base_url

                client = openai.OpenAI(**client_kwargs)
                create_params = {
                    "model": model_name,
                    "messages": [{"role": "user", "content": "Hi"}],
                }
                if not (model_name.startswith("gpt-5") or "gpt-5" in model_name):
                    create_params["max_tokens"] = 10

                response = client.chat.completions.create(**create_params)
                success = bool(response.choices and len(response.choices) > 0)
                message = "Connection successful" if success else "Connection failed"
            elif provider == "anthropic":
                import anthropic

                client = anthropic.Anthropic(api_key=api_key)
                response = client.messages.create(
                    model=model_name,
                    max_tokens=10,
                    messages=[{"role": "user", "content": "Hello"}],
                )
                success = bool(response.content)
                message = "Connection successful" if success else "Connection failed"
            else:
                raise ValueError(f"Unsupported provider: {provider}")

            return {
                "success": success,
                "model_name": model_name,
                "provider": provider,
                "message": message,
                "tested_at": _utc_now().isoformat(),
            }
        except Exception as api_error:
            return {
                "success": False,
                "model_name": model_name,
                "provider": provider,
                "message": f"Connection failed: {str(api_error)}",
                "error": str(api_error),
                "tested_at": _utc_now().isoformat(),
            }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to test chat model: {str(e)}"
        )
