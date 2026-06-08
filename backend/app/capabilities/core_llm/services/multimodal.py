"""
Core LLM: Multimodal Analyze Service

Unified middleware for multimodal (vision) analysis.
Model selection is owned by model-routing-registry:
  profile_model_bindings.local.vision -> enabled multimodal model.
"""

import asyncio
import contextlib
import importlib
import importlib.util
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# Local OpenAI-compatible VLM endpoints may only handle one heavy vision call at a time.
_MLX_SEMAPHORE = asyncio.Semaphore(1)
_MLX_CONNECT_TIMEOUT_SECONDS = float(os.getenv("VLM_CONNECT_TIMEOUT_SECONDS", "30"))
_MLX_READ_TIMEOUT_SECONDS = float(os.getenv("VLM_READ_TIMEOUT_SECONDS", "2400"))
_MLX_PROGRESS_READ_TIMEOUT_SECONDS = (
    float(os.getenv("VLM_PROGRESS_READ_TIMEOUT_SECONDS"))
    if os.getenv("VLM_PROGRESS_READ_TIMEOUT_SECONDS")
    else None
)
_MLX_WRITE_TIMEOUT_SECONDS = float(os.getenv("VLM_WRITE_TIMEOUT_SECONDS", "120"))
_MLX_POOL_TIMEOUT_SECONDS = float(os.getenv("VLM_POOL_TIMEOUT_SECONDS", "30"))
_MLX_MAX_OUTPUT_TOKENS_CAP_DEFAULT = 12288
_WATCHDOG_STATE_DIR = Path(os.getenv("VLM_WATCHDOG_STATE_DIR", "/app/data/runtime/mlx-watchdog"))
_MLX_PROCESS_LOCK_FILE_OVERRIDE = os.getenv("VLM_PROCESS_LOCK_FILE")
_WATCHDOG_HEARTBEAT_INTERVAL_SECONDS = float(
    os.getenv("VLM_WATCHDOG_HEARTBEAT_INTERVAL_SECONDS", "5")
)
_WATCHDOG_CLIENT_TIMEOUT_GRACE_SECONDS = float(
    os.getenv("VLM_CLIENT_TIMEOUT_WATCHDOG_GRACE_SECONDS", "1200")
)


@dataclass
class _VlmProcessFileLock:
    path: Path
    fd: Any = None

    async def __aenter__(self):
        await asyncio.to_thread(self._acquire)
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await asyncio.to_thread(self._release)
        return False

    def _acquire(self) -> None:
        import fcntl

        lock_path = self.path
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            lock_path = Path(os.getenv("TMPDIR", "/tmp")) / "mindscape-vlm-provider.lock"
            lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = lock_path.open("a+")
        fcntl.flock(self.fd.fileno(), fcntl.LOCK_EX)

    def _release(self) -> None:
        if self.fd is None:
            return
        import fcntl

        try:
            fcntl.flock(self.fd.fileno(), fcntl.LOCK_UN)
        finally:
            self.fd.close()
            self.fd = None


def _coerce_positive_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return None
    return coerced if coerced > 0 else None


def _cap_local_vlm_max_tokens(
    value: int,
    *,
    route_metadata: Optional[Dict[str, Any]] = None,
) -> int:
    metadata = route_metadata or {}
    cap = (
        _coerce_positive_int(metadata.get("local_max_output_tokens_cap"))
        or _coerce_positive_int(metadata.get("max_output_tokens_cap"))
        or _coerce_positive_int(
            os.getenv(
                "VLM_MAX_OUTPUT_TOKENS_CAP",
                str(_MLX_MAX_OUTPUT_TOKENS_CAP_DEFAULT),
            )
        )
    )
    if cap is None or value <= cap:
        return value
    logger.warning(
        "[VLM] Capping local max_tokens from %d to %d for MLX stability",
        value,
        cap,
    )
    return cap


def _normalize_reasoning_trace_mode(value: Any) -> str:
    return "capture" if str(value or "").lower() == "capture" else "suppress"


def _looks_like_json_object(text: str) -> bool:
    return bool((text or "").lstrip().startswith("{"))


def _looks_like_visible_loop_prose(text: str) -> bool:
    lowered = (text or "").lower()
    return any(
        marker in lowered
        for marker in (
            "thinking process",
            "field mapping",
            "correction on",
            "one more check",
        )
    )


def _mlx_server_progress_enabled() -> bool:
    return os.getenv("VLM_PROGRESS_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _build_mlx_http_timeout(
    httpx_module: Any,
    *,
    server_progress_enabled: bool,
) -> Any:
    read_timeout = (
        _MLX_PROGRESS_READ_TIMEOUT_SECONDS
        if server_progress_enabled
        else _MLX_READ_TIMEOUT_SECONDS
    )
    return httpx_module.Timeout(
        connect=_MLX_CONNECT_TIMEOUT_SECONDS,
        read=read_timeout,
        write=_MLX_WRITE_TIMEOUT_SECONDS,
        pool=_MLX_POOL_TIMEOUT_SECONDS,
    )


def _should_preserve_watchdog_state_on_error(error: BaseException) -> bool:
    try:
        import httpx
    except Exception:
        httpx = None
    if httpx is not None and isinstance(error, httpx.ReadTimeout):
        return True
    return error.__class__.__name__ == "ReadTimeout"


def _safe_lane_slug(value: Any) -> str:
    normalized = str(value or "").strip() or "lane"
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "_", normalized).strip("_")
    return slug or "lane"


def _host_resource_lane_id(route_metadata: Optional[Dict[str, Any]] = None) -> str:
    metadata = route_metadata or {}
    return str(
        metadata.get("host_resource_lane_id")
        or os.getenv("LOCAL_CORE_HOST_RESOURCE_LANE_ID")
        or os.getenv("LOCAL_CORE_RUNNER_PROFILE")
        or ""
    ).strip()


def _watchdog_state_file(route_metadata: Optional[Dict[str, Any]] = None) -> Path:
    metadata = route_metadata or {}
    explicit = str(
        metadata.get("vlm_watchdog_state_file")
        or os.getenv("VLM_WATCHDOG_STATE_FILE")
        or ""
    ).strip()
    if explicit:
        return Path(explicit)
    lane_id = _host_resource_lane_id(metadata)
    if lane_id:
        return _WATCHDOG_STATE_DIR / f"{_safe_lane_slug(lane_id)}.json"
    return _WATCHDOG_STATE_DIR / "inflight_request.json"


def _mlx_process_lock_file(route_metadata: Optional[Dict[str, Any]] = None) -> Path:
    metadata = route_metadata or {}
    explicit = str(metadata.get("vlm_process_lock_file") or "").strip()
    if explicit:
        return Path(explicit)
    if _MLX_PROCESS_LOCK_FILE_OVERRIDE:
        return Path(_MLX_PROCESS_LOCK_FILE_OVERRIDE)
    lane_id = _host_resource_lane_id(metadata)
    if lane_id:
        return _WATCHDOG_STATE_DIR / f"{_safe_lane_slug(lane_id)}.lock"
    return _WATCHDOG_STATE_DIR / "mlx_provider.lock"


def _write_watchdog_state(payload: Dict[str, Any], state_file: Path) -> None:
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = state_file.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        tmp_path.replace(state_file)
    except Exception as exc:
        logger.debug("[MultimodalAnalyze] Failed to write watchdog state: %s", exc)


def _clear_watchdog_state(state_file: Path) -> None:
    try:
        state_file.unlink()
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.debug("[MultimodalAnalyze] Failed to clear watchdog state: %s", exc)


def _preserve_watchdog_state_for_client_timeout(payload: Dict[str, Any], state_file: Path) -> None:
    timeout_at = time.time()
    timeout_payload = dict(payload)
    timeout_payload.update(
        {
            "status": "active",
            "phase": "client_timeout_grace",
            "heartbeat_at": timeout_at,
            "client_timeout_at": timeout_at,
            "grace_until": timeout_at + _WATCHDOG_CLIENT_TIMEOUT_GRACE_SECONDS,
        }
    )
    _write_watchdog_state(timeout_payload, state_file)


async def _watchdog_heartbeat(payload: Dict[str, Any], state_file: Path) -> None:
    while True:
        await asyncio.sleep(_WATCHDOG_HEARTBEAT_INTERVAL_SECONDS)
        heartbeat_payload = dict(payload)
        heartbeat_payload["heartbeat_at"] = time.time()
        _write_watchdog_state(heartbeat_payload, state_file)


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
    max_tokens: Optional[int] = None,
    **kwargs,  # absorb extra playbook inputs (profile_id, etc.)
) -> Dict[str, Any]:
    """
    Unified multimodal analysis — routes to cloud or local model.

    Routing authority:
      model-routing-registry profile binding `local.vision`.

    Args:
        images: List of dicts with 'shortcode' and 'base64_jpeg' keys.
        prompt: Text prompt for the analysis.
        temperature: Sampling temperature.
        workspace_id: Optional workspace context.
        workspace_id: Optional workspace context.

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

    first_image = images[0] if isinstance(images, list) and images else {}
    request_id = (
        kwargs.get("request_id")
        or first_image.get("request_id")
        or ""
    )
    reference_id = (
        kwargs.get("reference_id")
        or first_image.get("reference_id")
        or first_image.get("shortcode")
        or ""
    )
    analysis_profile = (
        kwargs.get("analysis_profile")
        or first_image.get("analysis_profile")
        or ""
    )
    payload_stats = (
        kwargs.get("payload_stats")
        or first_image.get("payload_stats")
        or {}
    )
    reasoning_trace_mode = (
        kwargs.get("reasoning_trace_mode")
        or first_image.get("reasoning_trace_mode")
        or "suppress"
    )
    requested_max_tokens = _coerce_positive_int(
        max_tokens
        if max_tokens is not None
        else kwargs.get("max_tokens", first_image.get("max_tokens"))
    )

    # ── Resolve model ──
    model_name, provider_name, route_metadata = _resolve_vision_route()
    
    if not model_name or not provider_name:
        return {
            "status": "error",
            "error": "No vision model configured or available",
            "recoverable": True,
            "error_type": "provider_unavailable"
        }

    logger.info(
        "[MultimodalAnalyze] Resolved registry model=%s provider=%s",
        model_name,
        provider_name,
    )

    # Route request to specific provider
    if provider_name == "vertex-ai":
        return await _route_cloud_llm(
            images,
            prompt,
            model_name,
            "vertex-ai",
            temperature,
            workspace_id,
            max_tokens=requested_max_tokens,
        )

    elif provider_name == "openai" or provider_name == "anthropic":
        return await _route_cloud_llm(
            images,
            prompt,
            model_name,
            provider_name,
            temperature,
            workspace_id,
            max_tokens=requested_max_tokens,
        )

    elif provider_name == "mlx":
        return await _route_mlx_server(
            images,
            prompt,
            model_name,
            temperature,
            base_url=_resolve_multimodal_base_url(route_metadata),
            route_metadata=route_metadata,
            request_id=request_id,
            reference_id=reference_id,
            analysis_profile=analysis_profile,
            payload_stats=payload_stats,
            reasoning_trace_mode=reasoning_trace_mode,
            max_tokens=requested_max_tokens,
        )

    elif provider_name == "huggingface":
        return await _route_huggingface(
            images,
            prompt,
            model_name,
            temperature,
            max_tokens=requested_max_tokens,
        )

    raise ValueError(
        f"Unsupported multimodal provider '{provider_name}' in model-routing-registry"
    )


def _resolve_vision_route() -> tuple[str, str, Dict[str, Any]]:
    """Resolve the vision model through model-routing-registry only."""
    from ....models.model_provider import ModelType
    from ....services.model_routing_policy_service import ModelRoutingPolicyService

    route = ModelRoutingPolicyService().resolve_profile_model(
        profile="vision",
        scope="local",
        model_type=ModelType.MULTIMODAL,
    )
    if not route.model_name or not route.provider:
        raise ValueError(
            "Vision model route is not configured in "
            "model-routing-registry profile_model_bindings.local.vision"
        )
    logger.info(
        "[MultimodalAnalyze] Registry route source=%s model=%s provider=%s",
        route.source,
        route.model_name,
        route.provider,
    )
    metadata = dict(route.metadata or {})
    return (
        route.model_name,
        _resolve_multimodal_runtime_provider(route.provider, metadata),
        metadata,
    )


def _resolve_multimodal_runtime_provider(provider: str, metadata: Dict[str, Any]) -> str:
    """Normalize source-provider metadata to the concrete multimodal runtime."""
    normalized_provider = str(provider or "").strip()
    runtime_provider = str(
        (metadata or {}).get("runtime_provider")
        or (metadata or {}).get("runtime_engine")
        or (metadata or {}).get("inference_provider")
        or ""
    ).strip()
    if runtime_provider and runtime_provider != "auto":
        return runtime_provider

    hf_format = str((metadata or {}).get("hf_format") or "").strip().lower()
    hf_tags = [
        str(tag or "").strip().lower()
        for tag in ((metadata or {}).get("hf_tags") or [])
        if str(tag or "").strip()
    ]
    if normalized_provider == "huggingface" and (
        hf_format == "mlx" or "mlx" in hf_tags
    ):
        return "mlx"

    return normalized_provider


def _resolve_multimodal_base_url(route_metadata: Dict[str, Any]) -> str:
    """Resolve the local multimodal endpoint from the selected registry model."""
    metadata = route_metadata or {}
    base_url = str(
        metadata.get("base_url")
        or metadata.get("endpoint_url")
        or metadata.get("openai_base_url")
        or metadata.get("api_base")
        or metadata.get("server_url")
        or ""
    ).strip()
    if not base_url:
        raise ValueError(
            "MLX multimodal route requires model metadata.base_url "
            "(or endpoint_url/openai_base_url/api_base/server_url) in "
            "model-routing-registry"
        )
    return base_url.rstrip("/")


async def _route_mlx_server(
    images: List[Dict[str, Any]],
    prompt: str,
    model_name: str,
    temperature: float,
    *,
    base_url: Optional[str] = None,
    route_metadata: Optional[Dict[str, Any]] = None,
    request_id: str = "",
    reference_id: str = "",
    analysis_profile: str = "",
    payload_stats: Optional[Dict[str, Any]] = None,
    reasoning_trace_mode: str = "suppress",
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Route to the OpenAI-compatible vision endpoint selected by registry."""
    import httpx

    if not base_url:
        base_url = _resolve_multimodal_base_url(route_metadata or {})
    url = f"{base_url}/v1/chat/completions"
    reasoning_trace_mode = _normalize_reasoning_trace_mode(reasoning_trace_mode)
    payload_stats = payload_stats or {}

    logger.info(
        "[MultimodalAnalyze] Routing to multimodal endpoint: %s (model=%s)",
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
    if not reference_id:
        reference_id = main_shortcode
    
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

    system_prompt = (
        "You are a vision analysis API. "
        "Output ONLY the raw JSON object. "
        "No explanation, no markdown. "
        "Start your response with '{' immediately."
    )
    if reasoning_trace_mode == "capture":
        system_prompt = (
            f"{system_prompt} "
            'Never output phrases like "Thinking Process", "Field Mapping", '
            '"Correction on", or "One more check".'
        )
    else:
        system_prompt = f"/no_think\n{system_prompt} No thinking."

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": content,
        }
    ]

    server_progress_enabled = _mlx_server_progress_enabled()
    timeout = _build_mlx_http_timeout(
        httpx,
        server_progress_enabled=server_progress_enabled,
    )
    watchdog_state_file = _watchdog_state_file(route_metadata)
    process_lock_file = _mlx_process_lock_file(route_metadata)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            from ....shared.inference_config import InferenceConfig
            requested_max_tokens = _coerce_positive_int(max_tokens)
            resolved_max = InferenceConfig.get_max_tokens(
                model_name,
                caller_default=requested_max_tokens or 12288,
            )
            resolved_max = _cap_local_vlm_max_tokens(
                resolved_max,
                route_metadata=route_metadata,
            )
            
            first_b64 = images[0].get("base64_jpeg", "")
            mime = _detect_image_mime(first_b64) if first_b64 else "unknown"
            logger.info(
                "[VLM] MIME=%s max_tokens=%d model=%s",
                mime,
                resolved_max,
                model_name,
            )

            queue_started = time.perf_counter()
            queue_wait_ms = 0.0
            mlx_post_ms = 0.0
            watchdog_payload = {
                "status": "active",
                "phase": "generating",
                "request_id": request_id,
                "reference_id": reference_id,
                "analysis_profile": analysis_profile,
                "model": model_name,
                "host_resource_lane_id": _host_resource_lane_id(route_metadata),
                "started_at": time.time(),
                "heartbeat_at": time.time(),
            }
            heartbeat_task = None
            request_error: Optional[BaseException] = None
            try:
                async with _MLX_SEMAPHORE:
                    async with _VlmProcessFileLock(process_lock_file):
                        queue_wait_ms = (time.perf_counter() - queue_started) * 1000
                        watchdog_payload["started_at"] = time.time()
                        watchdog_payload["heartbeat_at"] = time.time()
                        _write_watchdog_state(watchdog_payload, watchdog_state_file)
                        heartbeat_task = asyncio.create_task(
                            _watchdog_heartbeat(watchdog_payload, watchdog_state_file)
                        )
                        logger.info(
                            "[MultimodalAnalyze] Multimodal endpoint provider lock acquired for %s with %d images",
                            main_shortcode,
                            len(content) - 1,
                        )
                        post_started = time.perf_counter()
                        try:
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
                        except BaseException as exc:
                            request_error = exc
                            raise
                        mlx_post_ms = (time.perf_counter() - post_started) * 1000
            finally:
                if heartbeat_task is not None:
                    heartbeat_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await heartbeat_task
                if request_error and _should_preserve_watchdog_state_on_error(
                    request_error
                ):
                    _preserve_watchdog_state_for_client_timeout(
                        watchdog_payload,
                        watchdog_state_file,
                    )
                else:
                    _clear_watchdog_state(watchdog_state_file)
            
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            msg = choice.get("message") or {}
            finish_reason = choice.get("finish_reason")
            
            # Prefer content over reasoning; when both exist,
            # pick whichever looks like JSON (starts with '{').
            resp_content = (msg.get("content") or "").strip()
            reasoning = (msg.get("reasoning") or "").strip()
            response_source = "empty"
            if resp_content and _looks_like_json_object(resp_content):
                text = resp_content
                response_source = "content"
            elif reasoning and _looks_like_json_object(reasoning):
                text = reasoning
                response_source = "reasoning"
            elif (
                reasoning_trace_mode == "capture"
                and resp_content
                and _looks_like_visible_loop_prose(resp_content)
            ):
                text = resp_content
                response_source = "capture_leak_non_json"
            else:
                text = resp_content or reasoning
                response_source = "content" if resp_content else "reasoning"
                
            if text:
                telemetry = {
                    "request_id": request_id,
                    "reference_id": reference_id,
                    "analysis_profile": analysis_profile,
                    "image_payload_count": payload_stats.get(
                        "image_payload_count",
                        len([img for img in images if img.get("base64_jpeg")]),
                    ),
                    "image_payload_total_bytes": payload_stats.get(
                        "image_payload_total_bytes",
                        sum(len(img.get("base64_jpeg", "")) for img in images),
                    ),
                    "resolved_max_tokens": resolved_max,
                    "queue_wait_ms": queue_wait_ms,
                    "mlx_post_ms": mlx_post_ms,
                    "response_chars": len(text),
                    "finish_reason": finish_reason,
                    "response_source": response_source,
                    "reasoning_trace_mode": reasoning_trace_mode,
                }
                result_item = {
                    "shortcode": main_shortcode,
                    "description": text,
                    "_telemetry": telemetry,
                }
                if reasoning_trace_mode == "capture" and reasoning:
                    result_item["thinking"] = reasoning
                results.append(result_item)
                logger.info(
                    "[MultimodalAnalyze][Perf] request_id=%s reference_id=%s profile=%s max_tokens=%d queue_ms=%.1f post_ms=%.1f finish=%s source=%s chars=%d",
                    request_id,
                    reference_id,
                    analysis_profile,
                    resolved_max,
                    queue_wait_ms,
                    mlx_post_ms,
                    finish_reason,
                    response_source,
                    len(text),
                )
                logger.info(
                    "[MultimodalAnalyze] Multimodal endpoint analysis OK for %s (%d chars)",
                    main_shortcode, len(text),
                )
        except Exception as e:
            logger.warning(
                "[MultimodalAnalyze] Multimodal endpoint call failed for %s: %s: %s",
                main_shortcode,
                e.__class__.__name__,
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
        "results": results,
        "request_id": request_id,
        "reference_id": reference_id,
        "analysis_profile": analysis_profile,
        "_telemetry": results[0].get("_telemetry", {}) if results else {},
    }


async def _route_huggingface(
    images: List[Dict[str, Any]],
    prompt: str,
    model_id: str,
    temperature: float,
    *,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Route to Hugging Face VLM (Qwen2-VL etc.)."""
    vision_analyze = _load_hf_vision_tool()
    if vision_analyze is None:
        return {
            "status": "error",
            "error": "Hugging Face vision tool not available. "
                     "Is the huggingface capability pack installed?",
        }

    call_kwargs = {
        "images": images,
        "prompt": prompt,
        "model_id": model_id,
        "temperature": temperature,
    }
    requested_max_tokens = _coerce_positive_int(max_tokens)
    if requested_max_tokens is not None:
        import inspect

        try:
            signature = inspect.signature(vision_analyze)
            accepts_kwargs = any(
                param.kind == inspect.Parameter.VAR_KEYWORD
                for param in signature.parameters.values()
            )
            if "max_tokens" in signature.parameters or accepts_kwargs:
                call_kwargs["max_tokens"] = requested_max_tokens
        except (TypeError, ValueError):
            pass

    return await vision_analyze(**call_kwargs)


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
) -> Dict[str, Any]:
    """Route to managed multimodal provider selected by model-routing-registry."""
    from ....shared.llm_utils import call_llm
    from ....shared.llm_provider_helper import build_managed_llm_provider

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
        route_context = None
        if workspace_id:
            from ....services.executor_route_context import load_executor_route_context

            route_context = await load_executor_route_context(workspace_id)
        executor_runtime = (
            str((route_context or {}).get("executor_runtime") or "").strip()
            or None
        )
        llm_provider = None
        if not executor_runtime:
            llm_provider, _selection = build_managed_llm_provider(
                model_name=model_name,
                provider_name=provider_name,
                purpose="core_llm.multimodal_analyze",
            )
        resp = await call_llm(
            messages=messages,
            llm_provider=llm_provider,
            model=model_name,
            temperature=temperature,
            max_tokens=_coerce_positive_int(max_tokens),
            workspace_id=workspace_id,
            route_context=route_context,
            purpose="core_llm.multimodal_analyze",
            stage_name="multimodal_analyze",
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
