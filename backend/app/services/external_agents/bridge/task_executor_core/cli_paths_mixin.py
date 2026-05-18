from .base import *
from .schemas import ExecutionContext, ExecutionResult


class CliPathsMixin:

    @staticmethod
    def _expected_snapshot_paths(ctx: ExecutionContext) -> List[str]:
        inputs = ctx.inputs if isinstance(ctx.inputs, dict) else {}
        candidates: List[str] = []

        deliverable_path = inputs.get("deliverable_path")
        if isinstance(deliverable_path, str) and deliverable_path.strip():
            raw = deliverable_path.strip()
            candidates.append(raw)
            basename = os.path.basename(raw)
            if basename and basename != raw:
                candidates.append(basename)

        deliverable_targets = inputs.get("deliverable_targets")
        if isinstance(deliverable_targets, list):
            for item in deliverable_targets:
                if not isinstance(item, dict):
                    continue
                raw = (item.get("deliverable_path") or "").strip()
                if not raw:
                    continue
                candidates.append(raw)
                basename = os.path.basename(raw)
                if basename and basename != raw:
                    candidates.append(basename)

        deduped: List[str] = []
        seen: set[str] = set()
        for raw in candidates:
            normalized = raw.replace("\\", "/").lstrip("./")
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped

    def _resolve_cli_runtime_paths(
        self,
        ctx: ExecutionContext,
    ) -> tuple[str, str, List[str]]:
        """Resolve the CLI working dir and the optional diff snapshot root.

        Host bridges receive sandbox paths from backend dispatch payloads, but those
        paths may only exist inside the backend container. When the host cannot see
        that sandbox, we still let CLI runtimes execute from the workspace root for
        repository context. When a deliverable path is known, we probe only that
        expected file so markdown assets can still be landed.
        """
        sandbox_path = (ctx.sandbox_path or "").strip()
        if sandbox_path and os.path.isdir(sandbox_path):
            return sandbox_path, sandbox_path, []

        cwd = self.workspace_root if os.path.isdir(self.workspace_root) else os.getcwd()
        expected_paths = self._expected_snapshot_paths(ctx)
        if sandbox_path:
            if expected_paths:
                logger.warning(
                    "[TaskExecutor] Host sandbox %r unavailable for %s; "
                    "using cwd=%r with targeted snapshot for %s",
                    sandbox_path,
                    ctx.execution_id,
                    cwd,
                    expected_paths,
                )
            else:
                logger.warning(
                    "[TaskExecutor] Host sandbox %r unavailable for %s; "
                    "using cwd=%r without file snapshot",
                    sandbox_path,
                    ctx.execution_id,
                    cwd,
                )
        return cwd, (cwd if expected_paths else ""), expected_paths

    async def _run_cli_agent_subprocess(
        self,
        ctx: ExecutionContext,
        cmd: List[str],
        cwd: str,
        runtime_name: str,
        last_message_path: Optional[str] = None,
        snapshot_root: Optional[str] = None,
        snapshot_paths: Optional[List[str]] = None,
        extra_env: Optional[Dict[str, str]] = None,
        selected_runtime_id: Optional[str] = None,
        workspace_id: str = "",
        effective_workspace_id: str = "",
        stall_timeout: Optional[float] = None,
    ) -> ExecutionResult:
        resolved_snapshot_root = (snapshot_root or "").strip()
        before_files = (
            self._snapshot_files(resolved_snapshot_root, only_paths=snapshot_paths)
            if resolved_snapshot_root
            else {}
        )
        env = os.environ.copy()
        env["MINDSCAPE_AGENT_RUNTIME"] = runtime_name
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

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )
        logger.info(
            "[TaskExecutor] Spawned %s subprocess pid=%s for execution %s",
            runtime_name,
            proc.pid,
            ctx.execution_id,
        )
        self._active[ctx.execution_id] = proc
        progress_task = asyncio.create_task(
            self._progress_ticker(ctx.execution_id, proc)
        )

        try:
            stdout_bytes, stderr_bytes = await self._wait_for_cli_subprocess(
                proc=proc,
                runtime_name=runtime_name,
                execution_id=ctx.execution_id,
                last_message_path=last_message_path,
                snapshot_root=resolved_snapshot_root,
                snapshot_paths=snapshot_paths,
                stall_timeout=stall_timeout,
            )
        except asyncio.TimeoutError as exc:
            progress_task.cancel()
            try:
                await progress_task
            except asyncio.CancelledError:
                pass
            return ExecutionResult(
                status="timeout",
                output="",
                error=str(exc),
                metadata={
                    "effective_sandbox_path": resolved_snapshot_root or cwd,
                    "selected_runtime_id": selected_runtime_id or None,
                    "workspace_id": workspace_id or None,
                    "effective_workspace_id": effective_workspace_id or None,
                },
            )

        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass

        after_files = (
            self._snapshot_files(resolved_snapshot_root, only_paths=snapshot_paths)
            if resolved_snapshot_root
            else {}
        )
        files_created, files_modified = self._diff_file_snapshots(before_files, after_files)
        attachments = self._collect_targeted_attachments(
            snapshot_root=resolved_snapshot_root,
            cwd=cwd,
            snapshot_paths=snapshot_paths,
        )

        stdout = clip_cli_stream(
            stdout_bytes.decode("utf-8", errors="replace"),
            max_size=MAX_OUTPUT_SIZE,
        ).strip()
        stderr = clip_cli_stream(
            stderr_bytes.decode("utf-8", errors="replace"),
            max_size=MAX_OUTPUT_SIZE,
        ).strip()
        output = stdout
        synthesized_error: Optional[str] = None

        if runtime_name == "codex_cli":
            output, synthesized_error = self._resolve_codex_cli_output(
                stdout=stdout,
                stderr=stderr,
                last_message_path=last_message_path,
            )
        else:
            if last_message_path and os.path.isfile(last_message_path):
                try:
                    output = (
                        Path(last_message_path).read_text(encoding="utf-8").strip()
                        or output
                    )
                except OSError:
                    pass
            if not output and stderr:
                output = stderr

        if proc.returncode == 0 and not synthesized_error:
            if runtime_name == "codex_cli" and selected_runtime_id:
                await self._report_runtime_success(
                    runtime_name,
                    selected_runtime_id,
                )
            logger.info(
                "[TaskExecutor] %s subprocess pid=%s finished with code 0 for %s",
                runtime_name,
                proc.pid,
                ctx.execution_id,
            )
            return ExecutionResult(
                status="completed",
                output=output or "(no response from agent)",
                files_modified=files_modified,
                files_created=files_created,
                attachments=attachments,
                metadata={
                    "effective_sandbox_path": resolved_snapshot_root or cwd,
                    "selected_runtime_id": selected_runtime_id or None,
                    "workspace_id": workspace_id or None,
                    "effective_workspace_id": effective_workspace_id or None,
                },
            )
        if synthesized_error:
            if selected_runtime_id and self._looks_like_quota_exhaustion(synthesized_error):
                await self._report_runtime_quota_exhausted(
                    runtime_name,
                    selected_runtime_id,
                    workspace_id=workspace_id,
                    effective_workspace_id=effective_workspace_id,
                    error_text=synthesized_error,
                )
            elif selected_runtime_id and self._looks_like_auth_failure(synthesized_error):
                classification = classify_codex_cli_runtime_failure(synthesized_error)
                await self._report_runtime_auth_failure(
                    runtime_name,
                    selected_runtime_id,
                    error_code=str(classification.get("error_code") or "auth_failure"),
                    workspace_id=workspace_id,
                    effective_workspace_id=effective_workspace_id,
                )
            logger.warning(
                "[TaskExecutor] %s subprocess pid=%s produced no usable agent message "
                "for %s: %s",
                runtime_name,
                proc.pid,
                ctx.execution_id,
                synthesized_error,
            )
            return ExecutionResult(
                status="failed",
                output=output,
                error=synthesized_error,
                files_modified=files_modified,
                files_created=files_created,
                attachments=attachments,
                metadata={
                    "effective_sandbox_path": resolved_snapshot_root or cwd,
                    "selected_runtime_id": selected_runtime_id or None,
                    "workspace_id": workspace_id or None,
                    "effective_workspace_id": effective_workspace_id or None,
                },
            )
        if selected_runtime_id and self._looks_like_quota_exhaustion(stderr or stdout):
            quota_error_text = stderr or stdout
            await self._report_runtime_quota_exhausted(
                runtime_name,
                selected_runtime_id,
                workspace_id=workspace_id,
                effective_workspace_id=effective_workspace_id,
                error_text=quota_error_text,
            )
        elif selected_runtime_id and self._looks_like_auth_failure(stderr or stdout):
            classification = classify_codex_cli_runtime_failure(stderr or stdout)
            await self._report_runtime_auth_failure(
                runtime_name,
                selected_runtime_id,
                error_code=str(classification.get("error_code") or "auth_failure"),
                workspace_id=workspace_id,
                effective_workspace_id=effective_workspace_id,
            )
        logger.warning(
            "[TaskExecutor] %s subprocess pid=%s finished with code %s for %s",
            runtime_name,
            proc.pid,
            proc.returncode,
            ctx.execution_id,
        )
        return ExecutionResult(
            status="failed",
            output=output,
            error=f"Exit code {proc.returncode}: {tail_cli_stream(stderr or stdout, max_size=500)}",
            files_modified=files_modified,
            files_created=files_created,
            attachments=attachments,
            metadata={
                "effective_sandbox_path": resolved_snapshot_root or cwd,
                "selected_runtime_id": selected_runtime_id or None,
                "workspace_id": workspace_id or None,
                "effective_workspace_id": effective_workspace_id or None,
            },
        )

    async def _wait_for_cli_subprocess(
        self,
        *,
        proc: asyncio.subprocess.Process,
        runtime_name: str,
        execution_id: str,
        last_message_path: Optional[str],
        snapshot_root: str,
        snapshot_paths: Optional[List[str]],
        stall_timeout: Optional[float],
    ) -> tuple[bytes, bytes]:
        return await wait_for_cli_subprocess_activity(
            proc=proc,
            runtime_name=runtime_name,
            execution_id=execution_id,
            last_message_path=last_message_path,
            snapshot_root=snapshot_root,
            snapshot_paths=snapshot_paths,
            stall_timeout=stall_timeout,
        )

    @staticmethod
    def _cli_activity_signature(
        *,
        last_message_path: Optional[str],
        snapshot_root: str,
        snapshot_paths: Optional[List[str]],
    ) -> tuple[tuple[str, int, int], ...]:
        return cli_activity_signature(
            last_message_path=last_message_path,
            snapshot_root=snapshot_root,
            snapshot_paths=snapshot_paths,
        )

    @staticmethod
    def _collect_targeted_attachments(
        *,
        snapshot_root: str,
        cwd: str,
        snapshot_paths: Optional[List[str]],
    ) -> List[Dict[str, Any]]:
        if not isinstance(snapshot_paths, list) or not snapshot_paths:
            return []

        roots: List[Path] = []
        seen_roots: set[str] = set()
        for raw_root in (snapshot_root, cwd):
            candidate = str(raw_root or "").strip()
            if not candidate or candidate in seen_roots or not os.path.isdir(candidate):
                continue
            seen_roots.add(candidate)
            roots.append(Path(candidate))

        attachments: List[Dict[str, Any]] = []
        seen_filenames: set[str] = set()
        for raw_path in snapshot_paths:
            if not isinstance(raw_path, str):
                continue
            normalized = raw_path.replace("\\", "/").lstrip("./")
            filename = os.path.basename(normalized)
            if not normalized or not filename or filename in seen_filenames:
                continue

            resolved_file: Optional[Path] = None
            for root in roots:
                for probe in (normalized, filename):
                    candidate = root / probe
                    if candidate.is_file():
                        resolved_file = candidate
                        break
                if resolved_file is not None:
                    break
            if resolved_file is None:
                continue

            try:
                content: Any = resolved_file.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                try:
                    content = resolved_file.read_bytes()
                except OSError:
                    continue
            except OSError:
                continue

            attachments.append(
                {
                    "filename": filename,
                    "content": content,
                }
            )
            seen_filenames.add(filename)

        return attachments

    @classmethod
    def _resolve_codex_cli_output(
        cls,
        *,
        stdout: str,
        stderr: str,
        last_message_path: Optional[str],
    ) -> tuple[str, Optional[str]]:
        return resolve_codex_cli_output(
            stdout=stdout,
            stderr=stderr,
            last_message_path=last_message_path,
        )

    @staticmethod
    def _extract_codex_cli_error(*, stdout: str, stderr: str) -> Optional[str]:
        return extract_codex_cli_error(stdout=stdout, stderr=stderr)

    @staticmethod
    def _looks_like_quota_exhaustion(message: str) -> bool:
        return (
            classify_codex_cli_runtime_failure(message).get("fault_kind") == "quota"
        )

    @classmethod
    def _looks_like_auth_failure(cls, message: str) -> bool:
        return classify_codex_cli_runtime_failure(message).get("fault_kind") == "auth"

    @classmethod
    def _should_retry_codex_runtime_fault(cls, result: ExecutionResult) -> bool:
        message = str((result.error or "") or (result.output or "")).strip()
        if result.status == "timeout":
            return True
        return should_retry_codex_runtime_fault(message)
