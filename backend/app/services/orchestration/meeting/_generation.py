"""
Meeting engine text generation mixin.

Handles LLM provider initialization, text generation with retry logic,
and preferred agent delegation.
"""

import asyncio
import inspect
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


_NON_RETRIABLE_RUNTIME_PATTERNS = (
    "terminalquotaerror",
    "exhausted your capacity",
    "usage limit",
    "quota exceeded",
    "resource_exhausted",
    "resource exhausted",
    "rate limit",
    "too many requests",
    "not supported when using codex",
)


def _is_non_retriable_runtime_error(exc: Exception) -> bool:
    """Return True when the runtime error should fail fast.

    The Gemini CLI runtime bridge already performs one internal refresh/retry
    for auth/quota faults. If the error still bubbles up here, retrying the
    whole meeting turn just burns additional budget and delays failure.
    """
    text = str(exc or "").lower()
    return any(pattern in text for pattern in _NON_RETRIABLE_RUNTIME_PATTERNS)


def _looks_like_codex_quota_exhaustion(message: str) -> bool:
    normalized = str(message or "").lower()
    if not normalized:
        return False
    return any(
        marker in normalized
        for marker in (
            "usage limit",
            "rate limit",
            "quota",
            "too many requests",
            "resource_exhausted",
            "429",
        )
    )


def _looks_like_codex_auth_failure(message: str) -> bool:
    normalized = str(message or "").lower()
    if not normalized:
        return False
    markers = (
        "401 unauthorized",
        "unauthorized",
        "missing bearer",
        "missing bearer or basic authentication",
        "authentication failed",
        "invalid api key",
        "incorrect api key",
        "missing api key",
    )
    return (
        any(marker in normalized for marker in markers)
        and not _looks_like_codex_quota_exhaustion(normalized)
    )


def _should_retry_direct_codex_runtime_fault(message: str) -> bool:
    normalized = str(message or "").strip().lower()
    if not normalized:
        return False
    if _looks_like_codex_quota_exhaustion(normalized):
        return True
    if _looks_like_codex_auth_failure(normalized):
        return True
    return "subprocess stalled after" in normalized


class MeetingGenerationMixin:
    """Mixin providing LLM text generation methods for MeetingEngine."""

    async def _generate_text(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 4096,
        capability_profile: Optional[str] = None,
        model: Optional[str] = None,
        use_executor_runtime: bool = False,
    ) -> str:
        """Generate text with retry logic, via preferred agent or LLM provider.

        Args:
            messages: Chat messages to send to the LLM.
            max_tokens: Maximum output tokens. Default 4096 — meeting rounds
                are multi-turn conversations that need generous output budgets.
                Callers doing constrained tasks (e.g. self-heal repair) can
                pass a lower value.
            capability_profile: Optional profile name (e.g. 'fast', 'precise').
                When set, CapabilityProfileResolver resolves it to a model.
            model: Optional explicit model override. Takes precedence over
                capability_profile resolution. Used by MeetingLLMAdapter and
                external consumers.
            use_executor_runtime: When True, force the preferred executor runtime
                for this generation. Meeting governance defaults to direct LLM
                generation because executor runtimes are execution environments,
                not the identity layer for facilitator/planner/critic turns.
        """
        # Resolve model: explicit model > capability_profile > global default
        resolved_model: Optional[str] = model
        resolved_variant: Optional[str] = None
        if not resolved_model and capability_profile:
            from backend.app.services.capability_profile_resolver import (
                CapabilityProfileResolver,
            )

            resolver = CapabilityProfileResolver()
            resolved_model, resolved_variant = resolver.resolve(capability_profile)

        # P1.6-C: Trace hook — record per-agent model routing for observability
        if capability_profile:
            try:
                self._emit_event(
                    "meeting_turn_model",
                    payload={
                        "capability_profile": capability_profile,
                        "resolved_model": resolved_model,
                        "resolved_variant": resolved_variant,
                        "fallback_happened": resolved_model is None,
                        "session_id": getattr(
                            getattr(self, "session", None), "id", None
                        ),
                    },
                )
            except Exception:
                pass  # observability must never crash the engine

        attempts = max(0, self.max_retries)

        last_error: Optional[Exception] = None
        for attempt in range(attempts + 1):
            try:
                if use_executor_runtime:
                    return await self._generate_text_via_executor_runtime(
                        messages, model=resolved_model
                    )

                try:
                    await self._ensure_provider(force=True)
                except Exception as provider_exc:
                    if self.executor_runtime:
                        logger.info(
                            "Meeting generation falling back to executor runtime "
                            "because direct LLM provider is unavailable: %s",
                            provider_exc,
                        )
                        return await self._generate_text_via_executor_runtime(
                            messages, model=resolved_model
                        )
                    raise

                return await self._generate_text_via_llm(
                    messages, max_tokens=max_tokens, model=resolved_model
                )
            except Exception as exc:
                last_error = exc
                if _is_non_retriable_runtime_error(exc):
                    # OP-6: Emit structured RuntimeUnavailableEvent before fail-fast
                    self._emit_runtime_unavailable_event(
                        runtime_id=getattr(self, "executor_runtime", None)
                        or "llm_provider",
                        error=str(exc),
                        reason="non_retriable_quota_or_rate_limit",
                    )
                    break
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
        model: Optional[str] = None,
    ) -> str:
        """Generate text directly via the configured LLM provider.

        When the provider supports ``chat_completion_stream``, tokens are
        published to Redis in real-time so the SSE endpoint can relay them
        to the frontend as a typing effect.  Falls back to the original
        non-streaming path when streaming is unavailable.
        """
        call_kwargs = {
            "messages": messages,
            "model": model or self.model_name,
            "temperature": 0.3,
            "max_tokens": max_tokens,
        }

        # ── Streaming path ────────────────────────────────────
        if hasattr(self.provider, "chat_completion_stream"):
            workspace_id = getattr(self.workspace, "id", None) or ""
            session_id = getattr(self.session, "id", None) or ""
            full_text = ""
            try:
                from backend.app.services.cache.async_redis import (
                    publish_meeting_chunk,
                )
                thread_id = getattr(self, "thread_id", None) or getattr(self.session, "thread_id", None) or session_id

                # Publish "stream_start" so the frontend knows a new
                # streaming block is beginning.
                await publish_meeting_chunk(
                    workspace_id,
                    {
                        "type": "stream_start",
                        "session_id": session_id,
                    },
                    thread_id,
                )

                try:
                    sig = inspect.signature(self.provider.chat_completion_stream)
                    allowed = set(sig.parameters.keys())
                    stream_kwargs = {k: v for k, v in call_kwargs.items() if k in allowed}
                    if "messages" not in stream_kwargs:
                        stream_kwargs["messages"] = messages

                    async for chunk_content in self.provider.chat_completion_stream(
                        **stream_kwargs
                    ):
                        full_text += chunk_content
                        await publish_meeting_chunk(
                            workspace_id,
                            {
                                "type": "chunk",
                                "content": chunk_content,
                                "session_id": session_id,
                            },
                            thread_id,
                        )
                finally:
                    # Publish "stream_end" so the frontend can finalise the
                    # accumulated text and clear the streaming buffer.
                    await publish_meeting_chunk(
                        workspace_id,
                        {
                            "type": "stream_end",
                            "session_id": session_id,
                            "full_text": full_text,
                        },
                        thread_id,
                    )

            except Exception as stream_exc:
                logger.warning(
                    "Meeting streaming failed, falling back to non-stream: %s",
                    stream_exc,
                )
                # Fallback: use non-streaming to still produce output
                if not full_text:
                    sig_fb = inspect.signature(self.provider.chat_completion)
                    allowed_fb = set(sig_fb.parameters.keys())
                    kwargs_fb = {
                        k: v for k, v in call_kwargs.items() if k in allowed_fb
                    }
                    if "messages" not in kwargs_fb:
                        kwargs_fb["messages"] = messages
                    full_text = str(await self.provider.chat_completion(**kwargs_fb))

            if not full_text or not full_text.strip():
                raise RuntimeError("Meeting LLM returned empty content")
            return full_text.strip()

        # ── Non-streaming fallback ────────────────────────────
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

        if str(self.executor_runtime).strip().lower() == "codex_cli":
            direct_output = await self._generate_text_via_direct_codex_cli(
                messages, model=model
            )
            if direct_output:
                return direct_output

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
            # OP-6: Emit structured event before fail-fast
            self._emit_runtime_unavailable_event(
                runtime_id=self.executor_runtime,
                error=f"Preferred agent '{self.executor_runtime}' unavailable after 3 attempts",
                reason="executor_runtime_unavailable",
            )
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

        await self._emit_meeting_stage("generating", f"正在透過 {self.executor_runtime} 執行中...")

        result = await self._agent_executor.execute(
            task=task,
            agent_id=self.executor_runtime,
            context_overrides={
                "meeting_session_id": self.session.id,
                "thread_id": self.thread_id,
                "project_id": self.project_id,
                "conversation_context": system_prompt,
                "model": model,  # per-agent model hint for runtime bridge
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

        # ── Simulated streaming for executor runtime ──
        # Push the completed turn result as stream_start → chunk → stream_end
        # so the frontend shows progressive output for each meeting turn.
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
            # Emit the full result as a single chunk
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

    async def _generate_text_via_direct_codex_cli(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        """Execute Codex CLI directly on host, bypassing fragile bridge paths."""
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

        await self._emit_meeting_stage(
            "generating", "正在透過 codex_cli 直接執行中..."
        )

        binary = os.environ.get("CODEX_CLI_PATH", "").strip() or "codex"
        max_attempts = max(
            1,
            int(os.environ.get("MINDSCAPE_CODEX_POOL_MAX_TASK_ATTEMPTS", "3")),
        )
        attempted_runtime_ids: set[str] = set()
        cwd = os.environ.get("HOST_PROJECT_PATH", "").strip() or os.getcwd()
        last_runtime_error = ""
        attempt = 1

        while attempt <= max_attempts:
            auth_bundle = await self._fetch_direct_codex_auth_bundle()
            if isinstance(auth_bundle, dict):
                raw_capacity = (
                    auth_bundle.get("available_quota_scope_count")
                    or auth_bundle.get("available_runtime_count")
                    or 0
                )
                try:
                    bundle_capacity = int(raw_capacity)
                except (TypeError, ValueError):
                    bundle_capacity = 0
                if bundle_capacity > max_attempts:
                    max_attempts = bundle_capacity

            extra_env = auth_bundle.get("env") if isinstance(auth_bundle, dict) else {}
            selected_runtime_id = (
                str(auth_bundle.get("selected_runtime_id") or "").strip()
                if isinstance(auth_bundle, dict)
                else ""
            )

            if attempt > 1 and not selected_runtime_id:
                pool_error = ""
                if isinstance(auth_bundle, dict):
                    pool_error = str(
                        auth_bundle.get("error")
                        or auth_bundle.get("warning")
                        or ""
                    ).strip()
                detail = (
                    f"{last_runtime_error} (pool failover unavailable: {pool_error})"
                    if last_runtime_error and pool_error
                    else last_runtime_error
                    or pool_error
                    or "Codex pool failover did not yield an alternate runtime"
                )
                raise RuntimeError(f"Preferred agent 'codex_cli' failed: {detail}")

            if selected_runtime_id and selected_runtime_id in attempted_runtime_ids:
                detail = (
                    f"{last_runtime_error} (pool reused exhausted runtime {selected_runtime_id})"
                    if last_runtime_error
                    else f"Codex pool reused exhausted runtime {selected_runtime_id}"
                )
                raise RuntimeError(f"Preferred agent 'codex_cli' failed: {detail}")

            progress_message = "正在透過 codex_cli 直接執行中..."
            if attempt > 1:
                progress_message = (
                    f"正在透過 codex_cli 直接執行中（pool failover {attempt}/{max_attempts}）..."
                )
            await self._emit_meeting_stage("generating", progress_message)

            with tempfile.NamedTemporaryFile(
                prefix="meeting_codex_last_",
                suffix=".txt",
                delete=False,
            ) as tmp:
                last_message_path = tmp.name

            cmd = [
                binary,
                "-c",
                'model_reasoning_effort="high"',
                "exec",
                "--skip-git-repo-check",
                "--full-auto",
                "--output-last-message",
                last_message_path,
            ]
            if model:
                cmd.extend(["--model", model])
            cmd.append(task)

            try:
                returncode, stdout_text, stderr_text, output_text, combined_output = (
                    await self._run_direct_codex_cli_subprocess(
                        cmd=cmd,
                        cwd=cwd,
                        last_message_path=last_message_path,
                        extra_env=extra_env if isinstance(extra_env, dict) else None,
                    )
                )
            finally:
                try:
                    os.unlink(last_message_path)
                except OSError:
                    pass

            if returncode == 0 and output_text:
                return output_text

            error_text = (
                stderr_text or combined_output or output_text or "unknown error"
            ).strip()
            if selected_runtime_id and _looks_like_codex_quota_exhaustion(error_text):
                await self._report_direct_codex_runtime_quota_exhausted(
                    selected_runtime_id
                )
            elif selected_runtime_id and _looks_like_codex_auth_failure(error_text):
                await self._report_direct_codex_runtime_auth_failure(
                    selected_runtime_id
                )

            if not _should_retry_direct_codex_runtime_fault(error_text):
                raise RuntimeError(
                    f"Preferred agent 'codex_cli' failed: {error_text}"
                )
            if not selected_runtime_id:
                raise RuntimeError(
                    f"Preferred agent 'codex_cli' failed: {error_text}"
                )

            last_runtime_error = error_text
            attempted_runtime_ids.add(selected_runtime_id)
            if attempt >= max_attempts:
                raise RuntimeError(
                    f"Preferred agent 'codex_cli' failed: {error_text}"
                )
            logger.warning(
                "Meeting direct codex runtime %s hit retryable fault; attempting pool failover (%d/%d)",
                selected_runtime_id,
                attempt,
                max_attempts,
            )
            attempt += 1

        raise RuntimeError(
            "Preferred agent 'codex_cli' failed: Codex pool failover exhausted without a successful execution"
        )

    async def _fetch_direct_codex_auth_bundle(self) -> Dict[str, Any]:
        def _fallback_bundle() -> Dict[str, Any]:
            api_key = os.environ.get("OPENAI_API_KEY", "").strip()
            env = {"OPENAI_API_KEY": api_key} if api_key else {}
            return {"auth_mode": "env_fallback", "env": env}

        try:
            from backend.app.services.codex_pool_service import CodexPoolService
            from backend.app.services.codex_workspace_resolver import (
                CodexWorkspaceResolver,
            )

            selection = None
            workspace_id = str(getattr(getattr(self, "workspace", None), "id", "") or "")
            if workspace_id:
                try:
                    selection = await asyncio.to_thread(
                        CodexWorkspaceResolver().resolve,
                        workspace_id=workspace_id,
                    )
                except ValueError:
                    logger.debug(
                        "Workspace-scoped Codex pool selection not configured for meeting workspace %s",
                        workspace_id,
                    )

            preferred_runtime_id = (
                selection.selected_runtime_id if selection else None
            )
            allow_fallback = not bool(preferred_runtime_id)
            pool_result = await asyncio.to_thread(
                CodexPoolService().get_active_auth_bundle,
                preferred_runtime_id=preferred_runtime_id,
                allow_fallback=allow_fallback,
            )
            if "env" in pool_result and selection:
                pool_result.update(
                    {
                        "requested_workspace_id": selection.requested_workspace_id,
                        "effective_workspace_id": selection.effective_workspace_id,
                        "auth_workspace_id": selection.auth_workspace_id,
                        "source_workspace_id": selection.source_workspace_id,
                        "selection_reason": selection.selection_reason,
                        "selection_trace": list(selection.trace),
                    }
                )
            return pool_result
        except Exception:
            logger.exception("Meeting direct Codex pool lookup failed")
            return _fallback_bundle()

    async def _report_direct_codex_runtime_quota_exhausted(
        self,
        runtime_id: str,
    ) -> None:
        if not runtime_id:
            return
        try:
            from backend.app.services.codex_pool_service import CodexPoolService

            await asyncio.to_thread(
                CodexPoolService().report_quota_exhausted,
                runtime_id,
            )
        except Exception:
            logger.exception(
                "Failed to report direct codex quota exhaustion for runtime %s",
                runtime_id,
            )

    async def _report_direct_codex_runtime_auth_failure(
        self,
        runtime_id: str,
        *,
        error_code: str = "401",
    ) -> None:
        if not runtime_id:
            return
        try:
            from backend.app.services.codex_pool_service import CodexPoolService

            await asyncio.to_thread(
                CodexPoolService().report_auth_failure,
                runtime_id,
                error_code=error_code,
            )
        except Exception:
            logger.exception(
                "Failed to report direct codex auth failure for runtime %s",
                runtime_id,
            )

    async def _run_direct_codex_cli_subprocess(
        self,
        *,
        cmd: List[str],
        cwd: str,
        last_message_path: str,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> tuple[int, str, str, str, str]:
        env = os.environ.copy()
        if extra_env:
            env.update(
                {
                    str(key): str(value)
                    for key, value in extra_env.items()
                    if value is not None and str(value) != ""
                }
            )

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
        except Exception:
            proc.kill()
            await proc.wait()
            raise

        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        output_text = ""
        try:
            with open(last_message_path, "r", encoding="utf-8") as fh:
                output_text = fh.read().strip()
        except Exception:
            output_text = ""

        if not output_text:
            output_text = stdout_text
        combined_output = "\n".join(
            part for part in (output_text, stdout_text, stderr_text) if part
        ).strip()
        return proc.returncode, stdout_text, stderr_text, output_text, combined_output

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

    async def _ensure_provider(self, force: bool = False) -> None:
        """Initialize the LLM provider if not already set."""
        if self.provider:
            return
        # Skip direct LLM provider init when executor_runtime is available —
        # unless the caller explicitly forces direct LLM routing.
        if self.executor_runtime and not force:
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

    def _emit_runtime_unavailable_event(
        self,
        runtime_id: str,
        error: str,
        reason: str,
    ) -> None:
        """OP-6: Emit structured RuntimeUnavailableEvent for observability.

        Enables dashboards and alerting to track runtime failures without
        log parsing.  Fallback decisions happen ABOVE the meeting engine,
        per v3 constraint.
        """
        try:
            self._emit_event(
                "runtime_unavailable",
                payload={
                    "runtime_id": runtime_id,
                    "error": error[:500],
                    "reason": reason,
                    "session_id": getattr(getattr(self, "session", None), "id", None),
                    "model_name": getattr(self, "model_name", None),
                },
            )
        except Exception:
            pass  # observability must never crash the engine
