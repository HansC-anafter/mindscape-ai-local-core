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

    async def _generate_text(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 4096,
    ) -> str:
        """Generate text with retry logic, via preferred agent or LLM provider.

        Args:
            messages: Chat messages to send to the LLM.
            max_tokens: Maximum output tokens. Default 4096 — meeting rounds
                are multi-turn conversations that need generous output budgets.
                Callers doing constrained tasks (e.g. self-heal repair) can
                pass a lower value.
        """
        attempts = max(0, self.max_retries)

        last_error: Optional[Exception] = None
        for attempt in range(attempts + 1):
            try:
                if self.executor_runtime:
                    return await self._generate_text_via_executor_runtime(messages)
                await self._ensure_provider()
                return await self._generate_text_via_llm(
                    messages, max_tokens=max_tokens
                )
            except Exception as exc:
                last_error = exc
                if attempt >= attempts:
                    break
                self.orchestrator.record_retry()
                await asyncio.sleep(self._retry_delay_seconds(attempt))

        raise RuntimeError(
            f"Meeting turn generation failed: {last_error}"
        ) from last_error

    async def _generate_text_via_llm(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 4096,
    ) -> str:
        """Generate text directly via the configured LLM provider."""
        call_kwargs = {
            "messages": messages,
            "model": self.model_name,
            "temperature": 0.3,
            "max_tokens": max_tokens,
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

    async def _generate_text_via_executor_runtime(
        self, messages: List[Dict[str, str]]
    ) -> str:
        """Generate text by delegating to a preferred agent runtime."""
        if not self.executor_runtime:
            raise RuntimeError("executor_runtime is not configured for meeting mode")
        if not self.workspace:
            raise RuntimeError(
                "workspace is required for executor_runtime meeting mode"
            )

        if not self._agent_executor:
            from backend.app.services.workspace_agent_executor import (
                WorkspaceAgentExecutor,
            )

            self._agent_executor = WorkspaceAgentExecutor(self.workspace)

        available = False
        for attempt in range(3):
            available = await self._agent_executor.check_agent_available(
                self.executor_runtime
            )
            if available:
                break
            if attempt < 2:
                logger.warning(
                    "Agent '%s' unavailable (attempt %d/3), retrying...",
                    self.executor_runtime,
                    attempt + 1,
                )
                await asyncio.sleep(2 * (attempt + 1))
        if not available:
            raise RuntimeError(
                f"Preferred agent '{self.executor_runtime}' is unavailable in meeting mode"
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
            agent_id=self.executor_runtime,
            context_overrides={
                "meeting_session_id": self.session.id,
                "thread_id": self.thread_id,
                "project_id": self.project_id,
                "conversation_context": system_prompt,
            },
        )
        if not result.success:
            # Surface clarification requests as decision events, not fatal errors
            if result.needs_clarification:
                await self._emit_clarification_event(result.clarification_questions)
                return (
                    f"[Meeting paused] Awaiting user confirmation: "
                    f"{'; '.join(result.clarification_questions)}"
                )
            raise RuntimeError(
                f"Preferred agent '{self.executor_runtime}' failed: "
                f"{result.error or 'unknown error'}"
            )
        if not result.output or not result.output.strip():
            raise RuntimeError(
                f"Preferred agent '{self.executor_runtime}' returned empty output"
            )
        return result.output.strip()

    async def _emit_clarification_event(self, questions: list[str]) -> None:
        """Emit a decision_required event so the UI shows a confirmation card."""
        try:
            import uuid
            from datetime import datetime, timezone
            from backend.app.models.mindscape import MindEvent, EventType, EventActor

            event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                actor=EventActor.AGENT,
                channel="meeting",
                profile_id=getattr(self, "profile_id", "") or "",
                project_id=getattr(self, "project_id", None),
                workspace_id=self.workspace.id,
                event_type=EventType.DECISION_REQUIRED,
                payload={
                    "card_type": "decision",
                    "priority": "high",
                    "requires_user_approval": True,
                    "clarification_questions": questions,
                    "selected_playbook_code": f"agent:{self.executor_runtime}",
                    "rationale": "Task risk assessment requires user confirmation before proceeding.",
                },
            )
            self.store.create_event(event)
            logger.info("Emitted DECISION_REQUIRED event for meeting clarification")
        except Exception as exc:
            logger.warning("Failed to emit clarification event: %s", exc)

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
