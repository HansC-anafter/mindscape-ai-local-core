"""
Core LLM: Multimodal Analyze Service

Unified middleware for multimodal (vision) analysis.
Model selection is owned by model-routing-registry:
  profile_model_bindings.local.vision -> enabled multimodal model.
"""

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .multimodal_cloud import route_cloud_llm as _route_cloud_llm
from .multimodal_huggingface import (
    _hf_vision_cache,
    check_hf_vision_health,
    load_hf_vision_tool as _load_hf_vision_tool,
    route_huggingface as _route_huggingface,
)
from .multimodal_mlx import route_mlx_server as _route_mlx_server
from .multimodal_routing import (
    resolve_multimodal_base_url as _resolve_multimodal_base_url,
    resolve_multimodal_runtime_provider as _resolve_multimodal_runtime_provider,
    resolve_vision_route as _resolve_vision_route,
)

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
