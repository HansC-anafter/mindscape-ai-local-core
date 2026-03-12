"""
Meeting LLM Adapter — runtime-aware LLM access for meeting engine components.

Provides a unified chat_completion() interface that routes through the
configured runtime (executor_runtime → gemini-cli, or direct LLM provider).

Consumers (TaskDecomposer, future Agent Assembler, etc.) depend on this
adapter instead of hardcoding provider resolution logic.

Contract:
    adapter = MeetingLLMAdapter.from_engine(engine)
    output  = await adapter.chat_completion(messages=[...])
"""

import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger(__name__)


class MeetingLLMAdapter:
    """Runtime-aware LLM adapter for meeting engine sub-components.

    Routes ``chat_completion()`` calls through the meeting engine's
    existing ``_generate_text()`` method, which already handles:

    - executor_runtime → WorkspaceAgentExecutor → gemini-cli
    - direct LLM provider fallback (when no executor_runtime)
    - retry logic, availability checks, clarification handling

    Usage::

        adapter = MeetingLLMAdapter.from_engine(engine)
        decomposer = TaskDecomposer(llm_adapter=adapter, ...)
    """

    def __init__(
        self,
        generate_fn: Callable[[List[Dict[str, str]]], Coroutine[Any, Any, str]],
        *,
        runtime_id: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        """
        Args:
            generate_fn: Async callable that accepts messages and returns text.
                         Typically ``engine._generate_text``.
            runtime_id:  Active executor runtime ID (for logging/diagnostics).
            model_name:  Resolved model name (for logging/diagnostics).
        """
        self._generate_fn = generate_fn
        self._runtime_id = runtime_id
        self._model_name = model_name

    # ----- factory ----------------------------------------------------------

    @classmethod
    def from_engine(cls, engine: Any) -> "MeetingLLMAdapter":
        """Build adapter from a MeetingEngine instance.

        Captures the engine's ``_generate_text`` method, which is the
        authoritative routing layer for all meeting LLM calls.
        """
        return cls(
            generate_fn=engine._generate_text,
            runtime_id=getattr(engine, "executor_runtime", None),
            model_name=getattr(engine, "model_name", None),
        )

    # ----- public interface (matches decomposer contract) -------------------

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        **kwargs,
    ) -> str:
        """Send messages through the configured runtime and return text.

        The ``model`` keyword argument is forwarded to the underlying
        generate_fn (P1.6).  Other kwargs are accepted for signature
        compatibility but NOT forwarded — the runtime controls those.
        """
        model = kwargs.pop("model", None)
        if kwargs:
            logger.debug(
                "MeetingLLMAdapter: ignoring kwargs %s (runtime controls params)",
                list(kwargs.keys()),
            )
        if model:
            return await self._generate_fn(messages, model=model)
        return await self._generate_fn(messages)

    # ----- diagnostics ------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"MeetingLLMAdapter(runtime={self._runtime_id!r}, "
            f"model={self._model_name!r})"
        )
