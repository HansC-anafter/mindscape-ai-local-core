"""
LLM Model Discovery & Custom Registration Endpoints

Provides:
- GET  /discover/huggingface  — Search HF Hub models by pipeline_tag
- POST /models/custom         — Register a custom model into model_configs
- DELETE /models/custom/{id}  — Remove a user-added custom model
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Body, HTTPException, Query

router = APIRouter()
logger = logging.getLogger(__name__)

# ── HF pipeline_tag → our ModelType mapping ──────────────────────────────────
PIPELINE_TAG_TO_MODEL_TYPE = {
    "text-generation": "chat",
    "text2text-generation": "chat",
    "image-text-to-text": "multimodal",
    "visual-question-answering": "multimodal",
    "image-to-text": "multimodal",
    "feature-extraction": "embedding",
    "sentence-similarity": "embedding",
}

# Reverse: our model_type → HF pipeline_tags (for discovery search)
MODEL_TYPE_TO_PIPELINE_TAGS = {
    "chat": ["text-generation"],
    "multimodal": ["image-text-to-text"],
    "embedding": ["feature-extraction"],
}

HF_API_BASE = "https://huggingface.co/api"


@router.get("/discover/huggingface", response_model=List[Dict[str, Any]])
async def discover_huggingface_models(
    model_type: Optional[str] = Query(
        None,
        description="Filter by our model type: 'chat', 'multimodal', 'embedding'",
    ),
    search: Optional[str] = Query(None, description="Free-text search query"),
    limit: int = Query(20, ge=1, le=100, description="Max results to return"),
):
    """
    Search Hugging Face Hub for models, mapped to our model types.

    Returns a list of HF models with id, pipeline_tag, mapped model_type,
    downloads, likes, and description.
    """
    try:
        results = []

        # Determine which pipeline_tags to query
        if model_type and model_type in MODEL_TYPE_TO_PIPELINE_TAGS:
            tags_to_query = MODEL_TYPE_TO_PIPELINE_TAGS[model_type]
        elif model_type:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown model_type '{model_type}'. "
                f"Supported: {list(MODEL_TYPE_TO_PIPELINE_TAGS.keys())}",
            )
        else:
            # Query all supported tags
            tags_to_query = []
            for tags in MODEL_TYPE_TO_PIPELINE_TAGS.values():
                tags_to_query.extend(tags)

        async with httpx.AsyncClient(timeout=15) as client:
            for tag in tags_to_query:
                params: Dict[str, Any] = {
                    "pipeline_tag": tag,
                    "sort": "downloads",
                    "direction": "-1",
                    "limit": limit,
                }
                if search:
                    params["search"] = search

                resp = await client.get(f"{HF_API_BASE}/models", params=params)
                if resp.status_code != 200:
                    logger.warning(
                        "HF API returned %d for tag=%s: %s",
                        resp.status_code,
                        tag,
                        resp.text[:200],
                    )
                    continue

                for item in resp.json():
                    pipeline = item.get("pipeline_tag", tag)
                    mapped_type = PIPELINE_TAG_TO_MODEL_TYPE.get(pipeline, "chat")
                    results.append(
                        {
                            "model_id": item.get("id", ""),
                            "pipeline_tag": pipeline,
                            "model_type": mapped_type,
                            "downloads": item.get("downloads", 0),
                            "likes": item.get("likes", 0),
                            "description": (item.get("cardData") or {}).get(
                                "description", ""
                            ),
                            "tags": item.get("tags", []),
                            "last_modified": item.get("lastModified", ""),
                        }
                    )

        # De-duplicate by model_id, keep highest downloads
        seen = {}
        for r in results:
            mid = r["model_id"]
            if mid not in seen or r["downloads"] > seen[mid]["downloads"]:
                seen[mid] = r
        results = sorted(seen.values(), key=lambda x: x["downloads"], reverse=True)

        return results[:limit]

    except httpx.ConnectError:
        raise HTTPException(
            status_code=502,
            detail="Cannot reach Hugging Face API. Check network connectivity.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("HF discovery failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Discovery failed: {e}")


@router.get("/discover/huggingface/{repo_id:path}", response_model=Dict[str, Any])
async def get_huggingface_model_info(repo_id: str):
    """
    Get info for a specific HF model by repo ID (e.g. 'Qwen/Qwen2-VL-9B-Instruct').

    Returns the model's pipeline_tag, mapped model_type, and metadata.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{HF_API_BASE}/models/{repo_id}")
            if resp.status_code == 404:
                raise HTTPException(
                    status_code=404,
                    detail=f"Model '{repo_id}' not found on Hugging Face Hub.",
                )
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"HF API error: {resp.status_code}",
                )

            data = resp.json()
            pipeline = data.get("pipeline_tag", "")
            mapped_type = PIPELINE_TAG_TO_MODEL_TYPE.get(pipeline, "chat")

            return {
                "model_id": data.get("id", repo_id),
                "pipeline_tag": pipeline,
                "model_type": mapped_type,
                "downloads": data.get("downloads", 0),
                "likes": data.get("likes", 0),
                "description": (data.get("cardData") or {}).get("description", ""),
                "tags": data.get("tags", []),
                "last_modified": data.get("lastModified", ""),
                "author": data.get("author", ""),
            }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("HF model info failed for %s: %s", repo_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/models/custom", response_model=Dict[str, Any])
async def register_custom_model(
    payload: Dict[str, Any] = Body(
        ...,
        example={
            "model_id": "Qwen/Qwen2-VL-9B-Instruct",
            "provider": "huggingface",
            "model_type": "multimodal",
            "display_name": "Qwen2-VL 9B",
            "description": "Qwen2 Vision-Language 9B Instruct",
        },
    )
):
    """
    Register a custom model into the central model_configs table.

    If model_id looks like an HF repo (contains '/'), we auto-lookup
    its pipeline_tag to infer model_type when not explicitly provided.
    """
    from backend.app.models.model_provider import ModelConfig, ModelType
    from backend.app.services.model_config_store import ModelConfigStore

    model_id = payload.get("model_id", "").strip()
    provider = payload.get("provider", "huggingface").strip()
    model_type_str = payload.get("model_type", "").strip()
    display_name = payload.get("display_name", "").strip()
    description = payload.get("description", "").strip()

    if not model_id:
        raise HTTPException(status_code=400, detail="model_id is required")

    # Auto-detect model_type from HF if not provided
    hf_meta = {}
    if "/" in model_id:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{HF_API_BASE}/models/{model_id}")
                if resp.status_code == 200:
                    data = resp.json()
                    pipeline = data.get("pipeline_tag", "")
                    tags = data.get("tags", [])
                    if not model_type_str:
                        model_type_str = PIPELINE_TAG_TO_MODEL_TYPE.get(pipeline, "chat")
                    if not display_name:
                        display_name = model_id.split("/")[-1]
                    if not description:
                        description = (data.get("cardData") or {}).get(
                            "description", f"HuggingFace model: {model_id}"
                        )

                    # ── Extract rich metadata ──
                    # Format detection from tags
                    fmt = "safetensors"
                    if "gguf" in tags:
                        fmt = "GGUF"
                    elif "mlx" in [t.lower() for t in tags if isinstance(t, str)]:
                        fmt = "MLX"

                    # Quantization detection from tags
                    quant = None
                    for t in tags:
                        if isinstance(t, str) and any(q in t.lower() for q in ["4-bit", "8-bit", "fp8", "gptq", "awq", "bnb"]):
                            quant = t
                            break

                    # Parameter count
                    params = None
                    safetensors_info = data.get("safetensors", {})
                    if safetensors_info and "total" in safetensors_info:
                        params = safetensors_info["total"]
                    gguf_info = data.get("gguf", {})
                    if gguf_info and "total" in gguf_info:
                        params = gguf_info["total"]

                    # Context length
                    ctx_len = None
                    if gguf_info and "context_length" in gguf_info:
                        ctx_len = gguf_info["context_length"]

                    hf_meta = {
                        "is_custom": True,
                        "source": "user_registration",
                        "hf_author": data.get("author", ""),
                        "hf_format": fmt,
                        "hf_quantization": quant,
                        "hf_library": data.get("library_name", ""),
                        "hf_pipeline_tag": pipeline,
                        "hf_parameters": params,
                        "hf_context_length": ctx_len,
                        "hf_downloads": data.get("downloads", 0),
                        "hf_likes": data.get("likes", 0),
                        "hf_tags": [t for t in tags[:15] if isinstance(t, str)],
                        "hf_storage_bytes": data.get("usedStorage"),
                    }
        except Exception as e:
            logger.warning("Auto-detect from HF failed for %s: %s", model_id, e)

    if not hf_meta:
        hf_meta = {"is_custom": True, "source": "user_registration"}

    if not model_type_str:
        model_type_str = "chat"  # fallback

    # Validate model_type
    try:
        model_type_enum = ModelType(model_type_str)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid model_type '{model_type_str}'. "
            f"Must be one of: {[t.value for t in ModelType]}",
        )

    if not display_name:
        display_name = model_id.split("/")[-1] if "/" in model_id else model_id

    if not description:
        description = f"Custom model: {model_id}"

    # Check for duplicates
    store = ModelConfigStore()
    existing = await asyncio.to_thread(
        store.get_model_by_name_and_provider,
        model_id,
        provider,
        model_type_enum,
    )
    if existing:
        return {
            "success": True,
            "message": f"Model '{model_id}' already registered (id={existing.id})",
            "model": {
                "id": existing.id,
                "model_name": existing.model_name,
                "provider": existing.provider_name,
                "model_type": existing.model_type.value,
                "display_name": existing.display_name,
                "enabled": existing.enabled,
            },
            "is_new": False,
        }

    # Create the model
    model = ModelConfig(
        model_name=model_id,
        provider_name=provider,
        model_type=model_type_enum,
        display_name=display_name,
        description=description,
        enabled=True,  # auto-enable custom models
        is_latest=True,
        is_recommended=False,
        context_window=hf_meta.get("hf_context_length"),
        metadata=hf_meta,
    )

    created = await asyncio.to_thread(store.create_or_update_model, model)

    return {
        "success": True,
        "message": f"Model '{model_id}' registered successfully",
        "model": {
            "id": created.id,
            "model_name": created.model_name,
            "provider": created.provider_name,
            "model_type": created.model_type.value,
            "display_name": created.display_name,
            "enabled": created.enabled,
        },
        "is_new": True,
    }


@router.delete("/models/custom/{model_id}", response_model=Dict[str, Any])
async def remove_custom_model(model_id: int):
    """Remove a user-added custom model from model_configs."""
    from backend.app.services.model_config_store import ModelConfigStore

    store = ModelConfigStore()
    model = await asyncio.to_thread(store.get_model_by_id, model_id)

    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    # Safety: only allow deleting custom models
    is_custom = (model.metadata or {}).get("is_custom", False)
    if not is_custom:
        raise HTTPException(
            status_code=403,
            detail="Cannot delete built-in models. Use disable instead.",
        )

    await asyncio.to_thread(store.delete_model, model_id)

    return {"success": True, "message": f"Custom model {model_id} removed"}
