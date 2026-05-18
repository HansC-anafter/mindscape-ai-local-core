from .base import *
from .schemas import ExecutionContext, ExecutionResult


class RuntimeExecutionMixin:

    async def _execute_via_gemini_runtime_bridge(
        self,
        ctx: ExecutionContext,
        timeout: int,
    ) -> ExecutionResult:
        """
        Execute an NL task via the Gemini runtime bridge command.

        The bridge command must be provided by env `GEMINI_CLI_RUNTIME_CMD`.
        It receives one JSON payload from stdin and should return JSON on stdout.
        """
        # Auto-discover bridge script: env override > project-relative path
        runtime_cmd = os.environ.get("MINDSCAPE_CLI_RUNTIME_CMD", "").strip()
        if not runtime_cmd:
            runtime_cmd = os.environ.get("GEMINI_CLI_RUNTIME_CMD", "").strip()
        logger.info(
            "[HostBridgeTaskExecutor] runtime_surface=%s runtime_cmd=%r workspace_root=%r",
            self.runtime_surface,
            runtime_cmd,
            self.workspace_root,
        )
        if not runtime_cmd:
            # Derive from project root (workspace_root may be project or parent)
            for candidate_root in (
                self.workspace_root,
                os.path.dirname(self.workspace_root),
            ):
                bridge_path = os.path.join(
                    candidate_root, "scripts", "gemini_cli_runtime_bridge.py"
                )
                if os.path.isfile(bridge_path):
                    import sys as _sys
                    runtime_cmd = f"{_sys.executable} {bridge_path}"
                    break

        if not runtime_cmd:
            return ExecutionResult(
                status="failed",
                error=(
                    "Cannot find gemini_cli_runtime_bridge.py. "
                    "Set GEMINI_CLI_RUNTIME_CMD or ensure scripts/ "
                    "is in the project root."
                ),
            )

        # posix=False on Windows: preserve backslashes in paths
        argv = shlex.split(runtime_cmd, posix=(os.name != 'nt'))
        if not argv:
            return ExecutionResult(
                status="failed",
                error="Invalid GEMINI_CLI_RUNTIME_CMD (empty argv)",
            )

        # Auto-derive backend API URL from env or WS host
        backend_url = os.environ.get("MINDSCAPE_BACKEND_API_URL", "").strip()
        if not backend_url:
            ws_host = os.environ.get("MINDSCAPE_WS_HOST", "").strip()
            if ws_host:
                backend_url = f"http://{ws_host}"

        payload = {
            "execution_id": ctx.execution_id,
            "workspace_id": ctx.workspace_id,
            "surface": self.runtime_surface,
            "task": ctx.task,
            "allowed_tools": ctx.allowed_tools,
            "max_duration": timeout,
            "model": ctx.model,
            "backend_api_url": backend_url,
            "context": {
                "project_id": ctx.project_id,
                "intent_id": ctx.intent_id,
                "lens_id": ctx.lens_id,
                "auth_workspace_id": ctx.auth_workspace_id,
                "source_workspace_id": ctx.source_workspace_id,
                "sandbox_path": ctx.sandbox_path,
                "issued_at": ctx.issued_at,
                "conversation_context": ctx.conversation_context,
                "thread_id": ctx.thread_id,
                "uploaded_files": ctx.uploaded_files,
                "recommended_pack_codes": ctx.recommended_pack_codes,
                "file_hint": ctx.file_hint,
                "control_action": ctx.control_action,
            },
        }

        await self._report_progress(ctx.execution_id, 15, "Calling Gemini CLI bridge")
        cwd = self.workspace_root if os.path.isdir(self.workspace_root) else os.getcwd()

        # Inject per-task env vars so the MCP gateway can RAG-filter tools
        # for this specific task (not the parent process's stale env).
        sub_env = os.environ.copy()
        # Enrich task hint with file context for RAG matching
        if ctx.file_hint:
            sub_env["MINDSCAPE_TASK_HINT"] = f"{ctx.task} {ctx.file_hint}"[:500]
        else:
            sub_env["MINDSCAPE_TASK_HINT"] = ctx.task[:500]
        sub_env["MINDSCAPE_WORKSPACE_ID"] = ctx.workspace_id
        if ctx.recommended_pack_codes:
            sub_env["MINDSCAPE_RECOMMENDED_PACKS"] = json.dumps(
                ctx.recommended_pack_codes
            )

        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=sub_env,
        )
        self._active[ctx.execution_id] = proc

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(json.dumps(payload).encode("utf-8")),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.communicate()
            return ExecutionResult(
                status="timeout",
                error=f"Gemini CLI bridge timed out after {timeout}s",
            )

        stdout = stdout_b.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE].strip()
        stderr = stderr_b.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE].strip()
        if proc.returncode != 0:
            return ExecutionResult(
                status="failed",
                output=stdout,
                error=f"Gemini CLI bridge exit code {proc.returncode}: {stderr[:500]}",
            )

        # Prefer structured JSON output from runtime, but allow plain text.
        try:
            runtime_data = json.loads(stdout) if stdout else {}
        except json.JSONDecodeError:
            return ExecutionResult(status="completed", output=stdout)

        status = str(runtime_data.get("status", "completed"))
        output = str(runtime_data.get("output", "") or "")
        error = runtime_data.get("error")
        tool_calls = runtime_data.get("tool_calls") or []
        files_modified = runtime_data.get("files_modified") or []
        files_created = runtime_data.get("files_created") or []
        runtime_id = runtime_data.get("runtime_id")
        auth_scope = runtime_data.get("auth_scope")
        result = ExecutionResult(
            status=status,
            output=output,
            error=str(error) if error else None,
            tool_calls=tool_calls if isinstance(tool_calls, list) else [],
            files_modified=files_modified if isinstance(files_modified, list) else [],
            files_created=files_created if isinstance(files_created, list) else [],
        )
        result_dict = result.to_dict()
        if runtime_id:
            result_dict["runtime_id"] = runtime_id
        if isinstance(auth_scope, dict) and auth_scope:
            result_dict["auth_scope"] = auth_scope
        return result_dict

    def _resolve_runtime_binary(self, runtime_surface: str) -> str:
        runtime_surface = runtime_surface.lower()
        if runtime_surface == "codex_cli":
            return resolve_codex_cli_binary(os.environ.get("CODEX_CLI_PATH"))
        if runtime_surface == "claude_code_cli":
            return os.environ.get("CLAUDE_CODE_CLI_PATH", "").strip() or (
                shutil.which("claude") or "claude"
            )
        return os.environ.get("GEMINI_CLI_PATH", "").strip() or (
            shutil.which("gemini") or "gemini"
        )

    def _build_runtime_prompt(self, ctx: ExecutionContext) -> str:
        prompt_parts = []
        if ctx.conversation_context:
            prompt_parts.append(f"## Conversation Context\n{ctx.conversation_context}")
        if ctx.uploaded_files:
            file_lines = []
            for item in ctx.uploaded_files:
                if isinstance(item, dict):
                    file_name = item.get("file_name") or item.get("filename") or "file"
                    file_path = item.get("file_path") or ""
                    detected_type = item.get("detected_type") or item.get(
                        "file_type", "unknown"
                    )
                    line = f"- {file_name} ({detected_type})"
                    if file_path:
                        line += f": {file_path}"
                    file_lines.append(line)
                elif isinstance(item, str):
                    file_lines.append(f"- {item}")
            if file_lines:
                prompt_parts.append("## Uploaded Files\n" + "\n".join(file_lines))
        prompt_parts.append(ctx.task)
        prompt_parts.append(
            "IMPORTANT: After using any tools, provide a final text summary."
        )
        return "\n\n".join(part for part in prompt_parts if part)
