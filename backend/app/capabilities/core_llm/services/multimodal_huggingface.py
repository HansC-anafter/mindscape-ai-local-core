"""HuggingFace multimodal route helpers."""

import importlib.util
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


_hf_vision_cache: dict = {"fn": None, "source": None, "checked": False}


async def route_huggingface(
    images: List[Dict[str, Any]],
    prompt: str,
    model_id: str,
    temperature: float,
    *,
    max_tokens: Optional[int] = None,
) -> Dict[str, Any]:
    """Route to Hugging Face VLM (Qwen2-VL etc.)."""
    vision_analyze = load_hf_vision_tool()
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
    from backend.app.capabilities.core_llm.services import multimodal as facade

    requested_max_tokens = facade._coerce_positive_int(max_tokens)
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


def load_hf_vision_tool():
    """Dynamically load HF vision tool from installed capability pack."""
    if _hf_vision_cache["checked"]:
        return _hf_vision_cache["fn"]

    _hf_vision_cache["checked"] = True

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
                    logger.warning(
                        "[MultimodalAnalyze] %s exists but vision_analyze not found/callable",
                        pack_path,
                    )
            except Exception as e:
                logger.warning(
                    "[MultimodalAnalyze] Failed to load from %s: %s",
                    pack_path,
                    e,
                )
        else:
            logger.debug(
                "[MultimodalAnalyze] Pack path not found: %s",
                pack_path,
            )

    try:
        from capabilities.huggingface.tools.vision import vision_analyze

        _hf_vision_cache["fn"] = vision_analyze
        _hf_vision_cache["source"] = "direct_import"
        logger.info("[MultimodalAnalyze] HF vision tool loaded via direct import")
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
    """Health check for HF vision tool availability."""
    fn = load_hf_vision_tool()
    return {
        "available": fn is not None,
        "source": _hf_vision_cache.get("source"),
    }
