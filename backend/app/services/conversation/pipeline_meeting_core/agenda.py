"""Agenda helpers for meeting pipeline runtime."""

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

AGENDA_MAX_ITEMS = 10
AGENDA_ITEM_MAX_LEN = 200


def sanitize_agenda_item(msg: str) -> str:
    clean = msg.strip()
    if len(clean) > AGENDA_ITEM_MAX_LEN:
        clean = clean[:AGENDA_ITEM_MAX_LEN] + "..."
    return clean


async def append_agenda_if_needed(
    session: Any,
    session_store: Any,
    user_message: Optional[str],
    *,
    model_name: Optional[str] = None,
    executor_runtime: Optional[str] = None,
    llm_generate_fn: Optional[Callable[..., Awaitable[str]]] = None,
) -> None:
    if not user_message:
        return
    decomposed = await decompose_agenda(
        user_message,
        model_name=model_name,
        executor_runtime=executor_runtime,
        llm_generate_fn=llm_generate_fn,
    )
    current = list(session.agenda or [])
    for item in decomposed:
        if item and item not in current and len(current) < AGENDA_MAX_ITEMS:
            current.append(item)
    if current == list(session.agenda or []):
        return
    session.agenda = current
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: session_store.update(session))


async def decompose_agenda(
    user_message: str,
    model_name: str | None = None,
    executor_runtime: str | None = None,
    llm_generate_fn: Optional[Callable[..., Awaitable[str]]] = None,
) -> list[str]:
    del executor_runtime
    if not user_message or len(user_message.strip()) < 10:
        return [sanitize_agenda_item(user_message)]
    if llm_generate_fn is None:
        return [sanitize_agenda_item(user_message)]

    try:
        import json as _json

        if not model_name:
            return [sanitize_agenda_item(user_message)]

        messages = [
            {
                "role": "system",
                "content": (
                    "Split the request into 2-5 short task labels (<=10 words each). "
                    "Return ONLY a JSON array of strings. Example: "
                    '["research X","create Y posts","find images"]'
                ),
            },
            {"role": "user", "content": user_message[:500]},
        ]
        raw = await llm_generate_fn(messages, model=model_name)
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        items = _json.loads(text)
        if isinstance(items, list) and 2 <= len(items) <= AGENDA_MAX_ITEMS:
            return [sanitize_agenda_item(str(item)) for item in items if str(item).strip()]
    except Exception as exc:
        logger.warning("Agenda decomposition failed (fallback): %s", exc)

    return [sanitize_agenda_item(user_message)]
