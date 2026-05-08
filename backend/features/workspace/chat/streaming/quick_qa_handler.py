"""
Quick QA Handler

Streams a brief understanding response before the execution plan
in execution/hybrid mode. Provides immediate feedback while the
heavier execution plan is being generated.
"""

import json
import logging
from typing import Any, AsyncGenerator, Optional

from backend.app.shared.llm_utils import build_prompt, call_llm

logger = logging.getLogger(__name__)


async def stream_quick_qa_response(
    request: Any,
    user_event_id: str,
    locale: str,
    model_name: str,
    profile_id: str,
    workspace_id: str,
    db_path: str,
) -> AsyncGenerator[str, None]:
    """
    Stream a brief understanding response before execution plan generation.

    Generates a 2-3 sentence acknowledgment using a lightweight LLM call
    with limited tokens for speed.

    Args:
        request: WorkspaceChatRequest with .message.
        user_event_id: User event ID for SSE message_id.
        locale: Response locale.
        model_name: LLM model name.
        profile_id: Profile ID for provider resolution.
        db_path: Database path for provider manager.

    Yields:
        SSE event strings (chunk events).
    """
    try:
        quick_system_prompt = (
            f'You are a helpful AI assistant. The user has asked: "{request.message}"\n\n'
            f"Your task: Provide a brief (2-3 sentences), understanding response that:\n"
            f"1. Shows you understand their request\n"
            f"2. Provides initial guidance on what tools/approaches might help\n"
            f"3. Sets expectation that you're analyzing and will provide a detailed plan\n\n"
            f"Keep it concise and friendly. Respond in {locale}."
        )

        quick_messages = build_prompt(
            system_prompt=quick_system_prompt,
            user_prompt=request.message,
        )

        quick_response_text = ""
        del db_path
        llm_result = await call_llm(
            messages=quick_messages,
            model=model_name,
            workspace_id=workspace_id,
            profile_id=profile_id,
            purpose="workspace_chat.quick_qa",
            stage_name="response_formatting",
            temperature=0.7,
            max_tokens=500,
        )
        quick_response_text = str(llm_result.get("text") or "")
        if quick_response_text:
            yield f"data: {json.dumps({'type': 'chunk', 'content': quick_response_text, 'message_id': user_event_id, 'is_final': False})}\n\n"

        # Signal quick response completion (not final -- main response follows)
        yield f"data: {json.dumps({'type': 'chunk', 'content': '', 'message_id': user_event_id, 'is_final': False})}\n\n"
        yield f"data: {json.dumps({'type': 'quick_response_complete', 'message_id': user_event_id})}\n\n"

        logger.info("Quick QA response generated: %d chars", len(quick_response_text))

    except Exception as e:
        logger.warning("Failed to generate quick QA response: %s", e, exc_info=True)
        yield f"data: {json.dumps({'type': 'error', 'message': f'Quick response error: {str(e)}', 'message_id': user_event_id})}\n\n"
