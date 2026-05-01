"""
Meeting engine text generation mixin.

Routes all meeting text generation through the bound executor runtime.
"""

import asyncio
import logging
import os
import tempfile
from typing import Any, Dict, List, Optional

from backend.app.services.external_agents.bridge.codex_cli_runner import (
    DEFAULT_CLI_STALL_TIMEOUT_SECONDS,
    looks_like_codex_auth_failure as _looks_like_codex_auth_failure,
    looks_like_codex_quota_exhaustion as _looks_like_codex_quota_exhaustion,
    resolve_codex_cli_binary as _resolve_codex_cli_binary,
    resolve_codex_cli_cwd as _resolve_codex_cli_cwd,
    run_codex_cli_subprocess as _run_shared_codex_cli_subprocess,
    sanitize_codex_last_message as _sanitize_direct_codex_last_message,
    should_retry_codex_runtime_fault as _should_retry_codex_runtime_fault,
)

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


class MeetingGenerationMixin:
    """Mixin providing LLM text generation methods for MeetingEngine."""

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
                When set, CapabilityProfileResolver resolves it to a model.
            model: Optional explicit model override. Takes precedence over
                capability_profile resolution. Used by MeetingLLMAdapter and
                external consumers.
            use_executor_runtime: Retained for compatibility. Meeting generation
                always requires a bound executor runtime and never uses a direct
                provider path.
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
            and self._meeting_codex_direct_enabled()
        ):
            return await self._generate_text_via_direct_codex_cli(
                messages, model=model
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

        result = await self._agent_executor.execute(
            task=task,
            agent_id=self.executor_runtime,
            context_overrides=context_overrides,
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

    @staticmethod
    def _meeting_codex_direct_enabled() -> bool:
        raw = os.environ.get("MINDSCAPE_MEETING_CODEX_DIRECT", "").strip().lower()
        return raw in {"1", "true", "yes", "on"}

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

        binary = _resolve_codex_cli_binary(os.environ.get("CODEX_CLI_PATH", "").strip())
        cwd = _resolve_codex_cli_cwd(os.environ.get("HOST_PROJECT_PATH", "").strip())
        attempted_runtime_ids: set[str] = set()
        max_attempts = 1
        attempt = 1
        last_runtime_error = ""

        while attempt <= max_attempts:
            auth_bundle = await self._fetch_direct_codex_auth_bundle()
            pool_error = ""
            if isinstance(auth_bundle, dict):
                pool_error = str(
                    auth_bundle.get("error")
                    or auth_bundle.get("warning")
                    or ""
                ).strip()
                attempt_capacity_raw = (
                    auth_bundle.get("available_quota_scope_count")
                    or auth_bundle.get("available_runtime_count")
                    or 0
                )
                try:
                    max_attempts = max(max_attempts, int(attempt_capacity_raw))
                except (TypeError, ValueError):
                    pass
            if pool_error:
                if attempt > 1 and last_runtime_error:
                    raise RuntimeError(
                        f"Preferred agent 'codex_cli' failed: "
                        f"{last_runtime_error} (pool failover unavailable: {pool_error})"
                    )
                raise RuntimeError(f"Preferred agent 'codex_cli' failed: {pool_error}")

            extra_env = auth_bundle.get("env") if isinstance(auth_bundle, dict) else {}
            effective_workspace_id = (
                str(auth_bundle.get("effective_workspace_id") or "").strip()
                if isinstance(auth_bundle, dict)
                else ""
            )
            selected_runtime_id = (
                str(auth_bundle.get("selected_runtime_id") or "").strip()
                if isinstance(auth_bundle, dict)
                else ""
            )
            if not selected_runtime_id:
                if attempt > 1 and last_runtime_error:
                    raise RuntimeError(
                        f"Preferred agent 'codex_cli' failed: "
                        f"{last_runtime_error} (pool failover did not yield an alternate runtime)"
                    )
                raise RuntimeError(
                    "Preferred agent 'codex_cli' failed: no concrete Codex pool runtime is bound"
                )
            if selected_runtime_id in attempted_runtime_ids:
                raise RuntimeError(
                    f"Preferred agent 'codex_cli' failed: "
                    f"{last_runtime_error or 'pool failover unavailable'} "
                    f"(pool reused exhausted runtime {selected_runtime_id})"
                )

            progress_message = f"正在透過 codex_cli 直接執行中（runtime={selected_runtime_id}）..."
            if attempt > 1:
                progress_message = (
                    "正在透過 codex_cli 切換下一個 pool runtime 重試中"
                    f"（{attempt}/{max_attempts}, runtime={selected_runtime_id}）..."
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
            model_hint = self._executor_model_hint("codex_cli", model)
            if model_hint:
                cmd.extend(["--model", model_hint])
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
                if selected_runtime_id:
                    await self._report_direct_codex_runtime_success(
                        selected_runtime_id,
                    )
                return output_text

            error_text = (
                combined_output or stderr_text or output_text or "unknown error"
            ).strip()
            quota_fault = _looks_like_codex_quota_exhaustion(error_text)
            auth_fault = _looks_like_codex_auth_failure(error_text)
            retryable_runtime_fault = _should_retry_codex_runtime_fault(error_text)
            auth_error_code = self._extract_direct_codex_auth_error_code(error_text)
            if quota_fault:
                await self._report_direct_codex_runtime_quota_exhausted(
                    selected_runtime_id,
                    workspace_id=effective_workspace_id or getattr(self.workspace, "id", ""),
                )
            elif auth_fault or retryable_runtime_fault:
                await self._report_direct_codex_runtime_auth_failure(
                    selected_runtime_id,
                    error_code=(
                        "timeout"
                        if retryable_runtime_fault and not auth_fault
                        else auth_error_code
                    ),
                    workspace_id=effective_workspace_id or getattr(self.workspace, "id", ""),
                )
            if selected_runtime_id:
                self._bound_direct_codex_auth_bundle = None

            if not (quota_fault or auth_fault or retryable_runtime_fault):
                raise RuntimeError(
                    f"Preferred agent 'codex_cli' failed on bound runtime "
                    f"'{selected_runtime_id}': {error_text}"
                )

            last_runtime_error = error_text
            attempted_runtime_ids.add(selected_runtime_id)
            if attempt >= max_attempts:
                raise RuntimeError(
                    f"Preferred agent 'codex_cli' failed on bound runtime "
                    f"'{selected_runtime_id}': {error_text}"
                )
            attempt += 1

    def _direct_codex_lease_identity(self) -> tuple[Optional[str], Optional[str]]:
        session_id = str(getattr(getattr(self, "session", None), "id", "") or "").strip()
        if not session_id:
            return None, None
        return "meeting_session", session_id

    @staticmethod
    def _binding_snapshot_matches_direct_codex_lease(
        binding_snapshot: Any,
        *,
        lease_owner_type: Optional[str],
        lease_owner_id: Optional[str],
        runtime_id: Optional[str],
    ) -> bool:
        if not isinstance(binding_snapshot, dict):
            return False
        return (
            str(binding_snapshot.get("binding_state") or "").strip().lower() != "faulted"
            and str(binding_snapshot.get("lease_state") or "").strip().lower() == "active"
            and str(binding_snapshot.get("lease_owner_type") or "").strip()
            == str(lease_owner_type or "").strip()
            and str(binding_snapshot.get("lease_owner_id") or "").strip()
            == str(lease_owner_id or "").strip()
            and str(binding_snapshot.get("lease_runtime_id") or "").strip()
            == str(runtime_id or "").strip()
        )

    async def _fetch_direct_codex_auth_bundle(self) -> Dict[str, Any]:
        try:
            from backend.app.services.codex_pool_service import CodexPoolService
            from backend.app.services.codex_pool_admission_service import (
                CodexPoolAdmissionService,
            )
            from backend.app.services.executor_binding_service import (
                ExecutorBindingService,
            )
            from backend.app.services.executor_route_resolver import (
                ExecutorRouteResolver,
            )

            selection = None
            binding_service = ExecutorBindingService()
            workspace_id = str(getattr(getattr(self, "workspace", None), "id", "") or "")
            lease_owner_type, lease_owner_id = self._direct_codex_lease_identity()
            cached_bundle = getattr(self, "_bound_direct_codex_auth_bundle", None)
            if isinstance(cached_bundle, dict) and cached_bundle.get("selected_runtime_id"):
                cached_runtime_id = str(
                    cached_bundle.get("selected_runtime_id") or ""
                ).strip()
                if not (workspace_id and lease_owner_type and lease_owner_id):
                    return dict(cached_bundle)
                binding_snapshot = await asyncio.to_thread(
                    binding_service.load_binding_snapshot,
                    workspace_id=workspace_id,
                    surface="codex_cli",
                )
                if self._binding_snapshot_matches_direct_codex_lease(
                    binding_snapshot,
                    lease_owner_type=lease_owner_type,
                    lease_owner_id=lease_owner_id,
                    runtime_id=cached_runtime_id,
                ):
                    return dict(cached_bundle)
                self._bound_direct_codex_auth_bundle = None

            if workspace_id:
                try:
                    selection = await asyncio.to_thread(
                        ExecutorRouteResolver().resolve,
                        surface="codex_cli",
                        workspace_id=workspace_id,
                    )
                except ValueError:
                    logger.debug(
                        "Workspace-scoped Codex pool selection not configured for meeting workspace %s",
                        workspace_id,
                    )

            preference = (
                await asyncio.to_thread(
                    binding_service.resolve_pool_preference,
                    selection=selection,
                    lease_owner_type=lease_owner_type,
                    lease_owner_id=lease_owner_id,
                )
                if selection
                else {
                    "preferred_runtime_id": None,
                    "allow_runtime_substitution": False,
                    "preference_source": "no_bound_runtime",
                    "binding_runtime_id": None,
                    "binding_state": None,
                    "lease_runtime_id": None,
                    "lease_state": None,
                }
            )
            preferred_runtime_id = preference.get("preferred_runtime_id")
            allow_runtime_substitution = bool(
                preference.get("allow_runtime_substitution", False)
            )
            preference_source = str(preference.get("preference_source") or "no_bound_runtime")
            pool_service = CodexPoolService()
            admission = await asyncio.to_thread(
                CodexPoolAdmissionService().evaluate_execution_admission,
                preferred_runtime_id=preferred_runtime_id,
                allow_runtime_substitution=allow_runtime_substitution,
            )
            if not admission.admissible:
                if (
                    preference_source == "session_lease"
                    and selection
                    and workspace_id
                    and lease_owner_type
                    and lease_owner_id
                ):
                    try:
                        await asyncio.to_thread(
                            binding_service.clear_runtime_lease,
                            workspace_id=workspace_id,
                            surface=selection.surface,
                            lease_owner_type=lease_owner_type,
                            lease_owner_id=lease_owner_id,
                            runtime_id=preferred_runtime_id,
                            reason=f"admission:{admission.reason}",
                        )
                    except Exception:
                        logger.warning(
                            "Failed to clear stale meeting runtime lease for workspace %s",
                            workspace_id,
                            exc_info=True,
                        )
                return {
                    "error": admission.blocker_message(),
                    "admission": admission.to_payload(),
                    "preferred_runtime_id": preferred_runtime_id,
                    "binding_runtime_id": preference.get("binding_runtime_id"),
                    "binding_state": preference.get("binding_state"),
                    "preference_source": preference_source,
                }
            pool_result = await asyncio.to_thread(
                pool_service.get_active_auth_bundle,
                preferred_runtime_id=preferred_runtime_id,
                allow_runtime_substitution=allow_runtime_substitution,
            )
            if "env" in pool_result and preference_source == "session_lease":
                selected_runtime_id = str(
                    pool_result.get("selected_runtime_id") or ""
                ).strip()
                if (
                    selected_runtime_id
                    and preferred_runtime_id
                    and selected_runtime_id != preferred_runtime_id
                ):
                    pool_result = {
                        "error": (
                            "Preferred Codex runtime mismatch under fail-closed policy; "
                            "pool rebinding is disabled."
                        )
                    }
            if "env" in pool_result and selection:
                selected_runtime_id = str(
                    pool_result.get("selected_runtime_id") or ""
                ).strip()
                pool_result.update(
                    {
                        "preferred_runtime_id": selection.preferred_runtime_id,
                        "binding_runtime_id": preference.get("binding_runtime_id"),
                        "binding_state": preference.get("binding_state"),
                        "preference_source": preference_source,
                        "policy_mode": selection.policy_mode,
                        "requested_workspace_id": selection.requested_workspace_id,
                        "effective_workspace_id": selection.effective_workspace_id,
                        "auth_workspace_id": selection.auth_workspace_id,
                        "source_workspace_id": selection.source_workspace_id,
                        "selection_reason": selection.selection_reason,
                        "selection_trace": list(selection.trace),
                    }
                )
                try:
                    await asyncio.to_thread(
                        binding_service.record_route_resolution,
                        selection=selection,
                        resolved_runtime_id=selected_runtime_id,
                    )
                except Exception:
                    logger.warning(
                        "Failed to persist meeting Codex executor binding for workspace %s",
                        selection.effective_workspace_id,
                        exc_info=True,
                    )
                if workspace_id and lease_owner_type and lease_owner_id and selected_runtime_id:
                    try:
                        await asyncio.to_thread(
                            binding_service.record_runtime_lease,
                            workspace_id=workspace_id,
                            surface=selection.surface,
                            runtime_id=selected_runtime_id,
                            lease_owner_type=lease_owner_type,
                            lease_owner_id=lease_owner_id,
                        )
                    except Exception:
                        logger.warning(
                            "Failed to persist meeting runtime lease for workspace %s",
                            workspace_id,
                            exc_info=True,
                        )
            if (
                str(getattr(self, "executor_runtime", "") or "").strip().lower()
                == "codex_cli"
            ):
                selected_runtime_id = str(
                    pool_result.get("selected_runtime_id") or ""
                ).strip()
                if not selected_runtime_id:
                    reason = str(
                        pool_result.get("error")
                        or "Codex workspace route did not resolve a concrete pool runtime"
                    ).strip()
                    return {"error": reason}
                self._bound_direct_codex_auth_bundle = dict(pool_result)
            return pool_result
        except Exception:
            logger.exception("Meeting direct Codex pool lookup failed")
            return {
                "error": "Meeting codex route resolution failed before a runtime could be bound"
            }

    async def _report_direct_codex_runtime_quota_exhausted(
        self,
        runtime_id: str,
        *,
        workspace_id: str = "",
    ) -> None:
        if not runtime_id:
            return
        try:
            from backend.app.services.codex_pool_service import CodexPoolService
            from backend.app.services.executor_binding_service import (
                ExecutorBindingService,
            )

            await asyncio.to_thread(
                CodexPoolService().report_quota_exhausted,
                runtime_id,
            )
            if workspace_id:
                await asyncio.to_thread(
                    ExecutorBindingService().record_runtime_fault,
                    workspace_id=workspace_id,
                    surface="codex_cli",
                    runtime_id=runtime_id,
                    error_code="429",
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
        workspace_id: str = "",
    ) -> None:
        if not runtime_id:
            return
        try:
            from backend.app.services.codex_pool_service import CodexPoolService
            from backend.app.services.executor_binding_service import (
                ExecutorBindingService,
            )

            await asyncio.to_thread(
                CodexPoolService().report_auth_failure,
                runtime_id,
                error_code=error_code,
            )
            if workspace_id:
                await asyncio.to_thread(
                    ExecutorBindingService().record_runtime_fault,
                    workspace_id=workspace_id,
                    surface="codex_cli",
                    runtime_id=runtime_id,
                    error_code=error_code,
                )
        except Exception:
            logger.exception(
                "Failed to report direct codex auth failure for runtime %s",
                runtime_id,
            )

    async def _report_direct_codex_runtime_success(
        self,
        runtime_id: str,
    ) -> None:
        if not runtime_id:
            return
        try:
            from backend.app.services.codex_pool_service import CodexPoolService

            await asyncio.to_thread(
                CodexPoolService().report_runtime_success,
                runtime_id,
            )
        except Exception:
            logger.exception(
                "Failed to report direct codex success for runtime %s",
                runtime_id,
            )

    @staticmethod
    def _extract_direct_codex_auth_error_code(error_text: str) -> str:
        normalized = str(error_text or "").strip().lower()
        if "deactivated_workspace" in normalized:
            return "deactivated_workspace"
        if "403" in normalized:
            return "403"
        return "401"

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

        stall_timeout_raw = os.environ.get(
            "MINDSCAPE_CLI_STALL_TIMEOUT_SECONDS",
            str(DEFAULT_CLI_STALL_TIMEOUT_SECONDS),
        ).strip()
        try:
            stall_timeout = max(5.0, float(stall_timeout_raw))
        except ValueError:
            stall_timeout = DEFAULT_CLI_STALL_TIMEOUT_SECONDS

        try:
            result = await _run_shared_codex_cli_subprocess(
                cmd=cmd,
                cwd=cwd,
                env=env,
                last_message_path=last_message_path,
                execution_id=str(getattr(self.session, "id", "meeting-direct-codex")),
                timeout=300.0,
                stall_timeout=min(300.0, stall_timeout),
            )
        except asyncio.TimeoutError as exc:
            error_text = str(exc).strip() or "codex_cli subprocess stalled without output"
            return (1, "", "", "", error_text)
        return (
            result.returncode,
            result.stdout_text,
            result.stderr_text,
            result.output_text,
            result.synthesized_error or result.combined_output,
        )

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
