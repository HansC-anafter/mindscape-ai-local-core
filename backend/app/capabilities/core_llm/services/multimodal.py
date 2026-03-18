"""
Core LLM: Multimodal Analyze Service

Unified middleware for multimodal (vision) analysis.
Routes to cloud LLM or local HF model based on system settings.

Three-layer routing:
  Layer 1 (Settings):  Global policy — provider availability, model map
  Layer 2 (Playbook):  Declarative needs — modalities, reasoning, locality
  Layer 3 (Resolver):  Runtime decision — _model_override from resolver chain
"""

import asyncio
import importlib
import importlib.util
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# MLX VLM server can only handle 1 inference at a time; throttle concurrent calls
_MLX_SEMAPHORE = asyncio.Semaphore(1)


def _detect_image_mime(b64_data: str) -> str:
    """Detect image MIME type from base64-encoded magic bytes.

    Uses raw magic bytes instead of imghdr (removed in Python 3.13).
    """
    import base64
    try:
        raw = base64.b64decode(b64_data[:32])
        if raw[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"
        if raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
            return "image/webp"
        if raw[:3] == b'GIF':
            return "image/gif"
    except Exception:
        pass
    return "image/jpeg"


async def vision_analyze(
    images: List[Dict[str, Any]],
    prompt: str = (
        "You are an expert visual analyst. "
        "Describe the visual elements, style, lighting, vibe, and subject "
        "of this image. Keep it concise and focus on visual persona."
    ),
    temperature: Optional[float] = None,
    workspace_id: Optional[str] = None,
    _model_override: Optional[str] = None,
    **kwargs,  # absorb extra playbook inputs (profile_id, etc.)
) -> Dict[str, Any]:
    """
    Unified multimodal analysis — routes to cloud or local model.

    Routing priority:
      1. _model_override (injected by resolver chain / workflow_orchestrator)
      2. 'multimodal_model' from SystemSettingsStore
      3. Fallback: Qwen2-VL-9B via HF

    Args:
        images: List of dicts with 'shortcode' and 'base64_jpeg' keys.
        prompt: Text prompt for the analysis.
        temperature: Sampling temperature.
        workspace_id: Optional workspace context.
        _model_override: Model override from resolver chain (takes priority).

    Returns:
        Dict with status, analyzed_count, model_id, and results.
    """
    if not images:
        return {"status": "skipped", "reason": "No images provided"}

    # Handle stringified JSON from playbook template engine interpolation
    if isinstance(images, str):
        import json
        try:
            images = json.loads(images)
        except Exception as e:
            logger.warning(f"[MultimodalAnalyze] Failed to parse images string: {e}")
            return {"status": "error", "error": f"Invalid images format: {e}"}

    if temperature is None:
        temperature = 0.3

    # ── Resolve model ──
    model_name, provider_name = _resolve_multimodal_model(_model_override)
    
    if not model_name or not provider_name:
        return {
            "status": "error",
            "error": "No vision model configured or available",
            "recoverable": True,
            "error_type": "provider_unavailable"
        }

    logger.info(
        f"[MultimodalAnalyze] Resolved model={model_name}, provider={provider_name}"
    )

    from ....services.model_config_store import ModelConfigStore
    store = ModelConfigStore()

    # Route request to specific provider
    if provider_name == "vertex-ai":
        # Resolve temperature default from DB if not provided
        if temperature is None:
            m = store.get_model_by_name(model_name)
            if m and m.metadata and "temperature" in m.metadata:
                temperature = float(m.metadata["temperature"])
        if temperature is None:
            temperature = 0.4
            
        return await _route_cloud_llm(
            images, prompt, model_name, "vertex-ai", temperature, workspace_id
        )

    elif provider_name == "openai" or provider_name == "anthropic":
        # Resolve temperature default from DB if not provided
        if temperature is None:
            m = store.get_model_by_name(model_name)
            if m and m.metadata and "temperature" in m.metadata:
                temperature = float(m.metadata["temperature"])
        if temperature is None:
            temperature = 0.4
            
        return await _route_cloud_llm(
            images, prompt, model_name, provider_name, temperature, workspace_id
        )

    elif provider_name == "mlx":
        if temperature is None:
            m = store.get_model_by_name(model_name)
            if m and m.metadata and "temperature" in m.metadata:
                temperature = float(m.metadata["temperature"])
        if temperature is None:
            temperature = 0.6
            
        return await _route_mlx_server(images, prompt, model_name, temperature)

    elif provider_name == "huggingface":
        if temperature is None:
            m = store.get_model_by_name(model_name)
            if m and m.metadata and "temperature" in m.metadata:
                temperature = float(m.metadata["temperature"])
        if temperature is None:
            temperature = 0.6
            
        return await _route_huggingface(images, prompt, model_name, temperature)

    # Fallback for any other provider_name that might be passed
    return await _route_cloud_llm(
        images, prompt, model_name, provider_name, temperature, workspace_id
    )


def _resolve_multimodal_model(
    _model_override: Optional[str] = None,
) -> tuple:
    """Resolve model with priority: _model_override > settings > fallback."""

    # Priority 1: Resolver chain override (already resolved by workflow_orchestrator)
    if _model_override:
        try:
            from ....services.model_config_store import ModelConfigStore
            store = ModelConfigStore()
            
            # Since model_override is just a name (e.g. 'mlx-community/Qwen3.5-9B-4bit'),
            # we try to find it by scanning models if no exact getter exists
            m = None
            if hasattr(store, 'get_model_by_name_and_provider'):
                from ....models.model_provider import ModelType
                # Best effort: try common vision providers
                for test_prov in ["mlx", "openai", "vertex-ai", "huggingface"]:
                    m = store.get_model_by_name_and_provider(_model_override, test_prov, ModelType.MULTIMODAL)
                    if m:
                        break
                        
            if m:
                db_provider = getattr(m, 'provider_name', None)
                meta = getattr(m, 'metadata', None)
                provider = _determine_runtime_provider(_model_override, db_provider, meta)
            else:
                provider = _determine_runtime_provider(_model_override)
        except Exception as e:
            logger.warning("[MultimodalAnalyze] Failed to get model config for override %s: %s", _model_override, e)
            provider = _guess_provider(_model_override)

        logger.info(
            "[MultimodalAnalyze] Using _model_override=%s (provider=%s)",
            _model_override, provider,
        )
        return _model_override, provider

    # Priority 2: Delegate to system CapabilityProfileResolver (Gap-C fix)
    try:
        from ....services.capability_profile_resolver import (
            CapabilityProfileResolver,
        )

        # Vision modality — let resolver pick the model
        resolved_model, _variant = CapabilityProfileResolver().resolve(
            "vision",
            execution_profile={"modalities": ["vision"]},
        )
        if resolved_model:
            db_provider = _get_db_provider(resolved_model)
            meta = _get_db_metadata(resolved_model)
            provider = _determine_runtime_provider(resolved_model, db_provider, meta)
            logger.info(
                "[MultimodalAnalyze] Resolver chose model=%s (provider=%s)",
                resolved_model, provider,
            )
            return resolved_model, provider
    except Exception as e:
        logger.warning(
            "[MultimodalAnalyze] CapabilityProfileResolver failed, "
            "trying settings fallback: %s", e,
        )

    # Priority 3: System settings (legacy fallback)
    try:
        from ....services.system_settings_store import SystemSettingsStore
        from ....services.model_config_store import ModelConfigStore
        from ....models.model_provider import ModelType

        settings_store = SystemSettingsStore()
        mm_setting = settings_store.get_setting("multimodal_model")

        if mm_setting and mm_setting.value:
            model_name = str(mm_setting.value)

            # Try to find provider from model config
            model_store = ModelConfigStore()
            all_models = model_store.get_all_models(
                model_type=ModelType.MULTIMODAL, enabled=True
            )
            for m in all_models:
                if m.model_name == model_name:
                    return model_name, _determine_runtime_provider(model_name, m.provider_name, m.metadata)

            return model_name, _determine_runtime_provider(model_name)

    except Exception as e:
        logger.warning(
            "[MultimodalAnalyze] Settings lookup failed: %s", e,
        )

    # Priority 4: Auto-discover enabled multimodal model
    try:
        from ....services.model_config_store import ModelConfigStore
        from ....models.model_provider import ModelType
        store = ModelConfigStore()
        enabled = store.get_all_models(model_type=ModelType.MULTIMODAL, enabled=True)
        if enabled:
            model = enabled[0]
            provider = _determine_runtime_provider(model.model_name, model.provider_name, model.metadata)
            logger.info(
                "[MultimodalAnalyze] Auto-discovered model: %s (provider=%s)",
                model.model_name, provider,
            )
            return model.model_name, provider
    except Exception as e:
        logger.warning("[MultimodalAnalyze] Auto-discovery failed: %s", e)

    # Priority 5: Hardcoded fallback
    return None, None


def _determine_runtime_provider(model_name: str, db_provider: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> str:
    """
    Determine the runtime execution provider (routing engine).
    Priority:
      1. metadata.runtime_engine (user override from UI)
      2. Heuristics (if DB provider is huggingface, but name implies MLX, force MLX)
      3. db_provider
      4. _guess_provider
    """
    if metadata and metadata.get("runtime_engine") and metadata.get("runtime_engine") != "auto":
        engine = metadata.get("runtime_engine")
        logger.info("[MultimodalAnalyze] Resolved runtime_engine '%s' from metadata override", engine)
        return engine
        
    name = model_name.lower()
    if "mlx-community" in name or "mlx" in name:
        return "mlx"
    
    if db_provider:
        return db_provider
        
    return _guess_provider(model_name)

def _get_db_metadata(model_name: str) -> Optional[Dict[str, Any]]:
    """Helper to fetch metadata from database."""
    try:
        from ....services.model_config_store import ModelConfigStore
        store = ModelConfigStore()
        model = store.get_model_by_name(model_name)
        if model:
            return model.metadata
    except Exception as e:
        logger.warning("[MultimodalAnalyze] Failed to get db metadata: %s", e)
    return None

def _get_db_provider(model_name: str) -> Optional[str]:
    """Helper to fetch provider from database."""
    try:
        from ....services.model_config_store import ModelConfigStore
        store = ModelConfigStore()
        model = store.get_model_by_name(model_name)
        if model:
            return model.provider_name
    except Exception as e:
        logger.warning("[MultimodalAnalyze] Failed to get db provider: %s", e)
    return None


def _guess_provider(model_name: str) -> str:
    """Guess provider from model name heuristics."""
    name = model_name.lower()
    if "mlx-community" in name or "mlx" in name:
        return "mlx"
    if "qwen" in name or "llama" in name or "mistral" in name:
        return "huggingface"
    if "gemini" in name:
        return "vertex-ai"
    if "gpt" in name:
        return "openai"
    if "claude" in name:
        return "anthropic"
    return "huggingface"


def _resolve_mlx_base_url(model_name: str) -> str:
    """Resolve MLX server base URL from DB config.

    Priority:
      1. ModelConfig.metadata['base_url'] for the specific model
      2. 'huggingface_base_url' system setting (provider-level)
      3. MLX_SERVER_HOST environment variable
      4. Fallback: http://host.docker.internal:8210
    """
    _FALLBACK = "http://host.docker.internal:8210"

    # Priority 1: Model-level metadata.base_url
    try:
        from ....services.model_config_store import ModelConfigStore
        from ....models.model_provider import ModelType

        store = ModelConfigStore()
        # Try exact match first
        models = store.get_all_models(model_type=ModelType.MULTIMODAL, enabled=True)
        for m in models:
            if m.model_name == model_name and m.metadata:
                base_url = m.metadata.get("base_url")
                if base_url:
                    logger.info(
                        "[MultimodalAnalyze] Resolved base_url from model metadata: %s",
                        base_url,
                    )
                    return base_url.rstrip("/")
    except Exception as e:
        logger.debug("[MultimodalAnalyze] Model metadata lookup failed: %s", e)

    # Priority 2: Provider-level system setting
    try:
        from ....services.system_settings_store import SystemSettingsStore

        settings = SystemSettingsStore()
        setting = settings.get_setting("huggingface_base_url")
        if setting and setting.value:
            logger.info(
                "[MultimodalAnalyze] Resolved base_url from huggingface_base_url setting: %s",
                setting.value,
            )
            return setting.value.rstrip("/")
    except Exception as e:
        logger.debug("[MultimodalAnalyze] System setting lookup failed: %s", e)

    # Priority 3: Environment variable
    env_host = os.getenv("MLX_SERVER_HOST")
    if env_host:
        logger.info(
            "[MultimodalAnalyze] Resolved base_url from MLX_SERVER_HOST env: %s",
            env_host,
        )
        return env_host.rstrip("/")

    # Priority 4: Hardcoded fallback
    logger.info(
        "[MultimodalAnalyze] Using fallback MLX base_url: %s", _FALLBACK
    )
    return _FALLBACK


async def _route_mlx_server(
    images: List[Dict[str, Any]],
    prompt: str,
    model_name: str,
    temperature: float,
) -> Dict[str, Any]:
    """Route to local MLX server (OpenAI-compatible API on host).

    Base URL resolution priority:
      1. Model metadata 'base_url' from model_configs DB table
      2. 'huggingface_base_url' system setting
      3. MLX_SERVER_HOST environment variable
      4. Fallback: http://host.docker.internal:8210
    """
    import httpx

    mlx_host = _resolve_mlx_base_url(model_name)
    url = f"{mlx_host}/v1/chat/completions"

    logger.info(
        "[MultimodalAnalyze] Routing to MLX server: %s (model=%s)",
        url, model_name,
    )

    results = []
    
    if not images:
        return {
            "status": "error",
            "error": "No images provided",
            "recoverable": False,
            "error_type": "invalid_request",
        }
        
    main_shortcode = images[0].get("shortcode", "unknown")
    
    content = [{"type": "text", "text": prompt}]
    for img_data in images:
        b64_jpeg = img_data.get("base64_jpeg", "")
        if b64_jpeg:
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{_detect_image_mime(b64_jpeg)};base64,{b64_jpeg}"
                },
            })

    messages = [
        {
            "role": "system",
            "content": "/no_think\nYou are a vision analysis API. "
                       "Output ONLY the raw JSON object. "
                       "No thinking, no explanation, no markdown. "
                       "Start your response with '{' immediately.",
        },
        {
            "role": "user",
            "content": content,
        }
    ]

    async with httpx.AsyncClient(timeout=1200.0) as client:
        try:
            from ....shared.inference_config import InferenceConfig
            resolved_max = InferenceConfig.get_max_tokens(model_name, caller_default=6144)
            
            first_b64 = images[0].get("base64_jpeg", "")
            mime = _detect_image_mime(first_b64) if first_b64 else "unknown"
            logger.info("[MLX] MIME=%s max_tokens=%d model=%s", mime, resolved_max, model_name)

            # Acquire semaphore so only 1 MLX inference runs at a time
            async with _MLX_SEMAPHORE:
                logger.info(
                    "[MultimodalAnalyze] MLX semaphore acquired for %s with %d images",
                    main_shortcode, len(content) - 1,
                )
                resp = await client.post(
                    url,
                    json={
                        "model": model_name,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": resolved_max,
                        "response_format": {"type": "json_object"},
                    },
                )
            
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0]["message"]
            
            # Prefer content over reasoning; when both exist,
            # pick whichever looks like JSON (starts with '{').
            resp_content = (msg.get("content") or "").strip()
            reasoning = (msg.get("reasoning") or "").strip()
            if resp_content and resp_content.startswith("{"):
                text = resp_content
            elif reasoning and reasoning.startswith("{"):
                text = reasoning
            else:
                text = resp_content or reasoning
                
            if text:
                results.append({"shortcode": main_shortcode, "description": text})
                logger.info(
                    "[MultimodalAnalyze] MLX analysis OK for %s (%d chars)",
                    main_shortcode, len(text),
                )
        except Exception as e:
            logger.warning(
                "[MultimodalAnalyze] MLX server call failed for %s: %s",
                main_shortcode, e,
            )

    if not results:
        return {
            "status": "error",
            "error": "MLX server unreachable or returned no results",
            "recoverable": True,
            "error_type": "provider_unavailable",
        }

    return {
        "status": "success",
        "analyzed_count": len(results),
        "model_id": model_name,
        "provider": "mlx",
        "results": results,
    }


async def _route_huggingface(
    images: List[Dict[str, Any]],
    prompt: str,
    model_id: str,
    temperature: float,
) -> Dict[str, Any]:
    """Route to Hugging Face VLM (Qwen2-VL etc.)."""
    vision_analyze = _load_hf_vision_tool()
    if vision_analyze is None:
        return {
            "status": "error",
            "error": "Hugging Face vision tool not available. "
                     "Is the huggingface capability pack installed?",
        }

    return await vision_analyze(
        images=images,
        prompt=prompt,
        model_id=model_id,
        temperature=temperature,
    )


# Module-level cache for HF vision tool (avoid re-import per call)
_hf_vision_cache: dict = {"fn": None, "source": None, "checked": False}


def _load_hf_vision_tool():
    """Dynamically load HF vision tool from installed capability pack.

    Gap-D: Explicit logging of which path was used, with cached result.
    """
    if _hf_vision_cache["checked"]:
        return _hf_vision_cache["fn"]

    _hf_vision_cache["checked"] = True

    # Try 1: Installed pack in capabilities volume
    pack_paths = [
        Path("/app/data/capabilities/huggingface/tools/vision.py"),
        Path("/app/capabilities/huggingface/tools/vision.py"),
    ]
    for pack_path in pack_paths:
        if pack_path.exists():
            try:
                spec = importlib.util.spec_from_file_location(
                    "hf_vision", str(pack_path)
                )
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    fn = getattr(mod, "vision_analyze", None)
                    if fn and callable(fn):
                        _hf_vision_cache["fn"] = fn
                        _hf_vision_cache["source"] = str(pack_path)
                        logger.info(
                            "[MultimodalAnalyze] HF vision tool loaded via dynamic import: %s",
                            pack_path,
                        )
                        return fn
                    else:
                        logger.warning(
                            "[MultimodalAnalyze] %s exists but vision_analyze not found/callable",
                            pack_path,
                        )
            except Exception as e:
                logger.warning(
                    "[MultimodalAnalyze] Failed to load from %s: %s", pack_path, e,
                )
        else:
            logger.debug(
                "[MultimodalAnalyze] Pack path not found: %s", pack_path,
            )

    # Try 2: Direct import (dev environment)
    try:
        from capabilities.huggingface.tools.vision import vision_analyze
        _hf_vision_cache["fn"] = vision_analyze
        _hf_vision_cache["source"] = "direct_import"
        logger.info(
            "[MultimodalAnalyze] HF vision tool loaded via direct import"
        )
        return vision_analyze
    except ImportError:
        logger.debug(
            "[MultimodalAnalyze] Direct import failed (not in dev environment)"
        )

    logger.error(
        "[MultimodalAnalyze] HF vision tool not available. "
        "Searched: %s + direct import. Is huggingface pack installed?",
        [str(p) for p in pack_paths],
    )
    return None


def check_hf_vision_health() -> Dict[str, Any]:
    """Health check for HF vision tool availability.

    Call at startup or via /health endpoint to validate.
    """
    fn = _load_hf_vision_tool()
    return {
        "available": fn is not None,
        "source": _hf_vision_cache.get("source"),
    }


async def _route_cloud_llm(
    images: List[Dict[str, Any]],
    prompt: str,
    model_name: str,
    provider_name: str,
    temperature: float,
    workspace_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Route to cloud LLM (OpenAI / Anthropic / Vertex AI) via call_llm."""
    from ....shared.llm_utils import call_llm
    from ....services.agent_runner import LLMProviderManager
    from ....services.system_settings_store import SystemSettingsStore

    settings_store = SystemSettingsStore()

    # Build LLM provider
    openai_key = os.getenv("OPENAI_API_KEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    vertex_sa = None
    vertex_project = None
    vertex_location = None

    if provider_name == "vertex-ai" or "gemini" in model_name.lower():
        sa_setting = settings_store.get_setting("vertex_ai_service_account_json")
        proj_setting = settings_store.get_setting("vertex_ai_project_id")
        loc_setting = settings_store.get_setting("vertex_ai_location")
        vertex_sa = (sa_setting.value if sa_setting else None) or os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS"
        )
        vertex_project = (proj_setting.value if proj_setting else None) or os.getenv(
            "GOOGLE_CLOUD_PROJECT"
        )
        vertex_location = (loc_setting.value if loc_setting else None) or os.getenv(
            "VERTEX_LOCATION", "us-central1"
        )

    llm_provider = LLMProviderManager(
        openai_key=openai_key,
        anthropic_key=anthropic_key,
        vertex_api_key=vertex_sa,
        vertex_project_id=vertex_project,
        vertex_location=vertex_location,
    )

    results = []
    
    if not images:
        return {
            "status": "error",
            "error": "No images provided",
            "recoverable": False,
            "error_type": "invalid_request",
        }
        
    main_shortcode = images[0].get("shortcode", "unknown")
    content = [{"type": "text", "text": prompt}]
    
    for img_data in images:
        b64_jpeg = img_data.get("base64_jpeg", "")
        if b64_jpeg:
            mime_type = _detect_image_mime(b64_jpeg)
            if provider_name == "anthropic":
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": b64_jpeg
                    }
                })
            else:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{b64_jpeg}"},
                })

    messages = [
        {
            "role": "user",
            "content": content,
        }
    ]

    try:
        resp = await call_llm(
            messages=messages,
            llm_provider=llm_provider,
            model=model_name,
            temperature=temperature,
        )
        description = resp.get("text", "").strip()
        if description:
            results.append({"shortcode": main_shortcode, "description": description})
    except Exception as e:
        logger.warning(f"[MultimodalAnalyze] Cloud LLM failed for {main_shortcode}: {e}")

    if not results:
        return {
            "status": "error",
            "error": "Cloud LLM unreachable or returned no results",
            "recoverable": True,
            "error_type": "provider_unavailable",
        }

    return {
        "status": "success",
        "analyzed_count": len(results),
        "model_id": model_name,
        "provider": provider_name,
        "results": results,
    }


def _get_db_provider(model_name: str) -> Optional[str]:
    from ....services.model_config_store import ModelConfigStore
    from ....models.model_provider import ModelType
    try:
        models = ModelConfigStore().get_all_models(model_type=ModelType.MULTIMODAL, enabled=True)
        for m in models:
            if m.model_name == model_name:
                return m.provider_name
    except Exception:
        pass
    return None
