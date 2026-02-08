"""
Thread Summarizer Utility
Generates concise titles for conversation threads using lightweight LLM models.
"""

import logging
from typing import Optional, List, Dict
import json

from backend.app.services.stores.conversation_threads_store import (
    ConversationThreadsStore,
)
from .llm_provider import (
    get_llm_provider_manager,
    get_llm_provider,
)
from backend.app.shared.llm_utils import build_prompt

logger = logging.getLogger(__name__)


async def summarize_thread(
    workspace_id: str, thread_id: str, store, model_name: str = "gemini-2.5-flash-lite"
) -> Optional[str]:
    """
    Generate a summary title for a thread and update it.

    Args:
        workspace_id: Workspace ID
        thread_id: Thread ID
        store: MindscapeStore instance
        model_name: Model to use for summarization (default: lightweight model)

    Returns:
        Generated title or None if failed
    """
    try:
        # 1. Check if thread needs summarization
        thread = store.conversation_threads.get_thread(thread_id)
        if not thread:
            logger.warning(f"Thread {thread_id} not found for summarization")
            return None

        # Only summarize if title is default/generic
        default_titles = ["New Conversation", "Untitled", "預設對話", "新對話"]
        if thread.title and thread.title not in default_titles:
            return None

        # 2. Get recent messages for context
        # fetch last few messages to understand context
        events = store.events.get_events_by_thread(
            workspace_id=workspace_id,
            thread_id=thread_id,
            limit=5,  # First few turns are usually enough for a title
        )

        if not events:
            return None

        # Format conversation for LLM
        conversation_text = ""
        for event in reversed(events):  # list_events usually returns new -> old
            role = "User" if event.actor == "user" else "Assistant"
            content = ""
            if event.payload and "message" in event.payload:
                content = event.payload["message"]
            elif event.payload and "text" in event.payload:
                content = event.payload["text"]

            if content:
                conversation_text += f"{role}: {content}\n"

        if not conversation_text.strip():
            return None

        # 3. Generate Title using LLM
        system_prompt = """You are a helpful assistant that generates short, descriptive titles for conversations.
output ONLY the title, no quotes, no conversational filler.
Target length: 3-5 words (or 5-10 chars for CJK).
Language: Detect the language of the conversation and output the title in the same language (Traditional Chinese for zh-TW)."""

        user_prompt = f"""Generate a concise title for this conversation:\n\n{conversation_text}"""

        # Get provider
        profile_id = None
        # Try to find a profile id from events if possible, else use None (system default)
        for e in events:
            if e.profile_id:
                profile_id = e.profile_id
                break

        llm_provider_manager = get_llm_provider_manager(
            profile_id=profile_id, db_path=store.db_path, use_default_user=True
        )

        # Fallback to standard provider if flash-lite not available is handled by manager/provider logic usually,
        # but here we request a specific model. If it fails, maybe fallback to standard chat model?
        # For now let's try the specified model.

        provider = llm_provider_manager.get_provider(
            "vertex-ai"
        )  # Prefer vertex for gemini
        if not provider:
            # Fallback to openai if configured?
            provider = llm_provider_manager.get_provider("openai")

        if not provider:
            logger.warning("No LLM provider available for summarization")
            return None

        messages = build_prompt(system_prompt=system_prompt, user_prompt=user_prompt)

        try:
            # Use non-streaming completion
            response_text = await provider.chat_completion(
                messages=messages,
                model=model_name,
                temperature=0.3,  # Low temp for deterministic titles
                max_tokens=20,
            )

            title = response_text.strip().strip('"').strip("'")

            # 4. Update Thread
            if title:
                store.conversation_threads.update_thread(
                    thread_id=thread_id, title=title
                )
                logger.info(f"Updated thread {thread_id} title to: {title}")
                return title

        except Exception as e:
            logger.warning(f"LLM generation failed for summarization: {e}")
            return None

    except Exception as e:
        logger.error(f"Error summarizing thread {thread_id}: {e}", exc_info=True)
        return None
