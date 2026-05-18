"""Executor bridge generation helpers."""

import logging
from typing import Any, Dict, List, Optional

from backend.app.services.orchestration.meeting import _generation as generation_module

logger = logging.getLogger(__name__)


class MeetingGenerationExecutorBridgeMixin:
    def _has_bound_executor_runtime(self) -> bool:
        runtime_id = str(getattr(self, "executor_runtime", "") or "").strip()
        return bool(runtime_id)

    async def _generate_text(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 4096,
        capability_profile: Optional[str] = None,
        model: Optional[str] = None,
        use_executor_runtime: bool = False,
    ) -> str:
        """Generate text with retry logic via the bound executor runtime only.

        Args:
            messages: Chat messages to send to the LLM.
            max_tokens: Maximum output tokens. Default 4096 — meeting rounds
                are multi-turn conversations that need generous output budgets.
                Callers doing constrained tasks (e.g. self-heal repair) can
                pass a lower value.
            capability_profile: Optional profile name (e.g. 'fast', 'precise').
                When set, model-routing-registry resolves it to a model.
            model: Optional explicit model override. Takes precedence over
                capability_profile resolution.
            use_executor_runtime: Retained for compatibility. Meeting generation
                always requires a bound executor runtime and never uses a direct
                provider path.
        """
        resolved_model: Optional[str] = model
        if not resolved_model and capability_profile:
            from backend.app.models.model_provider import ModelType
            from backend.app.services.model_routing_policy_service import (
                ModelRoutingPolicyService,
            )

            route = ModelRoutingPolicyService().resolve_profile_model(
                profile=capability_profile,
                scope="local",
                model_type=ModelType.CHAT,
            )
            resolved_model = route.model_name
        if not resolved_model:
            from backend.app.services.model_routing_policy_service import (
                ModelRoutingPolicyService,
            )

            resolved_model = ModelRoutingPolicyService().resolve_chat_default().model_name

        if capability_profile:
            try:
                self._emit_event(
                    "meeting_turn_model",
                    payload={
                        "capability_profile": capability_profile,
                        "resolved_model": resolved_model,
                        "route_authority": "model-routing-registry",
                        "session_id": getattr(
                            getattr(self, "session", None), "id", None
                        ),
                    },
                )
            except Exception:
                pass

        attempts = max(0, self.max_retries)

        last_error: Optional[Exception] = None
        for attempt in range(attempts + 1):
            try:
                if not self._has_bound_executor_runtime():
                    raise RuntimeError(
                        "Meeting generation requires a bound executor runtime; "
                        "direct provider routing has been removed"
                    )
                return await self._generate_text_via_executor_runtime(
                    messages, model=resolved_model
                )
            except Exception as exc:
                last_error = exc
                if generation_module._is_runtime_error_non_retriable_for_executor(
                    getattr(self, "executor_runtime", None),
                    exc,
                ):
                    reason = (
                        "codex_pool_admission_blocked"
                        if isinstance(exc, generation_module.CodexPoolAdmissionBlockedError)
                        else "non_retriable_quota_or_rate_limit"
                    )
                    self._emit_runtime_unavailable_event(
                        runtime_id=getattr(self, "executor_runtime", None)
                        or "llm_provider",
                        error=str(exc),
                        reason=reason,
                    )
                    break
                if attempt >= attempts:
                    break
                self.orchestrator.record_retry()
                await generation_module.asyncio.sleep(self._retry_delay_seconds(attempt))

        raise RuntimeError(
            f"Meeting turn generation failed: {last_error}"
        ) from last_error

    async def _generate_text_via_executor_runtime(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        """Generate text by delegating to a preferred agent runtime."""
        if not self.executor_runtime:
            raise RuntimeError("executor_runtime is not configured for meeting mode")
        if not self.workspace:
            raise RuntimeError(
                "workspace is required for executor_runtime meeting mode"
            )

        if (
            str(self.executor_runtime).strip().lower() == "codex_cli"
            and generation_module._should_use_direct_codex_cli_subprocess()
        ):
            return await self._generate_text_via_direct_codex_cli(
                messages, model=model
            )

        if not self._agent_executor:
            from backend.app.services.workspace_agent_executor import (
                WorkspaceAgentExecutor,
            )

            self._agent_executor = WorkspaceAgentExecutor(self.workspace)

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

        await self._emit_meeting_stage("generating", f"Running through {self.executor_runtime}...")

        context_overrides: Dict[str, Any] = {
            "meeting_session_id": self.session.id,
            "thread_id": self.thread_id,
            "project_id": self.project_id,
            "conversation_context": system_prompt,
        }
        model_hint = self._executor_model_hint(self.executor_runtime, model)
        if model_hint:
            context_overrides["model"] = model_hint
        try:
            from backend.app.services.executor_route_context import (
                build_executor_route_context,
            )

            route_context = build_executor_route_context(self.workspace)
            if route_context:
                context_overrides["executor_route_context"] = route_context
        except Exception:
            logger.warning(
                "Failed to build meeting executor route context for workspace %s",
                getattr(self.workspace, "id", None),
                exc_info=True,
            )

        attempts = generation_module._executor_runtime_attempt_count()
        result = None
        for attempt in range(attempts):
            admission = await self._evaluate_executor_runtime_admission()
            if not bool(admission.get("admissible", True)):
                error_text = generation_module._codex_pool_admission_error_text(admission)
                if (
                    attempt < attempts - 1
                    and generation_module._is_runtime_error_retryable_for_executor(
                        self.executor_runtime,
                        error_text,
                    )
                ):
                    logger.warning(
                        "Preferred agent '%s' blocked by admission gate "
                        "(attempt %d/%d): %s",
                        self.executor_runtime,
                        attempt + 1,
                        attempts,
                        error_text,
                    )
                    await generation_module.asyncio.sleep(generation_module._executor_runtime_retry_delay(attempt))
                    continue
                self._emit_runtime_unavailable_event(
                    runtime_id=self.executor_runtime,
                    error=f"Preferred agent '{self.executor_runtime}' failed: {error_text}",
                    reason="codex_pool_admission_blocked",
                    metadata={"codex_pool_admission": admission},
                )
                raise generation_module.CodexPoolAdmissionBlockedError(
                    f"Preferred agent '{self.executor_runtime}' failed: {error_text}"
                )

            result = await self._agent_executor.execute(
                task=task,
                agent_id=self.executor_runtime,
                context_overrides=context_overrides,
            )
            if result.success:
                break

            if result.needs_clarification:
                await self._emit_clarification_event(result.clarification_questions)
                return (
                    f"[Meeting paused] Awaiting user confirmation: "
                    f"{'; '.join(result.clarification_questions)}"
                )

            error_text = result.error or "unknown error"
            if (
                attempt < attempts - 1
                and generation_module._is_runtime_error_retryable_for_executor(
                    self.executor_runtime,
                    error_text,
                )
            ):
                logger.warning(
                    "Preferred agent '%s' transient failure during meeting turn "
                    "(attempt %d/%d): %s",
                    self.executor_runtime,
                    attempt + 1,
                    attempts,
                    error_text,
                )
                await generation_module.asyncio.sleep(generation_module._executor_runtime_retry_delay(attempt))
                continue

            self._emit_runtime_unavailable_event(
                runtime_id=self.executor_runtime,
                error=f"Preferred agent '{self.executor_runtime}' failed: {error_text}",
                reason=(
                    "executor_runtime_transient_unavailable"
                    if generation_module._is_runtime_error_retryable_for_executor(
                        self.executor_runtime,
                        error_text,
                    )
                    else "executor_runtime_failed"
                ),
            )
            raise RuntimeError(
                f"Preferred agent '{self.executor_runtime}' failed: {error_text}"
            )

        if result is None or not result.success:
            raise RuntimeError(
                f"Preferred agent '{self.executor_runtime}' failed: unknown error"
            )
        if not result.output or not result.output.strip():
            raise RuntimeError(
                f"Preferred agent '{self.executor_runtime}' returned empty output"
            )

        output_text = result.output.strip()
        try:
            from backend.app.services.cache.async_redis import publish_meeting_chunk

            workspace_id = getattr(self.workspace, "id", None) or ""
            session_id = getattr(self.session, "id", None) or ""
            thread_id = getattr(self, "thread_id", None) or getattr(self.session, "thread_id", None) or session_id

            await publish_meeting_chunk(
                workspace_id,
                {"type": "stream_start", "session_id": session_id},
                thread_id,
            )
            await publish_meeting_chunk(
                workspace_id,
                {"type": "chunk", "content": output_text, "session_id": session_id},
                thread_id,
            )
            await publish_meeting_chunk(
                workspace_id,
                {"type": "stream_end", "session_id": session_id, "full_text": output_text},
                thread_id,
            )
        except Exception as pub_exc:
            logger.warning("Failed to publish executor turn result to Redis: %s", pub_exc)

        return output_text

    async def _evaluate_executor_runtime_admission(self) -> Dict[str, Any]:
        return {"admissible": True, "reason": "executor_bridge_runtime"}

    @staticmethod
    def _executor_model_hint(executor_runtime: Optional[str], model: Optional[str]) -> Optional[str]:
        candidate = str(model or "").strip()
        if not candidate:
            return None
        runtime = str(executor_runtime or "").strip().lower()
        if runtime == "codex_cli":
            lowered = candidate.lower()
            if lowered.startswith(("gpt-", "o", "codex")):
                return candidate
            return None
        return candidate
