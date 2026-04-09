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
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Local OpenAI-compatible VLM endpoints may only handle one heavy vision call at a time.
_MLX_SEMAPHORE = asyncio.Semaphore(1)
_WATCHDOG_STATE_DIR = Path(
    os.getenv("MULTIMODAL_WATCHDOG_STATE_DIR", "/app/logs/mlx-watchdog")
)
_WATCHDOG_STATE_FILE = _WATCHDOG_STATE_DIR / "inflight_request.json"
_WATCHDOG_HEARTBEAT_INTERVAL_SECONDS = max(
    1.0,
    float(os.getenv("MULTIMODAL_WATCHDOG_HEARTBEAT_INTERVAL_SECONDS", "15")),
)
_MLX_CONNECT_TIMEOUT_SECONDS = max(
    1.0,
    float(os.getenv("MULTIMODAL_MLX_CONNECT_TIMEOUT_SECONDS", "5")),
)
# Legacy MLX path still uses a bounded read timeout. When server-side progress
# watchdog is enabled, read timeout defaults to disabled so the host watchdog
# becomes the single source of truth for whether an inference is still making
# forward progress or should be killed.
_MLX_READ_TIMEOUT_SECONDS = max(
    30.0,
    float(os.getenv("MULTIMODAL_MLX_READ_TIMEOUT_SECONDS", "780")),
)
_MLX_WRITE_TIMEOUT_SECONDS = max(
    5.0,
    float(os.getenv("MULTIMODAL_MLX_WRITE_TIMEOUT_SECONDS", "30")),
)
_MLX_POOL_TIMEOUT_SECONDS = max(
    5.0,
    float(os.getenv("MULTIMODAL_MLX_POOL_TIMEOUT_SECONDS", "30")),
)
_MLX_RECOVERY_READY_TIMEOUT_SECONDS = max(
    30.0,
    float(os.getenv("MULTIMODAL_MLX_RECOVERY_READY_TIMEOUT_SECONDS", "240")),
)
_MLX_RECOVERY_READY_POLL_SECONDS = max(
    1.0,
    float(os.getenv("MULTIMODAL_MLX_RECOVERY_READY_POLL_SECONDS", "5")),
)
_MLX_RECOVERY_MAX_ATTEMPTS = max(
    0,
    int(os.getenv("MULTIMODAL_MLX_RECOVERY_MAX_ATTEMPTS", "1")),
)
_MLX_WARMUP_MAX_TOKENS = max(
    8,
    int(os.getenv("MULTIMODAL_MLX_WARMUP_MAX_TOKENS", "16")),
)


def _mlx_server_progress_enabled() -> bool:
    return os.getenv(
        "MULTIMODAL_MLX_SERVER_PROGRESS_ENABLED",
        "1",
    ).strip().lower() not in {"0", "false", "no", "off"}


def _optional_timeout_seconds(env_name: str) -> Optional[float]:
    raw = (os.getenv(env_name) or "").strip()
    if not raw:
        return None
    try:
        parsed = float(raw)
    except ValueError:
        logger.warning(
            "[MultimodalAnalyze] Invalid %s=%r; ignoring optional timeout override",
            env_name,
            raw,
        )
        return None
    if parsed <= 0:
        return None
    return max(1.0, parsed)


_MLX_PROGRESS_READ_TIMEOUT_SECONDS = _optional_timeout_seconds(
    "MULTIMODAL_MLX_PROGRESS_READ_TIMEOUT_SECONDS"
)


def _mlx_effective_read_timeout_seconds(*, server_progress_enabled: bool) -> Optional[float]:
    if server_progress_enabled:
        return _MLX_PROGRESS_READ_TIMEOUT_SECONDS
    return _MLX_READ_TIMEOUT_SECONDS


def _build_mlx_http_timeout(httpx_module: Any, *, server_progress_enabled: bool):
    return httpx_module.Timeout(
        connect=_MLX_CONNECT_TIMEOUT_SECONDS,
        read=_mlx_effective_read_timeout_seconds(
            server_progress_enabled=server_progress_enabled
        ),
        write=_MLX_WRITE_TIMEOUT_SECONDS,
        pool=_MLX_POOL_TIMEOUT_SECONDS,
    )


def _base64_size_bytes(b64_text: str) -> int:
    """Estimate decoded byte length from base64 text without decoding payload."""
    text = (b64_text or "").strip()
    if not text:
        return 0
    padding = text[-2:].count("=")
    return max(0, (len(text) * 3) // 4 - padding)


def _image_payload_stats(images: List[Dict[str, Any]]) -> Dict[str, int]:
    """Summarize image payload count and approximate decoded bytes."""
    payload_images = [
        item for item in (images or [])
        if isinstance(item, dict) and item.get("base64_jpeg")
    ]
    return {
        "image_payload_count": len(payload_images),
        "image_payload_total_bytes": sum(
            _base64_size_bytes(item.get("base64_jpeg", "")) for item in payload_images
        ),
    }


def _write_watchdog_state(payload: Dict[str, Any]) -> None:
    """Persist current active multimodal request for the host-side MLX watchdog."""
    try:
        _WATCHDOG_STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp_path = _WATCHDOG_STATE_FILE.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
        tmp_path.replace(_WATCHDOG_STATE_FILE)
    except Exception as exc:
        logger.warning("[MultimodalAnalyze] Failed to write watchdog state: %s", exc)


async def _write_watchdog_state_async(payload: Dict[str, Any]) -> None:
    await asyncio.to_thread(_write_watchdog_state, payload)


def _clear_watchdog_state(request_id: str) -> None:
    """Clear active request sentinel if it still belongs to the same request."""
    try:
        if not _WATCHDOG_STATE_FILE.exists():
            return
        data = json.loads(_WATCHDOG_STATE_FILE.read_text(encoding="utf-8"))
        if request_id and str(data.get("request_id") or "") != request_id:
            return
        _WATCHDOG_STATE_FILE.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("[MultimodalAnalyze] Failed to clear watchdog state: %s", exc)


async def _clear_watchdog_state_async(request_id: str) -> None:
    await asyncio.to_thread(_clear_watchdog_state, request_id)


def _should_preserve_watchdog_state_on_error(exc: BaseException) -> bool:
    try:
        import httpx
    except Exception:
        return False
    return isinstance(exc, httpx.TimeoutException)


async def _watchdog_heartbeat_loop(
    *,
    request_id: str,
    reference_id: str,
    analysis_profile: str,
    model_name: str,
    payload_stats: Dict[str, int],
    stop_event: asyncio.Event,
    started_at_epoch: float,
) -> None:
    """Refresh active request heartbeat while MLX is processing a request."""
    while True:
        payload = {
            "status": "active",
            "request_id": request_id,
            "reference_id": reference_id,
            "analysis_profile": analysis_profile,
            "model_id": model_name,
            "started_at_epoch": started_at_epoch,
            "heartbeat_at_epoch": time.time(),
            "image_payload_count": int(payload_stats.get("image_payload_count", 0)),
            "image_payload_total_bytes": int(payload_stats.get("image_payload_total_bytes", 0)),
        }
        await _write_watchdog_state_async(payload)
        try:
            await asyncio.wait_for(
                stop_event.wait(),
                timeout=_WATCHDOG_HEARTBEAT_INTERVAL_SECONDS,
            )
            break
        except asyncio.TimeoutError:
            continue


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


def _coerce_openai_message_text(value: Any) -> str:
    """Best-effort extraction for OpenAI-style message content variants."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: List[str] = []
        for item in value:
            text = _coerce_openai_message_text(item)
            if text:
                parts.append(text)
        return "\n".join(parts).strip()
    if isinstance(value, dict):
        for key in ("text", "content", "value", "output_text"):
            text = _coerce_openai_message_text(value.get(key))
            if text:
                return text
        return ""
    return str(value).strip()


def _normalize_reasoning_trace_mode(value: Any) -> str:
    text = str(value or "suppress").strip().lower()
    return "capture" if text == "capture" else "suppress"


def _normalize_requested_max_tokens(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _build_mlx_system_message(trace_mode: str) -> str:
    base = (
        "You are a vision analysis API. "
        "Return a single valid JSON object only. "
        "Do not emit markdown fences."
    )
    if trace_mode == "capture":
        return (
            base
            + " If auxiliary reasoning is emitted, keep it terse and evidence-focused. "
            + " Do not narrate validation, field mapping, corrections, or repeated checks. "
            + ' Never output phrases like "Thinking Process", "Field Mapping", "Correction on", or "One more check". '
            + "Do not place prose before the JSON object in visible output. "
            + "Start with '{' immediately."
        )
    return (
        "/no_think\n"
        + base
        + " No thinking, no explanation. Start with '{' immediately."
    )


def _finalize_multimodal_result(
    result: Dict[str, Any],
    *,
    request_id: str,
    reference_id: str,
    analysis_profile: str,
    payload_stats: Dict[str, int],
    provider_name: str,
    reasoning_trace_mode: str,
) -> Dict[str, Any]:
    if not isinstance(result, dict):
        return result

    result.setdefault("request_id", request_id)
    telemetry = dict(result.get("_telemetry") or {})
    telemetry.setdefault("request_id", request_id)
    telemetry.setdefault("reference_id", reference_id)
    telemetry.setdefault("analysis_profile", analysis_profile)
    telemetry.setdefault("image_payload_count", payload_stats.get("image_payload_count", 0))
    telemetry.setdefault(
        "image_payload_total_bytes",
        payload_stats.get("image_payload_total_bytes", 0),
    )
    telemetry.setdefault("provider", result.get("provider", provider_name))
    telemetry.setdefault("reasoning_trace_mode", reasoning_trace_mode)
    result["_telemetry"] = telemetry
    return result


def _looks_like_capture_reasoning_leak(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    if re.search(r"(?im)^\s*thinking process\s*:", normalized):
        return True
    if len(re.findall(r"(?i)\bone more check\b", normalized)) >= 2:
        return True
    if len(re.findall(r"(?i)\bcorrection on\b", normalized)) >= 2:
        return True
    if "JSON Structure Check" in normalized or "Field Mapping" in normalized:
        return True
    return False


def _looks_like_mlx_disconnect(exc: BaseException) -> bool:
    text = str(exc).lower()
    return (
        "server disconnected without sending a response" in text
        or "remoteprotocolerror" in text
        or "connection reset" in text
        or "broken pipe" in text
    )


async def _wait_for_mlx_server_ready(
    client: Any,
    *,
    base_url: str,
    request_id: str,
    reference_id: str,
    analysis_profile: str,
) -> bool:
    import httpx

    probe_url = f"{base_url}/v1/models"
    deadline = time.monotonic() + _MLX_RECOVERY_READY_TIMEOUT_SECONDS
    last_exc: Optional[BaseException] = None
    attempt = 0
    while time.monotonic() < deadline:
        attempt += 1
        try:
            resp = await client.get(
                probe_url,
                timeout=httpx.Timeout(connect=5.0, read=5.0, write=5.0, pool=5.0),
            )
            resp.raise_for_status()
            logger.info(
                "[MultimodalAnalyze] MLX ready probe succeeded request_id=%s reference_id=%s profile=%s attempt=%d",
                request_id,
                reference_id,
                analysis_profile,
                attempt,
            )
            return True
        except Exception as exc:
            last_exc = exc
            await asyncio.sleep(_MLX_RECOVERY_READY_POLL_SECONDS)
    logger.warning(
        "[MultimodalAnalyze] MLX ready probe timed out request_id=%s reference_id=%s profile=%s last_error=%s",
        request_id,
        reference_id,
        analysis_profile,
        last_exc,
    )
    return False


async def _mlx_warmup_request(
    client: Any,
    *,
    base_url: str,
    model_name: str,
    request_id: str,
    reference_id: str,
    analysis_profile: str,
) -> None:
    warmup_request_id = f"{request_id}_warmup"
    warmup_headers = {
        "X-MLX-Request-Id": warmup_request_id,
        "X-MLX-Reference-Id": reference_id,
        "X-MLX-Analysis-Profile": f"{analysis_profile}_warmup",
        "X-MLX-Model-Id": model_name,
        "X-MLX-Image-Payload-Count": "0",
        "X-MLX-Image-Payload-Bytes": "0",
    }
    try:
        resp = await client.post(
            f"{base_url}/v1/chat/completions",
            headers=warmup_headers,
            json={
                "model": model_name,
                "messages": [
                    {
                        "role": "system",
                        "content": "Return only a compact JSON object.",
                    },
                    {
                        "role": "user",
                        "content": "Respond with {\"warm\":true}.",
                    },
                ],
                "temperature": 0.0,
                "max_tokens": _MLX_WARMUP_MAX_TOKENS,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        logger.info(
            "[MultimodalAnalyze] MLX warmup request succeeded request_id=%s reference_id=%s profile=%s",
            request_id,
            reference_id,
            analysis_profile,
        )
    finally:
        await _clear_watchdog_state_async(warmup_request_id)


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

    first_image = images[0] if images and isinstance(images[0], dict) else {}
    request_id = str(
        kwargs.get("request_id")
        or first_image.get("request_id")
        or f"vlm_{uuid.uuid4().hex[:12]}"
    )
    reference_id = str(
        kwargs.get("reference_id")
        or first_image.get("reference_id")
        or ""
    )
    analysis_profile = str(
        kwargs.get("analysis_profile")
        or first_image.get("analysis_profile")
        or "unknown"
    )
    reasoning_trace_mode = _normalize_reasoning_trace_mode(
        kwargs.get("reasoning_trace_mode")
    )
    requested_max_tokens = _normalize_requested_max_tokens(kwargs.get("max_tokens"))
    payload_stats = _image_payload_stats(images)

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
        "[MultimodalAnalyze] Resolved model=%s, provider=%s request_id=%s reference_id=%s profile=%s payload_images=%d payload_bytes=%d",
        model_name,
        provider_name,
        request_id,
        reference_id,
        analysis_profile,
        payload_stats["image_payload_count"],
        payload_stats["image_payload_total_bytes"],
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
            
        result = await _route_cloud_llm(
            images,
            prompt,
            model_name,
            "vertex-ai",
            temperature,
            workspace_id,
            max_tokens=requested_max_tokens,
            reasoning_trace_mode=reasoning_trace_mode,
        )
        return _finalize_multimodal_result(
            result,
            request_id=request_id,
            reference_id=reference_id,
            analysis_profile=analysis_profile,
            payload_stats=payload_stats,
            provider_name="vertex-ai",
            reasoning_trace_mode=reasoning_trace_mode,
        )

    elif provider_name == "openai" or provider_name == "anthropic":
        # Resolve temperature default from DB if not provided
        if temperature is None:
            m = store.get_model_by_name(model_name)
            if m and m.metadata and "temperature" in m.metadata:
                temperature = float(m.metadata["temperature"])
        if temperature is None:
            temperature = 0.4
            
        result = await _route_cloud_llm(
            images,
            prompt,
            model_name,
            provider_name,
            temperature,
            workspace_id,
            max_tokens=requested_max_tokens,
            reasoning_trace_mode=reasoning_trace_mode,
        )
        return _finalize_multimodal_result(
            result,
            request_id=request_id,
            reference_id=reference_id,
            analysis_profile=analysis_profile,
            payload_stats=payload_stats,
            provider_name=provider_name,
            reasoning_trace_mode=reasoning_trace_mode,
        )

    elif provider_name == "mlx":
        if temperature is None:
            m = store.get_model_by_name(model_name)
            if m and m.metadata and "temperature" in m.metadata:
                temperature = float(m.metadata["temperature"])
        if temperature is None:
            temperature = 0.6

        result = await _route_mlx_server(
            images,
            prompt,
            model_name,
            temperature,
            request_id=request_id,
            reference_id=reference_id,
            analysis_profile=analysis_profile,
            payload_stats=payload_stats,
            max_tokens=requested_max_tokens,
            reasoning_trace_mode=reasoning_trace_mode,
        )
        return _finalize_multimodal_result(
            result,
            request_id=request_id,
            reference_id=reference_id,
            analysis_profile=analysis_profile,
            payload_stats=payload_stats,
            provider_name="mlx",
            reasoning_trace_mode=reasoning_trace_mode,
        )

    elif provider_name == "huggingface":
        if temperature is None:
            m = store.get_model_by_name(model_name)
            if m and m.metadata and "temperature" in m.metadata:
                temperature = float(m.metadata["temperature"])
        if temperature is None:
            temperature = 0.6
            
        return await _route_huggingface(images, prompt, model_name, temperature)

    # Fallback for any other provider_name that might be passed
    result = await _route_cloud_llm(
        images,
        prompt,
        model_name,
        provider_name,
        temperature,
        workspace_id,
        max_tokens=requested_max_tokens,
        reasoning_trace_mode=reasoning_trace_mode,
    )
    return _finalize_multimodal_result(
        result,
        request_id=request_id,
        reference_id=reference_id,
        analysis_profile=analysis_profile,
        payload_stats=payload_stats,
        provider_name=provider_name,
        reasoning_trace_mode=reasoning_trace_mode,
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


def _resolve_multimodal_base_url_from_env() -> tuple[Optional[str], Optional[str]]:
    """Resolve multimodal endpoint base URL from environment aliases."""
    for env_name in ("VISION_MODEL_BASE_URL", "VLM_BASE_URL", "MLX_SERVER_HOST"):
        env_host = os.getenv(env_name)
        if env_host:
            return env_host.rstrip("/"), env_name
    return None, None


def _resolve_multimodal_base_url(model_name: str) -> str:
    """Resolve multimodal endpoint base URL from config.

    Priority:
      1. ModelConfig.metadata['base_url'] for the specific model
      2. 'huggingface_base_url' system setting (provider-level)
      3. VISION_MODEL_BASE_URL environment variable
      4. VLM_BASE_URL environment variable
      5. MLX_SERVER_HOST environment variable (legacy fallback)
      6. Fallback: http://host.docker.internal:8210
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
    env_host, env_name = _resolve_multimodal_base_url_from_env()
    if env_host:
        logger.info(
            "[MultimodalAnalyze] Resolved base_url from %s env: %s",
            env_name,
            env_host,
        )
        return env_host

    # Priority 6: Hardcoded fallback
    logger.info(
        "[MultimodalAnalyze] Using fallback multimodal base_url: %s", _FALLBACK
    )
    return _FALLBACK


async def _route_mlx_server(
    images: List[Dict[str, Any]],
    prompt: str,
    model_name: str,
    temperature: float,
    *,
    request_id: str,
    reference_id: str = "",
    analysis_profile: str = "unknown",
    payload_stats: Optional[Dict[str, int]] = None,
    max_tokens: Optional[int] = None,
    reasoning_trace_mode: str = "suppress",
) -> Dict[str, Any]:
    """Route to an OpenAI-compatible vision endpoint.

    Base URL resolution priority:
      1. Model metadata 'base_url' from model_configs DB table
      2. 'huggingface_base_url' system setting
      3. VISION_MODEL_BASE_URL environment variable
      4. VLM_BASE_URL environment variable
      5. MLX_SERVER_HOST environment variable
      6. Fallback: http://host.docker.internal:8210
    """
    import httpx

    base_url = _resolve_multimodal_base_url(model_name)
    url = f"{base_url}/v1/chat/completions"

    logger.info(
        "[MultimodalAnalyze] Routing to multimodal endpoint: %s (model=%s)",
        url, model_name,
    )

    results = []
    payload_stats = dict(payload_stats or {})
    clear_watchdog_state = True
    telemetry: Dict[str, Any] = {
        "request_id": request_id,
        "reference_id": reference_id,
        "analysis_profile": analysis_profile,
        "image_payload_count": payload_stats.get("image_payload_count", 0),
        "image_payload_total_bytes": payload_stats.get("image_payload_total_bytes", 0),
        "queue_wait_ms": 0.0,
        "mlx_post_ms": 0.0,
        "response_chars": 0,
        "resolved_max_tokens": 0,
        "model_id": model_name,
    }
    
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
            "content": _build_mlx_system_message(reasoning_trace_mode),
        },
        {
            "role": "user",
            "content": content,
        }
    ]

    use_server_progress = _mlx_server_progress_enabled()
    telemetry["mlx_read_timeout_seconds"] = _mlx_effective_read_timeout_seconds(
        server_progress_enabled=use_server_progress
    )

    async def _post_completion(client: Any) -> Any:
        return await client.post(
            url,
            headers=request_headers or None,
            json={
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": resolved_max,
                "response_format": {"type": "json_object"},
            },
        )

    async with httpx.AsyncClient(
        timeout=_build_mlx_http_timeout(
            httpx,
            server_progress_enabled=use_server_progress,
        )
    ) as client:
        try:
            from ....shared.inference_config import InferenceConfig
            resolved_max = InferenceConfig.get_max_tokens(
                model_name,
                caller_default=max_tokens if max_tokens is not None else 12288,
            )
            
            first_b64 = images[0].get("base64_jpeg", "")
            mime = _detect_image_mime(first_b64) if first_b64 else "unknown"
            logger.info(
                "[VLM] MIME=%s max_tokens=%d model=%s",
                mime,
                resolved_max,
                model_name,
            )
            telemetry["resolved_max_tokens"] = resolved_max

            # Acquire semaphore so only one local VLM inference runs at a time.
            queue_wait_started = time.perf_counter()
            async with _MLX_SEMAPHORE:
                telemetry["queue_wait_ms"] = round(
                    (time.perf_counter() - queue_wait_started) * 1000.0,
                    3,
                )
                logger.info(
                    "[MultimodalAnalyze] Multimodal endpoint semaphore acquired request_id=%s shortcode=%s reference_id=%s profile=%s with %d images after %.2fms read_timeout=%s progress_watchdog=%s",
                    request_id,
                    main_shortcode,
                    reference_id,
                    analysis_profile,
                    len(content) - 1,
                    telemetry["queue_wait_ms"],
                    "none"
                    if telemetry["mlx_read_timeout_seconds"] is None
                    else telemetry["mlx_read_timeout_seconds"],
                    use_server_progress,
                )
                heartbeat_stop: Optional[asyncio.Event] = None
                heartbeat_task: Optional[asyncio.Task] = None
                request_headers: Dict[str, str] = {}
                if use_server_progress:
                    request_headers = {
                        "X-MLX-Request-Id": request_id,
                        "X-MLX-Reference-Id": reference_id,
                        "X-MLX-Analysis-Profile": analysis_profile,
                        "X-MLX-Model-Id": model_name,
                        "X-MLX-Image-Payload-Count": str(
                            payload_stats.get("image_payload_count", 0)
                        ),
                        "X-MLX-Image-Payload-Bytes": str(
                            payload_stats.get("image_payload_total_bytes", 0)
                        ),
                    }
                    logger.info(
                        "[MultimodalAnalyze] Using MLX server-side progress watchdog request_id=%s reference_id=%s profile=%s",
                        request_id,
                        reference_id,
                        analysis_profile,
                    )
                else:
                    heartbeat_stop = asyncio.Event()
                    heartbeat_started_at_epoch = time.time()
                    heartbeat_task = asyncio.create_task(
                        _watchdog_heartbeat_loop(
                            request_id=request_id,
                            reference_id=reference_id,
                            analysis_profile=analysis_profile,
                            model_name=model_name,
                            payload_stats=payload_stats,
                            stop_event=heartbeat_stop,
                            started_at_epoch=heartbeat_started_at_epoch,
                        )
                    )
                try:
                    mlx_post_started = time.perf_counter()
                    last_exc: Optional[BaseException] = None
                    resp = None
                    for recovery_attempt in range(_MLX_RECOVERY_MAX_ATTEMPTS + 1):
                        try:
                            resp = await _post_completion(client)
                            break
                        except Exception as exc:
                            last_exc = exc
                            if _should_preserve_watchdog_state_on_error(exc):
                                clear_watchdog_state = False
                                logger.warning(
                                    "[MultimodalAnalyze] Preserving watchdog state after MLX timeout request_id=%s reference_id=%s profile=%s",
                                    request_id,
                                    reference_id,
                                    analysis_profile,
                                )
                            if (
                                recovery_attempt >= _MLX_RECOVERY_MAX_ATTEMPTS
                                or not _looks_like_mlx_disconnect(exc)
                            ):
                                raise
                            logger.warning(
                                "[MultimodalAnalyze] MLX disconnected during inference request_id=%s reference_id=%s profile=%s recovery_attempt=%d/%d",
                                request_id,
                                reference_id,
                                analysis_profile,
                                recovery_attempt + 1,
                                _MLX_RECOVERY_MAX_ATTEMPTS,
                            )
                            ready = await _wait_for_mlx_server_ready(
                                client,
                                base_url=base_url,
                                request_id=request_id,
                                reference_id=reference_id,
                                analysis_profile=analysis_profile,
                            )
                            if not ready:
                                raise exc
                            try:
                                await _mlx_warmup_request(
                                    client,
                                    base_url=base_url,
                                    model_name=model_name,
                                    request_id=request_id,
                                    reference_id=reference_id,
                                    analysis_profile=analysis_profile,
                                )
                            except Exception as warmup_exc:
                                last_exc = warmup_exc
                                if recovery_attempt >= _MLX_RECOVERY_MAX_ATTEMPTS:
                                    raise
                                logger.warning(
                                    "[MultimodalAnalyze] MLX warmup failed request_id=%s reference_id=%s profile=%s recovery_attempt=%d/%d error=%s",
                                    request_id,
                                    reference_id,
                                    analysis_profile,
                                    recovery_attempt + 1,
                                    _MLX_RECOVERY_MAX_ATTEMPTS,
                                    warmup_exc,
                                )
                                continue
                    if resp is None and last_exc is not None:
                        raise last_exc
                    telemetry["mlx_post_ms"] = round(
                        (time.perf_counter() - mlx_post_started) * 1000.0,
                        3,
                    )
                finally:
                    try:
                        if heartbeat_stop is not None:
                            heartbeat_stop.set()
                        if heartbeat_task is not None:
                            await heartbeat_task
                    finally:
                        if clear_watchdog_state:
                            await _clear_watchdog_state_async(request_id)
            
            resp.raise_for_status()
            data = resp.json()
            choices = data.get("choices") if isinstance(data, dict) else None
            first_choice = choices[0] if isinstance(choices, list) and choices else {}
            msg = first_choice.get("message") if isinstance(first_choice, dict) else {}
            finish_reason = ""
            if isinstance(first_choice, dict):
                finish_reason = str(first_choice.get("finish_reason") or "").strip()
            if not finish_reason and isinstance(data, dict):
                finish_reason = str(data.get("finish_reason") or "").strip()

            # Prefer content over reasoning; when both exist,
            # pick whichever looks like JSON (starts with '{').
            resp_content = _coerce_openai_message_text(
                msg.get("content") if isinstance(msg, dict) else None
            )
            reasoning = _coerce_openai_message_text(
                (
                    msg.get("reasoning")
                    if isinstance(msg, dict)
                    else None
                )
                or (
                    msg.get("reasoning_content")
                    if isinstance(msg, dict)
                    else None
                )
                or (
                    first_choice.get("text")
                    if isinstance(first_choice, dict)
                    else None
                )
                or (
                    data.get("output_text")
                    if isinstance(data, dict)
                    else None
                )
            )
            chosen_source = ""
            if resp_content and resp_content.lstrip().startswith("{"):
                text = resp_content
                chosen_source = "content"
            elif reasoning and reasoning.lstrip().startswith("{"):
                text = reasoning
                chosen_source = "reasoning"
            else:
                text = resp_content or reasoning
                chosen_source = "content" if resp_content else "reasoning"
            capture_leak_non_json = bool(
                reasoning_trace_mode == "capture"
                and text
                and not text.lstrip().startswith("{")
                and _looks_like_capture_reasoning_leak(text)
            )
            if capture_leak_non_json:
                chosen_source = "capture_leak_non_json"
                
            if text:
                telemetry["response_chars"] = len(text)
                telemetry["finish_reason"] = finish_reason
                telemetry["response_source"] = chosen_source
                result_telemetry = {
                    "provider": "mlx",
                    "request_id": request_id,
                    "finish_reason": finish_reason,
                    "reasoning_trace_mode": reasoning_trace_mode,
                    "response_source": chosen_source,
                }
                result_item: Dict[str, Any] = {
                    "shortcode": main_shortcode,
                    "description": text,
                    "_telemetry": result_telemetry,
                }
                if reasoning_trace_mode == "capture":
                    if chosen_source == "content" and reasoning and reasoning != text:
                        result_item["thinking"] = reasoning
                    elif chosen_source == "reasoning" and resp_content and resp_content != text:
                        result_item["thinking"] = resp_content
                results.append(result_item)
                logger.info(
                    "[MultimodalAnalyze][Perf] request_id=%s shortcode=%s reference_id=%s profile=%s payload_images=%d payload_bytes=%d queue_wait_ms=%.2f mlx_post_ms=%.2f response_chars=%d max_tokens=%d",
                    request_id,
                    main_shortcode,
                    reference_id,
                    analysis_profile,
                    telemetry["image_payload_count"],
                    telemetry["image_payload_total_bytes"],
                    telemetry["queue_wait_ms"],
                    telemetry["mlx_post_ms"],
                    telemetry["response_chars"],
                    telemetry["resolved_max_tokens"],
                )
            else:
                logger.warning(
                    "[MultimodalAnalyze] Empty MLX response payload request_id=%s shortcode=%s reference_id=%s profile=%s choices_type=%s choices_count=%s",
                    request_id,
                    main_shortcode,
                    reference_id,
                    analysis_profile,
                    type(choices).__name__,
                    len(choices) if isinstance(choices, list) else -1,
                )
        except Exception as e:
            logger.warning(
                "[MultimodalAnalyze] Multimodal endpoint call failed request_id=%s shortcode=%s reference_id=%s profile=%s: %s",
                request_id,
                main_shortcode,
                reference_id,
                analysis_profile,
                e,
            )

    if not results:
        return {
            "status": "error",
            "error": "Multimodal endpoint unreachable or returned no results",
            "recoverable": True,
            "error_type": "provider_unavailable",
        }

    return {
        "status": "success",
        "analyzed_count": len(results),
        "model_id": model_name,
        "provider": "mlx",
        "request_id": request_id,
        "results": results,
        "_telemetry": telemetry,
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
    *,
    max_tokens: Optional[int] = None,
    reasoning_trace_mode: str = "suppress",
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
            max_tokens=max_tokens,
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
        "_telemetry": {
            "provider": provider_name,
            "reasoning_trace_mode": (
                "capture_unsupported_provider"
                if reasoning_trace_mode == "capture"
                else "suppress"
            ),
        },
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
