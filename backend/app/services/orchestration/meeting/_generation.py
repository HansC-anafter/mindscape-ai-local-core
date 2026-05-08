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
    resolve_codex_cli_binary as _resolve_codex_cli_binary,
    resolve_codex_cli_cwd as _resolve_codex_cli_cwd,
    run_codex_cli_subprocess as _run_shared_codex_cli_subprocess,
    sanitize_codex_last_message as _sanitize_direct_codex_last_message,
    should_use_direct_codex_cli_subprocess as _should_use_direct_codex_cli_subprocess,
)
from backend.app.services.codex_runtime_failure_classifier import (
    classify_codex_cli_runtime_failure as _classify_codex_cli_runtime_failure,
    should_retry_codex_runtime_fault as _should_retry_codex_runtime_fault,
)

logger = logging.getLogger(__name__)


class CodexPoolAdmissionBlockedError(RuntimeError):
    pass


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

_RETRYABLE_RUNTIME_PATTERNS = (
    "no websocket client connected",
    "websocket client",
    "ws client",
    "not connected",
    "connection closed",
    "temporarily unavailable",
    "unavailable",
    "timed out",
    "timeout",
    "no available codex runtimes in pool",
    "codex pool admission blocked",
    "no_runnable_runtimes",
    "preferred codex runtime unavailable",
)

_CODEX_POOL_RETRYABLE_RUNTIME_PATTERNS = (
    "you've hit your usage limit",
    "usage limit",
    "rate limit",
    "quota exceeded",
    "quota exhausted",
    "insufficient quota",
    "too many requests",
    "resource_exhausted",
    "resource exhausted",
    "deactivated_workspace",
    'code":"deactivated_workspace"',
    "access token could not be refreshed",
    "refresh token was already used",
    "please log out and sign in again",
)

_EXECUTOR_RUNTIME_RETRY_DELAYS_SECONDS = (2.0, 4.0, 8.0, 16.0, 30.0)


def _is_non_retriable_runtime_error(exc: Exception) -> bool:
    """Return True when the runtime error should fail fast.

    The Gemini CLI runtime bridge already performs one internal refresh/retry
    for auth/quota faults. If the error still bubbles up here, retrying the
    whole meeting turn just burns additional budget and delays failure.
    """
    text = str(exc or "").lower()
    return any(pattern in text for pattern in _NON_RETRIABLE_RUNTIME_PATTERNS)


def _is_retryable_runtime_error_text(error: Optional[str]) -> bool:
    text = str(error or "").lower()
    if not text:
        return False
    if any(pattern in text for pattern in _NON_RETRIABLE_RUNTIME_PATTERNS):
        return False
    return any(pattern in text for pattern in _RETRYABLE_RUNTIME_PATTERNS)


def _is_codex_pool_retryable_runtime_error_text(error: Optional[str]) -> bool:
    text = str(error or "").lower()
    if not text:
        return False
    if _is_retryable_runtime_error_text(text):
        return True
    return any(pattern in text for pattern in _CODEX_POOL_RETRYABLE_RUNTIME_PATTERNS)


def _is_runtime_error_retryable_for_executor(
    executor_runtime: Optional[str],
    error: Optional[str],
) -> bool:
    if str(executor_runtime or "").strip().lower() == "codex_cli":
        return _is_codex_pool_retryable_runtime_error_text(error)
    return _is_retryable_runtime_error_text(error)


def _is_runtime_error_non_retriable_for_executor(
    executor_runtime: Optional[str],
    exc: Exception,
) -> bool:
    if isinstance(exc, CodexPoolAdmissionBlockedError):
        return True
    if (
        str(executor_runtime or "").strip().lower() == "codex_cli"
        and _is_codex_pool_retryable_runtime_error_text(str(exc))
    ):
        return False
    return _is_non_retriable_runtime_error(exc)


def _executor_runtime_attempt_count() -> int:
    raw = os.environ.get("MINDSCAPE_MEETING_EXECUTOR_RUNTIME_ATTEMPTS", "").strip()
    if not raw:
        return 6
    try:
        return max(1, int(raw))
    except ValueError:
        return 6


def _executor_runtime_retry_delay(attempt_index: int) -> float:
    if attempt_index < len(_EXECUTOR_RUNTIME_RETRY_DELAYS_SECONDS):
        return _EXECUTOR_RUNTIME_RETRY_DELAYS_SECONDS[attempt_index]
    return _EXECUTOR_RUNTIME_RETRY_DELAYS_SECONDS[-1]


def _codex_pool_wait_attempt_count() -> int:
    raw = os.environ.get("MINDSCAPE_CODEX_POOL_WAIT_ATTEMPTS", "6").strip()
    try:
        return max(1, min(12, int(raw)))
    except ValueError:
        return 6


def _codex_pool_admission_error_text(admission: Dict[str, Any]) -> str:
    reason = str(admission.get("reason") or "no_runnable_runtimes").strip()
    runnable = admission.get("runnable_runtime_count", 0)
    healthy = admission.get("healthy_runtime_count", 0)
    probation = admission.get("probation_runtime_count", 0)
    quarantined = admission.get("quarantined_runtime_count", 0)
    cooldown = admission.get("cooldown_runtime_count", 0)
    failures = admission.get("failure_counts")
    failure_text = f", failures={failures}" if failures else ""
    return (
        "Codex pool admission blocked: "
        f"{reason} "
        f"(runnable={runnable}, healthy={healthy}, probation={probation}, "
        f"quarantined={quarantined}, cooldown={cooldown}{failure_text})"
    )


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
                if _is_runtime_error_non_retriable_for_executor(
                    getattr(self, "executor_runtime", None),
                    exc,
                ):
                    reason = (
                        "codex_pool_admission_blocked"
                        if isinstance(exc, CodexPoolAdmissionBlockedError)
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
            and _should_use_direct_codex_cli_subprocess()
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

        attempts = _executor_runtime_attempt_count()
        result = None
        for attempt in range(attempts):
            admission = await self._evaluate_executor_runtime_admission()
            if not bool(admission.get("admissible", True)):
                error_text = _codex_pool_admission_error_text(admission)
                if (
                    attempt < attempts - 1
                    and _is_runtime_error_retryable_for_executor(
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
                    await asyncio.sleep(_executor_runtime_retry_delay(attempt))
                    continue
                self._emit_runtime_unavailable_event(
                    runtime_id=self.executor_runtime,
                    error=f"Preferred agent '{self.executor_runtime}' failed: {error_text}",
                    reason="codex_pool_admission_blocked",
                    metadata={"codex_pool_admission": admission},
                )
                raise CodexPoolAdmissionBlockedError(
                    f"Preferred agent '{self.executor_runtime}' failed: {error_text}"
                )

            result = await self._agent_executor.execute(
                task=task,
                agent_id=self.executor_runtime,
                context_overrides=context_overrides,
            )
            if result.success:
                break

            # Surface clarification requests as decision events, not fatal errors
            if result.needs_clarification:
                await self._emit_clarification_event(result.clarification_questions)
                return (
                    f"[Meeting paused] Awaiting user confirmation: "
                    f"{'; '.join(result.clarification_questions)}"
                )

            error_text = result.error or "unknown error"
            if (
                attempt < attempts - 1
                and _is_runtime_error_retryable_for_executor(
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
                await asyncio.sleep(_executor_runtime_retry_delay(attempt))
                continue

            self._emit_runtime_unavailable_event(
                runtime_id=self.executor_runtime,
                error=f"Preferred agent '{self.executor_runtime}' failed: {error_text}",
                reason=(
                    "executor_runtime_transient_unavailable"
                    if _is_runtime_error_retryable_for_executor(
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

    async def _generate_text_via_direct_codex_cli(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
    ) -> str:
        """Execute Codex CLI through the pool-managed runtime path."""
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
        excluded_quota_scope_keys: set[str] = set()
        max_attempts = 1
        attempt = 1
        pool_wait_attempts = _codex_pool_wait_attempt_count()
        pool_wait_index = 0
        last_runtime_error = ""

        while attempt <= max_attempts:
            auth_bundle = await self._fetch_direct_codex_auth_bundle(
                excluded_runtime_ids=set(attempted_runtime_ids),
                excluded_quota_scope_keys=set(excluded_quota_scope_keys),
            )
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
                if (
                    _is_retryable_runtime_error_text(pool_error)
                    and pool_wait_index < pool_wait_attempts - 1
                ):
                    logger.warning(
                        "Codex pool temporarily unavailable for meeting turn "
                        "(wait %d/%d): %s",
                        pool_wait_index + 1,
                        pool_wait_attempts,
                        pool_error,
                    )
                    await asyncio.sleep(_executor_runtime_retry_delay(pool_wait_index))
                    pool_wait_index += 1
                    continue
                if (
                    "codex pool admission blocked" in pool_error.lower()
                    or "no_runnable_runtimes" in pool_error.lower()
                ):
                    raise CodexPoolAdmissionBlockedError(
                        f"Preferred agent 'codex_cli' failed: {pool_error}"
                    )
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
                    f"(pool_reused_excluded_runtime: pool reused exhausted runtime "
                    f"{selected_runtime_id})"
                )
            selected_quota_scope_key = (
                str(auth_bundle.get("quota_scope_key") or "").strip()
                if isinstance(auth_bundle, dict)
                else ""
            )
            if selected_quota_scope_key and selected_quota_scope_key in excluded_quota_scope_keys:
                raise RuntimeError(
                    f"Preferred agent 'codex_cli' failed: "
                    f"{last_runtime_error or 'pool failover unavailable'} "
                    f"(pool_reused_excluded_quota_scope: {selected_quota_scope_key})"
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
                "--sandbox",
                "workspace-write",
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
            runtime_fault = _classify_codex_cli_runtime_failure(error_text)
            fault_kind = str(runtime_fault.get("fault_kind") or "runtime").strip()
            fault_error_code = str(
                runtime_fault.get("error_code") or "runtime_error"
            ).strip()
            quota_fault = fault_kind == "quota"
            auth_fault = fault_kind == "auth"
            retryable_runtime_fault = _should_retry_codex_runtime_fault(error_text)
            auth_error_code = self._extract_direct_codex_auth_error_code(error_text)
            if quota_fault:
                await self._report_direct_codex_runtime_quota_exhausted(
                    selected_runtime_id,
                    workspace_id=effective_workspace_id or getattr(self.workspace, "id", ""),
                    error_text=error_text,
                )
            elif auth_fault or retryable_runtime_fault:
                await self._report_direct_codex_runtime_auth_failure(
                    selected_runtime_id,
                    error_code=(
                        "timeout"
                        if retryable_runtime_fault and not auth_fault
                        else (auth_error_code or fault_error_code)
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
            if quota_fault:
                quota_scope_key = selected_quota_scope_key or f"runtime:{selected_runtime_id}"
                excluded_quota_scope_keys.add(quota_scope_key)
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

    async def _fetch_direct_codex_auth_bundle(
        self,
        *,
        excluded_runtime_ids: Optional[set[str]] = None,
        excluded_quota_scope_keys: Optional[set[str]] = None,
    ) -> Dict[str, Any]:
        try:
            from backend.app.services.codex_pool_runtime_router import (
                resolve_codex_pool_runtime_bundle,
            )
            from backend.app.services.executor_binding_service import (
                ExecutorBindingService,
            )

            binding_service = ExecutorBindingService()
            workspace_id = str(getattr(getattr(self, "workspace", None), "id", "") or "")
            lease_owner_type, lease_owner_id = self._direct_codex_lease_identity()
            normalized_excluded_runtime_ids = {
                str(runtime_id).strip()
                for runtime_id in (excluded_runtime_ids or set())
                if str(runtime_id).strip()
            }
            normalized_excluded_quota_scope_keys = {
                str(scope_key).strip()
                for scope_key in (excluded_quota_scope_keys or set())
                if str(scope_key).strip()
            }
            cached_bundle = getattr(self, "_bound_direct_codex_auth_bundle", None)
            if isinstance(cached_bundle, dict) and cached_bundle.get("selected_runtime_id"):
                cached_runtime_id = str(
                    cached_bundle.get("selected_runtime_id") or ""
                ).strip()
                cached_quota_scope_key = str(
                    cached_bundle.get("quota_scope_key") or ""
                ).strip()
                cached_probe_state = str(
                    cached_bundle.get("probe_state") or ""
                ).strip().lower()
                cached_probe_success_at = str(
                    cached_bundle.get("last_probe_success_at") or ""
                ).strip()
                if (
                    cached_runtime_id in normalized_excluded_runtime_ids
                    or (
                        cached_quota_scope_key
                        and cached_quota_scope_key in normalized_excluded_quota_scope_keys
                    )
                    or cached_probe_state != "available"
                    or not cached_probe_success_at
                ):
                    self._bound_direct_codex_auth_bundle = None
                elif not (workspace_id and lease_owner_type and lease_owner_id):
                    return dict(cached_bundle)
                else:
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

            pool_result = await resolve_codex_pool_runtime_bundle(
                workspace_id=workspace_id,
                lease_owner_type=lease_owner_type,
                lease_owner_id=lease_owner_id,
                excluded_runtime_ids=normalized_excluded_runtime_ids,
                excluded_quota_scope_keys=normalized_excluded_quota_scope_keys,
                require_probe_available=True,
                fail_closed_session_lease=False,
                record_runtime_lease=True,
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
                    if isinstance(pool_result, dict):
                        result = dict(pool_result)
                        result["error"] = reason
                        return result
                    return {"error": reason}
                selected_quota_scope_key = str(
                    pool_result.get("quota_scope_key") or ""
                ).strip()
                if selected_runtime_id in normalized_excluded_runtime_ids:
                    result = dict(pool_result)
                    result["error"] = (
                        "pool_reused_excluded_runtime: Codex pool resolver returned "
                        f"excluded runtime {selected_runtime_id}"
                    )
                    return result
                if (
                    selected_quota_scope_key
                    and selected_quota_scope_key in normalized_excluded_quota_scope_keys
                ):
                    result = dict(pool_result)
                    result["error"] = (
                        "pool_reused_excluded_quota_scope: Codex pool resolver returned "
                        f"excluded quota scope {selected_quota_scope_key}"
                    )
                    return result
                probe_state = str(pool_result.get("probe_state") or "").strip().lower()
                last_probe_success_at = str(
                    pool_result.get("last_probe_success_at") or ""
                ).strip()
                if probe_state != "available" or not last_probe_success_at:
                    result = dict(pool_result)
                    result["error"] = (
                        "Codex pool admission blocked: probe_state_unavailable "
                        f"(runtime={selected_runtime_id}, probe_state={probe_state or 'missing'})"
                    )
                    return result
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
        error_text: str = "",
    ) -> None:
        if not runtime_id:
            return
        try:
            from backend.app.services.codex_pool_runtime_router import (
                report_codex_pool_runtime_fault,
            )

            await report_codex_pool_runtime_fault(
                runtime_id=runtime_id,
                fault_kind="quota",
                workspace_id=workspace_id,
                error_code="429",
                error_text=error_text,
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
            from backend.app.services.codex_pool_runtime_router import (
                report_codex_pool_runtime_fault,
            )

            await report_codex_pool_runtime_fault(
                runtime_id=runtime_id,
                fault_kind="auth",
                workspace_id=workspace_id,
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
            from backend.app.services.codex_pool_runtime_router import (
                report_codex_pool_runtime_success,
            )

            await report_codex_pool_runtime_success(runtime_id=runtime_id)
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
        if "refresh token was already used" in normalized:
            return "stale_refresh_token"
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
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """OP-6: Emit structured RuntimeUnavailableEvent for observability.

        Enables dashboards and alerting to track runtime failures without
        log parsing.  Fallback decisions happen ABOVE the meeting engine,
        per v3 constraint.
        """
        try:
            payload = {
                "runtime_id": runtime_id,
                "error": error[:500],
                "reason": reason,
                "session_id": getattr(getattr(self, "session", None), "id", None),
                "model_name": getattr(self, "model_name", None),
            }
            if metadata:
                payload.update(metadata)
            self._emit_event(
                "runtime_unavailable",
                payload=payload,
            )
        except Exception:
            pass  # observability must never crash the engine
