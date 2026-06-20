"""Local MLX multimodal route implementation."""

import asyncio
import contextlib
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def route_mlx_server(
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

    from backend.app.capabilities.core_llm.services import multimodal as facade

    if not base_url:
        base_url = facade._resolve_multimodal_base_url(route_metadata or {})
    url = f"{base_url}/v1/chat/completions"
    reasoning_trace_mode = facade._normalize_reasoning_trace_mode(
        reasoning_trace_mode
    )
    payload_stats = payload_stats or {}

    logger.info(
        "[MultimodalAnalyze] Routing to multimodal endpoint: %s (model=%s)",
        url,
        model_name,
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
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{facade._detect_image_mime(b64_jpeg)};base64,{b64_jpeg}"
                    },
                }
            )

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
        },
    ]

    server_progress_enabled = facade._mlx_server_progress_enabled()
    timeout = facade._build_mlx_http_timeout(
        httpx,
        server_progress_enabled=server_progress_enabled,
    )
    watchdog_state_file = facade._watchdog_state_file(route_metadata)
    process_lock_file = facade._mlx_process_lock_file(route_metadata)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            from ....shared.inference_config import InferenceConfig

            requested_max_tokens = facade._coerce_positive_int(max_tokens)
            resolved_max = InferenceConfig.get_max_tokens(
                model_name,
                caller_default=requested_max_tokens or 12288,
            )
            resolved_max = facade._cap_local_vlm_max_tokens(
                resolved_max,
                route_metadata=route_metadata,
            )

            first_b64 = images[0].get("base64_jpeg", "")
            mime = facade._detect_image_mime(first_b64) if first_b64 else "unknown"
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
                "host_resource_lane_id": facade._host_resource_lane_id(
                    route_metadata
                ),
                "started_at": time.time(),
                "heartbeat_at": time.time(),
            }
            heartbeat_task = None
            request_error: Optional[BaseException] = None
            try:
                async with facade._MLX_SEMAPHORE:
                    async with facade._VlmProcessFileLock(process_lock_file):
                        queue_wait_ms = (time.perf_counter() - queue_started) * 1000
                        watchdog_payload["started_at"] = time.time()
                        watchdog_payload["heartbeat_at"] = time.time()
                        facade._write_watchdog_state(
                            watchdog_payload, watchdog_state_file
                        )
                        heartbeat_task = asyncio.create_task(
                            facade._watchdog_heartbeat(
                                watchdog_payload, watchdog_state_file
                            )
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
                if request_error and facade._should_preserve_watchdog_state_on_error(
                    request_error
                ):
                    facade._preserve_watchdog_state_for_client_timeout(
                        watchdog_payload,
                        watchdog_state_file,
                    )
                else:
                    facade._clear_watchdog_state(watchdog_state_file)

            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            msg = choice.get("message") or {}
            finish_reason = choice.get("finish_reason")

            resp_content = (msg.get("content") or "").strip()
            reasoning = (msg.get("reasoning") or "").strip()
            response_source = "empty"
            if resp_content and facade._looks_like_json_object(resp_content):
                text = resp_content
                response_source = "content"
            elif reasoning and facade._looks_like_json_object(reasoning):
                text = reasoning
                response_source = "reasoning"
            elif (
                reasoning_trace_mode == "capture"
                and resp_content
                and facade._looks_like_visible_loop_prose(resp_content)
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
                    main_shortcode,
                    len(text),
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
