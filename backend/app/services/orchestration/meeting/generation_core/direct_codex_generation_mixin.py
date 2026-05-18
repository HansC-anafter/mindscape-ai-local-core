"""Direct Codex CLI generation flow."""

import logging
from typing import Any, Dict, List, Optional

from backend.app.services.orchestration.meeting import _generation as generation_module

logger = logging.getLogger(__name__)


class MeetingGenerationDirectCodexGenerationMixin:
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
            "generating", "Running directly through codex_cli..."
        )

        binary = generation_module._resolve_codex_cli_binary(generation_module.os.environ.get("CODEX_CLI_PATH", "").strip())
        cwd = generation_module._resolve_codex_cli_cwd(generation_module.os.environ.get("HOST_PROJECT_PATH", "").strip())
        attempted_runtime_ids: set[str] = set()
        excluded_quota_scope_keys: set[str] = set()
        max_attempts = 1
        attempt = 1
        pool_wait_attempts = generation_module._codex_pool_wait_attempt_count()
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
                    generation_module._is_retryable_runtime_error_text(pool_error)
                    and pool_wait_index < pool_wait_attempts - 1
                ):
                    logger.warning(
                        "Codex pool temporarily unavailable for meeting turn "
                        "(wait %d/%d): %s",
                        pool_wait_index + 1,
                        pool_wait_attempts,
                        pool_error,
                    )
                    await generation_module.asyncio.sleep(generation_module._executor_runtime_retry_delay(pool_wait_index))
                    pool_wait_index += 1
                    continue
                if (
                    "codex pool admission blocked" in pool_error.lower()
                    or "no_runnable_runtimes" in pool_error.lower()
                ):
                    raise generation_module.CodexPoolAdmissionBlockedError(
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

            progress_message = f"Running directly through codex_cli (runtime={selected_runtime_id})..."
            if attempt > 1:
                progress_message = (
                    "Retrying through the next codex_cli pool runtime "
                    f"({attempt}/{max_attempts}, runtime={selected_runtime_id})..."
                )
            await self._emit_meeting_stage("generating", progress_message)

            with generation_module.tempfile.NamedTemporaryFile(
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
                    generation_module.os.unlink(last_message_path)
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
            runtime_fault = generation_module._classify_codex_cli_runtime_failure(error_text)
            fault_kind = str(runtime_fault.get("fault_kind") or "runtime").strip()
            fault_error_code = str(
                runtime_fault.get("error_code") or "runtime_error"
            ).strip()
            quota_fault = fault_kind == "quota"
            auth_fault = fault_kind == "auth"
            retryable_runtime_fault = generation_module._should_retry_codex_runtime_fault(error_text)
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
