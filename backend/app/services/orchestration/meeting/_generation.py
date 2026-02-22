"""
Meeting engine text generation mixin.

Handles LLM provider initialization, text generation with retry logic,
and preferred agent delegation.
"""

import asyncio
import inspect
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MeetingGenerationMixin:
    """Mixin providing LLM text generation methods for MeetingEngine."""

    async def _generate_text(self, messages: List[Dict[str, str]]) -> str:
        """Generate text with retry logic, via preferred agent or LLM provider."""
        attempts = max(0, self.max_retries)

        last_error: Optional[Exception] = None
        for attempt in range(attempts + 1):
            try:
                if self.preferred_agent:
                    return await self._generate_text_via_preferred_agent(messages)
                await self._ensure_provider()
                return await self._generate_text_via_llm(messages)
            except Exception as exc:
                last_error = exc
                if attempt >= attempts:
                    break
                self.orchestrator.record_retry()
                await asyncio.sleep(self._retry_delay_seconds(attempt))

        raise RuntimeError(
            f"Meeting turn generation failed: {last_error}"
        ) from last_error

    async def _generate_text_via_llm(self, messages: List[Dict[str, str]]) -> str:
        """Generate text directly via the configured LLM provider."""
        call_kwargs = {
            "messages": messages,
            "model": self.model_name,
            "temperature": 0.3,
            "max_tokens": 1200,
        }
        sig = inspect.signature(self.provider.chat_completion)
        allowed = set(sig.parameters.keys())
        kwargs = {k: v for k, v in call_kwargs.items() if k in allowed}
        if "messages" not in kwargs:
            kwargs["messages"] = messages
        content = await self.provider.chat_completion(**kwargs)
        if not content or not str(content).strip():
            raise RuntimeError("Meeting LLM returned empty content")
        return str(content).strip()

    async def _generate_text_via_preferred_agent(
        self, messages: List[Dict[str, str]]
    ) -> str:
        """Generate text by delegating to a preferred agent runtime."""
        if not self.preferred_agent:
            raise RuntimeError("preferred_agent is not configured for meeting mode")
        if not self.workspace:
            raise RuntimeError("workspace is required for preferred_agent meeting mode")

        if not self._agent_executor:
            from backend.app.services.workspace_agent_executor import (
                WorkspaceAgentExecutor,
            )

            self._agent_executor = WorkspaceAgentExecutor(self.workspace)

        available = False
        for attempt in range(3):
            available = await self._agent_executor.check_agent_available(
                self.preferred_agent
            )
            if available:
                break
            if attempt < 2:
                logger.warning(
                    "Agent '%s' unavailable (attempt %d/3), retrying...",
                    self.preferred_agent,
                    attempt + 1,
                )
                await asyncio.sleep(2 * (attempt + 1))
        if not available:
            raise RuntimeError(
                f"Preferred agent '{self.preferred_agent}' is unavailable in meeting mode"
            )

        system_prompt = ""
        user_prompt = ""
        for msg in messages:
            role = str(msg.get("role", "")).lower()
            if role == "system" and not system_prompt:
                system_prompt = str(msg.get("content", ""))
            if role == "user":
                user_prompt = str(msg.get("content", ""))

        task = (
            "[Meeting Agent Turn]\n"
            f"Session: {self.session.id}\n"
            "Follow the system instructions and produce a direct role response.\n\n"
            f"[System Prompt]\n{system_prompt}\n\n"
            f"[Turn Prompt]\n{user_prompt}\n"
        )

        result = await self._agent_executor.execute(
            task=task,
            agent_id=self.preferred_agent,
            context_overrides={
                "meeting_session_id": self.session.id,
                "thread_id": self.thread_id,
                "project_id": self.project_id,
                "conversation_context": system_prompt,
            },
        )
        if not result.success:
            raise RuntimeError(
                f"Preferred agent '{self.preferred_agent}' failed: "
                f"{result.error or 'unknown error'}"
            )
        if not result.output or not result.output.strip():
            raise RuntimeError(
                f"Preferred agent '{self.preferred_agent}' returned empty output"
            )
        return result.output.strip()

    async def _ensure_provider(self) -> None:
        """Initialize the LLM provider if not already set."""
        if self.provider:
            return

        if not self.model_name:
            self.model_name = self._resolve_model_name()

        from backend.features.workspace.chat.utils.llm_provider import (
            get_llm_provider,
            get_llm_provider_manager,
        )

        manager = get_llm_provider_manager(
            profile_id=self.profile_id,
            db_path=getattr(self.store, "db_path", None),
        )
        provider, _ = get_llm_provider(
            model_name=self.model_name,
            llm_provider_manager=manager,
            profile_id=self.profile_id,
            db_path=getattr(self.store, "db_path", None),
        )
        self.provider = provider

    def _resolve_model_name(self) -> str:
        """Resolve the model name from system settings."""
        try:
            from backend.app.services.system_settings_store import SystemSettingsStore

            setting = SystemSettingsStore().get_setting("chat_model")
            if setting and setting.value:
                return str(setting.value)
        except Exception as exc:
            logger.warning("MeetingEngine failed to resolve chat_model: %s", exc)
        raise RuntimeError(
            "Meeting mode requires model_name or system setting 'chat_model'; "
            "no fallback model is allowed"
        )

    def _retry_delay_seconds(self, attempt: int) -> float:
        """Calculate retry delay based on strategy."""
        if self.retry_strategy == "immediate":
            return 0.0
        if self.retry_strategy == "exponential_backoff":
            return float(min(2**attempt, 8))
        return 0.0
