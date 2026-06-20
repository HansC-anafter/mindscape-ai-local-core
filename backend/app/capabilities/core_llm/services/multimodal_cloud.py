"""Managed multimodal provider route implementation."""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def route_cloud_llm(
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
    from ....shared.llm_provider_helper import build_managed_llm_provider
    from ....shared.llm_utils import call_llm
    from backend.app.capabilities.core_llm.services import multimodal as facade

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
            mime_type = facade._detect_image_mime(b64_jpeg)
            if provider_name == "anthropic":
                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": b64_jpeg,
                        },
                    }
                )
            else:
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime_type};base64,{b64_jpeg}"},
                    }
                )

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
            max_tokens=facade._coerce_positive_int(max_tokens),
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
