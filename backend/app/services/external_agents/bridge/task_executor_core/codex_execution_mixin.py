from .base import *
from .schemas import ExecutionContext, ExecutionResult
from .image_attachments import build_codex_image_args
from backend.app.services.host_runtime_sessions.runtime_recovery_policy import (
    build_direct_codex_failure_metadata,
    is_direct_codex_auth_bundle,
)


class CodexExecutionMixin:

    async def _execute_via_codex_cli(
        self,
        ctx: ExecutionContext,
        timeout: int,
    ) -> ExecutionResult:
        binary = self._resolve_runtime_binary("codex_cli")
        cwd, snapshot_root, snapshot_paths = self._resolve_cli_runtime_paths(ctx)
        stall_timeout = min(
            float(timeout),
            self._parse_env_float(
                "MINDSCAPE_CLI_STALL_TIMEOUT_SECONDS",
                DEFAULT_CLI_STALL_TIMEOUT_SECONDS,
                minimum=5.0,
            ),
        )

        if ctx.control_action == "codex_probe":
            await self._report_progress(ctx.execution_id, 15, "Refreshing Codex token")
            return await asyncio.wait_for(
                asyncio.to_thread(self._codex_probe_token_refresh_sync, ctx),
                timeout=timeout,
            )

        if ctx.control_action == "codex_account_home_delete":
            await self._report_progress(ctx.execution_id, 15, "Deleting Codex account home")
            return await asyncio.wait_for(
                asyncio.to_thread(self._delete_codex_control_account_home_sync, ctx),
                timeout=timeout,
            )

        control_cmd = self._build_codex_control_command(binary, ctx.control_action)
        if control_cmd:
            control_extra_env = self._codex_control_extra_env(ctx)
            if ctx.control_action == "codex_login":
                try:
                    await asyncio.to_thread(
                        self._ensure_codex_control_account_home_dirs_sync,
                        ctx,
                    )
                except Exception as exc:
                    return ExecutionResult(
                        status="failed",
                        error=f"codex_account_home_prepare_failed: {exc}",
                        metadata={
                            "selected_runtime_id": str(
                                ctx.inputs.get("runtime_id") or ""
                            ).strip()
                            if isinstance(ctx.inputs, dict)
                            else None,
                            "workspace_id": ctx.workspace_id or None,
                            "effective_workspace_id": ctx.workspace_id or None,
                        },
                    )
            await self._report_progress(ctx.execution_id, 15, "Calling Codex CLI")
            result = await asyncio.wait_for(
                self._run_cli_agent_subprocess(
                    ctx,
                    control_cmd,
                    cwd,
                    runtime_name="codex_cli",
                    snapshot_root=snapshot_root,
                    snapshot_paths=snapshot_paths,
                    stall_timeout=stall_timeout,
                    extra_env=control_extra_env or None,
                ),
                timeout=timeout,
            )
            if ctx.control_action in {
                "codex_login",
                "codex_login_status",
                "codex_logout",
                "codex_probe",
            }:
                identity_metadata = await asyncio.to_thread(
                    self._codex_control_identity_metadata_sync,
                    ctx,
                )
                if identity_metadata:
                    merged_metadata = dict(result.metadata or {})
                    merged_metadata.update(identity_metadata)
                    result.metadata = merged_metadata
            return result

        prompt = self._build_runtime_prompt(ctx)
        max_attempts = max(
            1,
            int(os.environ.get("MINDSCAPE_CODEX_POOL_MAX_TASK_ATTEMPTS", CODEX_POOL_MAX_TASK_ATTEMPTS)),
        )
        attempted_runtime_ids: set[str] = set()

        with tempfile.NamedTemporaryFile(
            prefix="mindscape_codex_last_",
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
        codex_model = self._codex_cli_model_hint(ctx.model)
        if codex_model:
            cmd.extend(["--model", codex_model])
        if ctx.task:
            cmd.append(prompt)
            cmd.extend(build_codex_image_args(ctx.uploaded_files))
        if ctx.max_duration:
            # Codex currently does not expose an explicit timeout flag; runner timeout is enforced outside.
            pass
        try:
            last_quota_error = ""
            attempt = 1
            while attempt <= max_attempts:
                auth_bundle = await self._fetch_runtime_auth_env(
                    "codex_cli",
                    ctx,
                    excluded_runtime_ids=attempted_runtime_ids,
                )
                if isinstance(auth_bundle, dict):
                    bundle_attempt_capacity_raw = (
                        auth_bundle.get("available_quota_scope_count")
                        or auth_bundle.get("available_runtime_count")
                        or 0
                    )
                    try:
                        bundle_attempt_capacity = int(bundle_attempt_capacity_raw)
                    except (TypeError, ValueError):
                        bundle_attempt_capacity = 0
                    if bundle_attempt_capacity > max_attempts:
                        max_attempts = bundle_attempt_capacity
                extra_env = auth_bundle.get("env") if isinstance(auth_bundle, dict) else {}
                direct_codex_runtime = is_direct_codex_auth_bundle(auth_bundle)
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
                if (
                    isinstance(auth_bundle, dict)
                    and auth_bundle.get("error")
                    and not selected_runtime_id
                ):
                    pool_error = str(auth_bundle.get("error") or "").strip()
                    if direct_codex_runtime:
                        return ExecutionResult(
                            status="failed",
                            output="",
                            error=pool_error,
                            metadata=build_direct_codex_failure_metadata(
                                selected_runtime_id=None,
                                workspace_id=ctx.workspace_id,
                                effective_workspace_id=effective_workspace_id,
                                error_text=pool_error,
                                stage="runtime_selection",
                            ),
                        )
                    error_text = (
                        f"{last_quota_error} (pool failover unavailable: {pool_error})"
                        if last_quota_error and attempt > 1
                        else pool_error
                    )
                    return ExecutionResult(
                        status="failed",
                        output="",
                        error=error_text,
                        metadata=self._codex_pool_failure_metadata(
                            selected_runtime_id=None,
                            attempted_runtime_ids=attempted_runtime_ids,
                            last_runtime_error=last_quota_error,
                            pool_error=pool_error,
                        ),
                    )
                if attempt > 1 and not selected_runtime_id:
                    pool_error = ""
                    if isinstance(auth_bundle, dict):
                        pool_error = str(
                            auth_bundle.get("error")
                            or auth_bundle.get("warning")
                            or ""
                        ).strip()
                    error_text = (
                        f"{last_quota_error} (pool failover unavailable: {pool_error})"
                        if last_quota_error and pool_error
                        else last_quota_error
                        or pool_error
                        or "Codex pool failover did not yield an alternate runtime"
                    )
                    return ExecutionResult(
                        status="failed",
                        output="",
                        error=error_text,
                        metadata=self._codex_pool_failure_metadata(
                            selected_runtime_id=None,
                            attempted_runtime_ids=attempted_runtime_ids,
                            last_runtime_error=last_quota_error,
                            pool_error=pool_error,
                        ),
                    )
                if selected_runtime_id and selected_runtime_id in attempted_runtime_ids:
                    if direct_codex_runtime:
                        error_text = last_quota_error or (
                            f"Direct Codex runtime was already attempted: {selected_runtime_id}"
                        )
                        return ExecutionResult(
                            status="failed",
                            output="",
                            error=error_text,
                            metadata=build_direct_codex_failure_metadata(
                                selected_runtime_id=selected_runtime_id,
                                workspace_id=ctx.workspace_id,
                                effective_workspace_id=effective_workspace_id,
                                error_text=error_text,
                                stage="runtime_selection",
                            ),
                        )
                    logger.warning(
                        "[TaskExecutor] Codex pool returned previously attempted runtime %s for %s; stopping failover loop",
                        selected_runtime_id,
                        ctx.execution_id,
                    )
                    error_text = (
                        f"{last_quota_error} (pool reused exhausted runtime {selected_runtime_id})"
                        if last_quota_error
                        else f"Codex pool reused exhausted runtime {selected_runtime_id}"
                    )
                    return ExecutionResult(
                        status="failed",
                        output="",
                        error=error_text,
                        metadata=self._codex_pool_failure_metadata(
                            selected_runtime_id=selected_runtime_id,
                            attempted_runtime_ids=attempted_runtime_ids,
                            last_runtime_error=last_quota_error,
                            pool_error="reused_exhausted_runtime",
                        ),
                    )

                progress_message = "Calling Codex CLI"
                if attempt > 1:
                    progress_message = f"Retrying Codex CLI via pool failover ({attempt}/{max_attempts})"
                await self._report_progress(ctx.execution_id, 15, progress_message)
                if direct_codex_runtime:
                    await self._report_progress(
                        ctx.execution_id,
                        18,
                        "Checking Codex CLI login status",
                    )
                    preflight_result = await self._preflight_direct_codex_cli(
                        binary=binary,
                        cwd=cwd,
                        extra_env=extra_env if isinstance(extra_env, dict) else None,
                        ctx=ctx,
                        selected_runtime_id=selected_runtime_id,
                        effective_workspace_id=effective_workspace_id,
                    )
                    if preflight_result is not None:
                        return preflight_result

                result = await asyncio.wait_for(
                    self._run_cli_agent_subprocess(
                        ctx,
                        cmd,
                        cwd,
                        runtime_name="codex_cli",
                        last_message_path=last_message_path,
                        snapshot_root=snapshot_root,
                        snapshot_paths=snapshot_paths,
                        extra_env=extra_env if isinstance(extra_env, dict) else None,
                        selected_runtime_id=selected_runtime_id,
                        workspace_id=ctx.workspace_id,
                        effective_workspace_id=effective_workspace_id,
                        stall_timeout=stall_timeout,
                    ),
                    timeout=timeout,
                )
                if result.status == "completed":
                    return result
                if direct_codex_runtime:
                    result.metadata = {
                        **(result.metadata or {}),
                        **build_direct_codex_failure_metadata(
                            selected_runtime_id=selected_runtime_id,
                            workspace_id=ctx.workspace_id,
                            effective_workspace_id=effective_workspace_id,
                            error_text=str((result.error or "") or (result.output or "")),
                            stage="execution",
                        ),
                    }
                    return result

                if not self._should_retry_codex_runtime_fault(result):
                    return result

                if not selected_runtime_id:
                    return result

                last_quota_error = str((result.error or "") or (result.output or "")).strip()
                attempted_runtime_ids.add(selected_runtime_id)
                if attempt >= max_attempts:
                    return result

                failure_label = (
                    "quota-like failure"
                    if self._looks_like_quota_exhaustion(last_quota_error)
                    else "auth failure"
                    if self._looks_like_auth_failure(last_quota_error)
                    else "retryable runtime fault"
                )
                logger.warning(
                    "[TaskExecutor] Codex runtime %s %s for %s; attempting pool failover (%d/%d)",
                    selected_runtime_id,
                    failure_label,
                    ctx.execution_id,
                    attempt,
                    max_attempts,
                )
                attempt += 1

            return ExecutionResult(
                status="failed",
                output="",
                error="Codex pool failover exhausted without a successful execution",
                metadata=self._codex_pool_failure_metadata(
                    selected_runtime_id=None,
                    attempted_runtime_ids=attempted_runtime_ids,
                    last_runtime_error=last_quota_error,
                    pool_error="failover_exhausted",
                ),
            )
        finally:
            try:
                os.unlink(last_message_path)
            except OSError:
                pass

    async def _preflight_direct_codex_cli(
        self,
        *,
        binary: str,
        cwd: str,
        extra_env: Optional[Dict[str, str]],
        ctx: ExecutionContext,
        selected_runtime_id: str,
        effective_workspace_id: str,
    ) -> Optional[ExecutionResult]:
        timeout_seconds = min(
            30.0,
            self._parse_env_float(
                "MINDSCAPE_DIRECT_CODEX_PREFLIGHT_TIMEOUT_SECONDS",
                12.0,
                minimum=2.0,
            ),
        )
        env = os.environ.copy()
        env["MINDSCAPE_AGENT_RUNTIME"] = "codex_cli"
        env["MINDSCAPE_AGENT_EXECUTION_ID"] = ctx.execution_id
        env["MINDSCAPE_AGENT_WORKSPACE_ID"] = ctx.workspace_id
        if extra_env:
            env.update(
                {
                    str(key): str(value)
                    for key, value in extra_env.items()
                    if value is not None and str(value) != ""
                }
            )
        cmd = [
            binary,
            "-c",
            'model_reasoning_effort="high"',
            "login",
            "status",
        ]
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                env=env,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            if proc is not None and proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except (asyncio.TimeoutError, ProcessLookupError):
                    if proc.returncode is None:
                        proc.kill()
                    try:
                        await asyncio.wait_for(proc.wait(), timeout=2.0)
                    except (asyncio.TimeoutError, ProcessLookupError):
                        pass
            return ExecutionResult(
                status="failed",
                output="",
                error=f"Codex CLI preflight timed out after {int(timeout_seconds)}s",
                metadata=build_direct_codex_failure_metadata(
                    selected_runtime_id=selected_runtime_id,
                    workspace_id=ctx.workspace_id,
                    effective_workspace_id=effective_workspace_id,
                    error_text="Codex CLI preflight timed out",
                    stage="preflight",
                ),
            )
        stdout = clip_cli_stream(
            stdout_bytes.decode("utf-8", errors="replace"),
            max_size=MAX_OUTPUT_SIZE,
        ).strip()
        stderr = clip_cli_stream(
            stderr_bytes.decode("utf-8", errors="replace"),
            max_size=MAX_OUTPUT_SIZE,
        ).strip()
        if proc.returncode == 0:
            return None
        stderr_tail = tail_cli_stream(stderr, max_size=500) if stderr else ""
        stdout_tail = tail_cli_stream(stdout, max_size=500) if stdout else ""
        detail = stderr_tail or stdout_tail or "no Codex CLI preflight output"
        return ExecutionResult(
            status="failed",
            output=stdout,
            error=f"Codex CLI preflight failed with exit code {proc.returncode}: {detail}",
            metadata=build_direct_codex_failure_metadata(
                selected_runtime_id=selected_runtime_id,
                workspace_id=ctx.workspace_id,
                effective_workspace_id=effective_workspace_id,
                error_text=stderr or stdout or detail,
                stage="preflight",
                exit_code=proc.returncode,
                stdout_tail=stdout_tail,
                stderr_tail=stderr_tail,
            ),
        )

    @staticmethod
    def _codex_pool_failure_metadata(
        *,
        selected_runtime_id: Optional[str],
        attempted_runtime_ids: set[str],
        last_runtime_error: str,
        pool_error: str,
    ) -> Dict[str, Any]:
        metadata: Dict[str, Any] = {
            "selected_runtime_id": selected_runtime_id or None,
            "attempted_runtime_ids": sorted(attempted_runtime_ids),
        }
        if last_runtime_error:
            metadata["last_runtime_error"] = last_runtime_error
        if pool_error:
            metadata["pool_error"] = pool_error
        return metadata
