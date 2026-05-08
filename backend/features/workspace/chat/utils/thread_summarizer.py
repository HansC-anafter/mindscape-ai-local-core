"""
Thread Summarizer Utility
Generates concise titles for conversation threads using lightweight LLM models.
"""

import logging
from typing import Optional
from backend.app.shared.llm_utils import build_prompt, call_llm

logger = logging.getLogger(__name__)


async def summarize_thread(
    workspace_id: str,
    thread_id: str,
    store,
    model_name: Optional[str] = None,
) -> Optional[str]:
    """
    Generate a summary title for a thread and update it.

    Args:
        workspace_id: Workspace ID
        thread_id: Thread ID
        store: MindscapeStore instance
        model_name: Optional requested model; registry route is used when omitted.

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

        profile_id = None
        for e in events:
            if e.profile_id:
                profile_id = e.profile_id
                break

        messages = build_prompt(system_prompt=system_prompt, user_prompt=user_prompt)

        try:
            llm_result = await call_llm(
                messages=messages,
                model=model_name,
                workspace_id=workspace_id,
                profile_id=profile_id,
                purpose="workspace_chat.thread_summary",
                stage_name="response_formatting",
                temperature=0.3,  # Low temp for deterministic titles
                max_tokens=20,
            )
            response_text = str(llm_result.get("text") or "")

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
