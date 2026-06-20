"""Provider-level SSE wrappers for workspace chat streaming."""

import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

logger = logging.getLogger(__name__)


async def stream_openai_response(
    provider: Any,
    messages: List[Dict[str, Any]],
    model_name: str,
) -> AsyncGenerator[str, None]:
    use_provider_stream = hasattr(provider, "chat_completion_stream")

    if not use_provider_stream:
        yield f"data: {json.dumps({'type': 'error', 'message': 'Selected registry provider does not support chat_completion_stream'})}\n\n"
        return

    from backend.app.shared.inference_config import InferenceConfig

    resolved_max = InferenceConfig.get_max_tokens(model_name)
    async for chunk_content in provider.chat_completion_stream(
        messages=messages,
        model=model_name,
        temperature=0.7,
        max_tokens=resolved_max,
    ):
        yield f"data: {json.dumps({'type': 'chunk', 'content': chunk_content, 'model_name': model_name})}\n\n"


async def stream_vertexai_response(
    provider: Any,
    messages: List[Dict[str, Any]],
    model_name: str,
) -> AsyncGenerator[str, None]:
    if not model_name:
        yield f"data: {json.dumps({'type': 'error', 'message': 'No chat model configured in model-routing-registry'})}\n\n"
        return

    logger.info("Starting stream_llm_response for model %s", model_name)

    from backend.app.shared.inference_config import InferenceConfig

    resolved_max = InferenceConfig.get_max_tokens(model_name)

    if hasattr(provider, "chat_completion_stream"):
        async for chunk_content in provider.chat_completion_stream(
            messages=messages,
            model=model_name,
            temperature=0.7,
            max_tokens=resolved_max,
        ):
            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk_content, 'model_name': model_name})}\n\n"
    else:
        yield f"data: {json.dumps({'type': 'error', 'message': 'Selected registry provider does not support chat_completion_stream'})}\n\n"


def extract_sse_chunk_content(event: str) -> Optional[str]:
    if not event.startswith("data: "):
        return None
    try:
        data = json.loads(event[6:].strip())
    except Exception:
        return None
    if data.get("type") == "chunk":
        return data.get("content", "")
    return None
