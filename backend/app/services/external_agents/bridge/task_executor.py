"""
HostBridgeTaskExecutor — host-side task execution engine for WS-dispatched CLI surfaces.

Receives dispatch payloads from the WebSocket client and executes coding
tasks. Supports progress reporting via a callback function.

Architecture:
    HostBridgeWSClient -> _handle_dispatch -> HostBridgeTaskExecutor.__call__
                                                       |
                                                  execute task
                                                       |
                                                  return result dict

Usage:
    executor = HostBridgeTaskExecutor(workspace_root="/path/to/project")
    client = HostBridgeWSClient(
        workspace_id="ws-123",
        task_handler=executor,
    )
"""

import asyncio
import json
import logging
import os
import shlex
import shutil
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, List, Optional

logger = logging.getLogger("task_executor")


# ============================================================
#  Configuration
# ============================================================

DEFAULT_TASK_TIMEOUT = 600  # 10 minutes
MAX_OUTPUT_SIZE = 100_000  # characters


@dataclass
class ExecutionContext:
    """Parsed context from a dispatch payload."""

    execution_id: str
    workspace_id: str
    task: str
    allowed_tools: List[str]
    max_duration: int
    model: str = ""
    project_id: str = ""
    intent_id: str = ""
    lens_id: str = ""
    sandbox_path: str = ""
    issued_at: str = ""
    conversation_context: str = ""
    thread_id: str = ""
    auth_workspace_id: str = ""
    source_workspace_id: str = ""
    control_action: str = ""
    uploaded_files: List[Dict[str, Any]] = field(default_factory=list)
    recommended_pack_codes: List[str] = field(default_factory=list)
    file_hint: str = ""

    @classmethod
    def from_dispatch(cls, msg: Dict[str, Any]) -> "ExecutionContext":
        """Parse a dispatch payload into an ExecutionContext."""
        ctx = msg.get("context", {})
        return cls(
            execution_id=msg.get("execution_id", ""),
            workspace_id=msg.get("workspace_id", ""),
            task=msg.get("task", ""),
            allowed_tools=msg.get("allowed_tools", []),
            max_duration=msg.get("max_duration", DEFAULT_TASK_TIMEOUT),
            model=msg.get("model", "") or "",
            project_id=ctx.get("project_id", ""),
            intent_id=ctx.get("intent_id", ""),
            lens_id=ctx.get("lens_id", ""),
            sandbox_path=ctx.get("sandbox_path", ""),
            issued_at=msg.get("issued_at", ""),
            conversation_context=ctx.get("conversation_context", ""),
            thread_id=ctx.get("thread_id", ""),
            auth_workspace_id=ctx.get("auth_workspace_id", ""),
            source_workspace_id=ctx.get("source_workspace_id", ""),
            control_action=ctx.get("control_action", ""),
            uploaded_files=ctx.get("uploaded_files", []),
            recommended_pack_codes=ctx.get("recommended_pack_codes", []),
            file_hint=ctx.get("file_hint", ""),
        )


@dataclass
class ExecutionResult:
    """Result of a task execution."""

    status: str = "completed"
    output: str = ""
    error: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    files_created: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "tool_calls": self.tool_calls,
            "files_modified": self.files_modified,
            "files_created": self.files_created,
        }


# Type for progress callback: async fn(execution_id, percent, message)
ProgressCallback = Callable[[str, int, str], Coroutine[Any, Any, None]]


# ============================================================
#  HostBridgeTaskExecutor
# ============================================================


class HostBridgeTaskExecutor:
    """
    Host-side task executor for WS-dispatched CLI surfaces.

    Executes coding tasks by running shell commands in the workspace.
    Reports progress via a callback function provided by the WS client.

    Pluggable via `command_builder` for custom execution strategies.
    """

    def __init__(
        self,
        workspace_root: Optional[str] = None,
        timeout: int = DEFAULT_TASK_TIMEOUT,
        command_builder: Optional[Callable[[ExecutionContext], List[str]]] = None,
        progress_callback: Optional[ProgressCallback] = None,
        runtime_surface: str = "gemini_cli",
    ):
        """
        Args:
            workspace_root: Root directory for task execution. Defaults to CWD.
            timeout: Max execution time in seconds.
            command_builder: Custom function to build shell commands from context.
                             If None, uses the default strategy.
            progress_callback: Async callback for progress updates.
        """
        self.workspace_root = workspace_root or os.getcwd()
        self.timeout = timeout
        self.command_builder = command_builder or self._default_command_builder
        self.progress_callback = progress_callback
        self.runtime_surface = runtime_surface or "gemini_cli"

        # Track active executions for cancellation
        self._active: Dict[str, asyncio.subprocess.Process] = {}

    async def __call__(
        self,
        dispatch_msg: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute a dispatch payload and return a result dict.

        This is the interface expected by HostBridgeWSClient.task_handler.
        """
        ctx = ExecutionContext.from_dispatch(dispatch_msg)

        logger.info(
            f"[TaskExecutor] Starting execution {ctx.execution_id}: "
            f"{ctx.task[:100]}..."
        )

        try:
            result = await self._execute(ctx)
        except asyncio.TimeoutError:
            logger.error(
                f"[TaskExecutor] Execution {ctx.execution_id} timed out "
                f"after {ctx.max_duration}s"
            )
            result = ExecutionResult(
                status="timeout",
                error=f"Task timed out after {ctx.max_duration}s",
            )
        except asyncio.CancelledError:
            logger.warning(f"[TaskExecutor] Execution {ctx.execution_id} cancelled")
            result = ExecutionResult(
                status="cancelled",
                error="Task was cancelled",
            )
        except Exception as e:
            logger.error(f"[TaskExecutor] Execution {ctx.execution_id} failed: {e}")
            result = ExecutionResult(
                status="failed",
                error=str(e),
            )
        finally:
            self._active.pop(ctx.execution_id, None)

        return result.to_dict() if hasattr(result, "to_dict") else result

    async def cancel(self, execution_id: str) -> bool:
        """Cancel an active execution by ID."""
        proc = self._active.get(execution_id)
        if proc and proc.returncode is None:
            proc.terminate()
            logger.info(f"[TaskExecutor] Cancelled execution {execution_id}")
            return True
        return False

    # ============================================================
    #  Internal execution
    # ============================================================

    async def _execute(self, ctx: ExecutionContext) -> ExecutionResult:
        """Run the task and collect results."""
        timeout = min(ctx.max_duration, self.timeout)

        # Report start progress
        await self._report_progress(ctx.execution_id, 5, "Preparing execution")

        # Build the command
        cmd = self.command_builder(ctx)
        if not cmd:
            # Natural-language task path: delegate to the configured CLI runtime.
            return await self._execute_via_runtime(ctx, timeout=timeout)

        logger.info(
            f"[TaskExecutor] Running command for {ctx.execution_id}: "
            f"{' '.join(cmd[:3])}..."
        )

        # Resolve working directory
        cwd = ctx.sandbox_path or self.workspace_root
        if not os.path.isdir(cwd):
            cwd = self.workspace_root

        await self._report_progress(ctx.execution_id, 10, "Starting subprocess")

        # Execute with timeout
        result = await asyncio.wait_for(
            self._run_subprocess(ctx, cmd, cwd),
            timeout=timeout,
        )

        await self._report_progress(ctx.execution_id, 95, "Finalizing")
        return result

    async def _execute_via_runtime(
        self,
        ctx: ExecutionContext,
        timeout: int,
    ) -> ExecutionResult:
        runtime_surface = (self.runtime_surface or "gemini_cli").strip().lower()
        if runtime_surface == "gemini_cli":
            return await self._execute_via_gemini_runtime_bridge(ctx, timeout=timeout)
        if runtime_surface == "codex_cli":
            return await self._execute_via_codex_cli(ctx, timeout=timeout)
        if runtime_surface == "claude_code_cli":
            return await self._execute_via_claude_code_cli(ctx, timeout=timeout)
        return ExecutionResult(
            status="failed",
            error=f"Unsupported runtime surface: {self.runtime_surface}",
        )

    @staticmethod
    def _resolve_backend_api_url() -> str:
        backend_url = os.environ.get("MINDSCAPE_BACKEND_API_URL", "").strip()
        if not backend_url:
            ws_host = os.environ.get("MINDSCAPE_WS_HOST", "").strip()
            if ws_host:
                backend_url = (
                    ws_host
                    if ws_host.startswith("http://") or ws_host.startswith("https://")
                    else f"http://{ws_host}"
                )
        return backend_url.rstrip("/")

    @staticmethod
    def _fallback_runtime_auth_env(runtime_name: str) -> Dict[str, str]:
        runtime_name = (runtime_name or "").strip().lower()
        if runtime_name == "codex_cli":
            api_key = os.environ.get("OPENAI_API_KEY", "").strip()
            return {"OPENAI_API_KEY": api_key} if api_key else {}
        if runtime_name == "claude_code_cli":
            api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
            return {"ANTHROPIC_API_KEY": api_key} if api_key else {}
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        return {"GEMINI_API_KEY": api_key} if api_key else {}

    def _fetch_runtime_auth_bundle_sync(
        self,
        runtime_name: str,
        ctx: ExecutionContext,
    ) -> Dict[str, Any]:
        backend_url = self._resolve_backend_api_url()
        if not backend_url:
            return {
                "auth_mode": "env_fallback",
                "env": self._fallback_runtime_auth_env(runtime_name),
            }

        params = {"surface": runtime_name}
        if ctx.workspace_id:
            params["workspace_id"] = ctx.workspace_id
        if ctx.auth_workspace_id:
            params["auth_workspace_id"] = ctx.auth_workspace_id
        if ctx.source_workspace_id:
            params["source_workspace_id"] = ctx.source_workspace_id
        url = (
            f"{backend_url}/api/v1/auth/cli-token?"
            f"{urllib.parse.urlencode(params)}"
        )
        try:
            req = urllib.request.Request(url, method="GET")
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            env = data.get("env")
            data["env"] = (
                {
                    str(key): str(value)
                    for key, value in env.items()
                    if value is not None and str(value) != ""
                }
                if isinstance(env, dict)
                else {}
            )
            return data
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "[TaskExecutor] Failed to fetch auth bundle for %s: %s",
                runtime_name,
                exc,
            )
            return {
                "auth_mode": "env_fallback",
                "env": self._fallback_runtime_auth_env(runtime_name),
            }

    async def _fetch_runtime_auth_env(
        self,
        runtime_name: str,
        ctx: ExecutionContext,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self._fetch_runtime_auth_bundle_sync,
            runtime_name,
            ctx,
        )

    @staticmethod
    def _build_codex_control_command(binary: str, control_action: str) -> List[str]:
        action = (control_action or "").strip().lower()
        if not action:
            return []
        base = [binary, "-c", 'model_reasoning_effort="high"']
        if action == "codex_login_status":
            return [*base, "login", "status"]
        if action == "codex_login":
            return [*base, "login"]
        if action == "codex_logout":
            return [*base, "logout"]
        return []

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
            return os.environ.get("CODEX_CLI_PATH", "").strip() or (
                shutil.which("codex") or "codex"
            )
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

    async def _execute_via_codex_cli(
        self,
        ctx: ExecutionContext,
        timeout: int,
    ) -> ExecutionResult:
        binary = self._resolve_runtime_binary("codex_cli")
        cwd = ctx.sandbox_path or self.workspace_root
        if not os.path.isdir(cwd):
            cwd = self.workspace_root

        control_cmd = self._build_codex_control_command(binary, ctx.control_action)
        if control_cmd:
            await self._report_progress(ctx.execution_id, 15, "Calling Codex CLI")
            return await asyncio.wait_for(
                self._run_cli_agent_subprocess(
                    ctx,
                    control_cmd,
                    cwd,
                    runtime_name="codex_cli",
                ),
                timeout=timeout,
            )

        prompt = self._build_runtime_prompt(ctx)
        auth_bundle = await self._fetch_runtime_auth_env("codex_cli", ctx)
        extra_env = auth_bundle.get("env") if isinstance(auth_bundle, dict) else {}

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
            "--full-auto",
            "--output-last-message",
            last_message_path,
        ]
        if ctx.model:
            cmd.extend(["--model", ctx.model])
        if ctx.task:
            cmd.append(prompt)
        if ctx.max_duration:
            # Codex currently does not expose an explicit timeout flag; runner timeout is enforced outside.
            pass
        await self._report_progress(ctx.execution_id, 15, "Calling Codex CLI")
        try:
            return await asyncio.wait_for(
                self._run_cli_agent_subprocess(
                    ctx,
                    cmd,
                    cwd,
                    runtime_name="codex_cli",
                    last_message_path=last_message_path,
                    extra_env=extra_env if isinstance(extra_env, dict) else None,
                ),
                timeout=timeout,
            )
        finally:
            try:
                os.unlink(last_message_path)
            except OSError:
                pass

    async def _execute_via_claude_code_cli(
        self,
        ctx: ExecutionContext,
        timeout: int,
    ) -> ExecutionResult:
        binary = self._resolve_runtime_binary("claude_code_cli")
        prompt = self._build_runtime_prompt(ctx)
        cwd = ctx.sandbox_path or self.workspace_root
        if not os.path.isdir(cwd):
            cwd = self.workspace_root
        auth_bundle = await self._fetch_runtime_auth_env("claude_code_cli", ctx)
        extra_env = auth_bundle.get("env") if isinstance(auth_bundle, dict) else {}

        cmd = [
            binary,
            "-p",
            "--dangerously-skip-permissions",
            "--add-dir",
            cwd,
        ]
        if ctx.model:
            cmd.extend(["--model", ctx.model])
        cmd.append(prompt)
        await self._report_progress(
            ctx.execution_id,
            15,
            "Calling Claude Code CLI",
        )
        return await asyncio.wait_for(
            self._run_cli_agent_subprocess(
                ctx,
                cmd,
                cwd,
                runtime_name="claude_code_cli",
                extra_env=extra_env if isinstance(extra_env, dict) else None,
            ),
            timeout=timeout,
        )

    async def _run_cli_agent_subprocess(
        self,
        ctx: ExecutionContext,
        cmd: List[str],
        cwd: str,
        runtime_name: str,
        last_message_path: Optional[str] = None,
        extra_env: Optional[Dict[str, str]] = None,
    ) -> ExecutionResult:
        before_files = self._snapshot_files(cwd)
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
        self._active[ctx.execution_id] = proc
        progress_task = asyncio.create_task(
            self._progress_ticker(ctx.execution_id, proc)
        )

        stdout_bytes, stderr_bytes = await proc.communicate()

        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass

        after_files = self._snapshot_files(cwd)
        files_created, files_modified = self._diff_file_snapshots(before_files, after_files)

        stdout = stdout_bytes.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE].strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE].strip()
        output = stdout

        if last_message_path and os.path.isfile(last_message_path):
            try:
                output = Path(last_message_path).read_text(encoding="utf-8").strip() or output
            except OSError:
                pass
        if not output and stderr:
            output = stderr

        if proc.returncode == 0:
            return ExecutionResult(
                status="completed",
                output=output or "(no response from agent)",
                files_modified=files_modified,
                files_created=files_created,
            )
        return ExecutionResult(
            status="failed",
            output=output,
            error=f"Exit code {proc.returncode}: {stderr[:500] or stdout[:500]}",
            files_modified=files_modified,
            files_created=files_created,
        )

    @staticmethod
    def _snapshot_files(root: str) -> Dict[str, tuple[int, int]]:
        if not root or not os.path.isdir(root):
            return {}
        snapshot: Dict[str, tuple[int, int]] = {}
        skip_dirs = {".git", "__pycache__", "node_modules", ".pytest_cache"}
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if name not in skip_dirs]
            for filename in filenames:
                full_path = os.path.join(dirpath, filename)
                try:
                    stat = os.stat(full_path)
                except OSError:
                    continue
                rel_path = os.path.relpath(full_path, root)
                snapshot[rel_path] = (stat.st_mtime_ns, stat.st_size)
        return snapshot

    @staticmethod
    def _diff_file_snapshots(
        before: Dict[str, tuple[int, int]],
        after: Dict[str, tuple[int, int]],
    ) -> tuple[List[str], List[str]]:
        created = sorted(path for path in after.keys() if path not in before)
        modified = sorted(
            path
            for path, after_meta in after.items()
            if path in before and before[path] != after_meta
        )
        return created, modified

    async def _run_subprocess(
        self,
        ctx: ExecutionContext,
        cmd: List[str],
        cwd: str,
    ) -> ExecutionResult:
        """Run a subprocess and stream output."""
        env = os.environ.copy()
        env["GEMINI_CLI_EXECUTION_ID"] = ctx.execution_id
        env["GEMINI_CLI_WORKSPACE_ID"] = ctx.workspace_id

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )

        self._active[ctx.execution_id] = proc

        # Report progress while waiting
        progress_task = asyncio.create_task(
            self._progress_ticker(ctx.execution_id, proc)
        )

        stdout_bytes, stderr_bytes = await proc.communicate()

        progress_task.cancel()
        try:
            await progress_task
        except asyncio.CancelledError:
            pass

        stdout = stdout_bytes.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE]
        stderr = stderr_bytes.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE]

        if proc.returncode == 0:
            return ExecutionResult(
                status="completed",
                output=stdout,
            )
        else:
            return ExecutionResult(
                status="failed",
                output=stdout,
                error=f"Exit code {proc.returncode}: {stderr[:500]}",
            )

    async def _progress_ticker(
        self,
        execution_id: str,
        proc: asyncio.subprocess.Process,
    ) -> None:
        """Send periodic progress updates while the subprocess runs."""
        pct = 15
        while pct < 90:
            await asyncio.sleep(5.0)
            if proc.returncode is not None:
                break
            await self._report_progress(execution_id, pct, "Executing task")
            pct = min(pct + 10, 90)

    async def _report_progress(
        self,
        execution_id: str,
        percent: int,
        message: str,
    ) -> None:
        """Report progress via the callback if set."""
        if self.progress_callback:
            try:
                await self.progress_callback(execution_id, percent, message)
            except Exception as e:
                logger.debug(f"[TaskExecutor] Progress callback error: {e}")

    # ============================================================
    #  Command builders
    # ============================================================

    @staticmethod
    def _default_command_builder(ctx: ExecutionContext) -> List[str]:
        """
        Default command builder: always delegates to the configured host runtime bridge.

        All tasks (shell commands and NL prompts alike) are routed through
        _execute_via_gemini_runtime_bridge() which invokes GEMINI_CLI_RUNTIME_CMD.
        The runtime bridge handles prompt construction and subprocess
        management safely.

        Previous implementation used prefix matching (e.g. "python", "git")
        to detect shell commands and run them via bash -c, which was
        dangerous: NL tasks starting with those prefixes would be
        misinterpreted as raw shell commands.
        """
        return []
