"""Model-routing helpers for multimodal analysis."""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def resolve_vision_route() -> tuple[str, str, Dict[str, Any]]:
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
        resolve_multimodal_runtime_provider(route.provider, metadata),
        metadata,
    )


def resolve_multimodal_runtime_provider(provider: str, metadata: Dict[str, Any]) -> str:
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


def resolve_multimodal_base_url(route_metadata: Dict[str, Any]) -> str:
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
