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
        surface="codex_cli",
        task_handler=executor,
    )
"""

import asyncio
import json
import logging
import os
import re
import shlex
import shutil
import socket
import tempfile
import time
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
CODEX_POOL_MAX_TASK_ATTEMPTS = 3
DEFAULT_CLI_STALL_TIMEOUT_SECONDS = 180.0
DEFAULT_AUTH_BUNDLE_TIMEOUT_SECONDS = 20.0
DEFAULT_AUTH_BUNDLE_MAX_ATTEMPTS = 3
DEFAULT_AUTH_BUNDLE_RETRY_DELAY_SECONDS = 0.5
DEFAULT_QUOTA_REPORT_TIMEOUT_SECONDS = 10.0
DEFAULT_QUOTA_REPORT_MAX_ATTEMPTS = 2


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
    inputs: Dict[str, Any] = field(default_factory=dict)

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
            inputs=ctx.get("inputs", {}) if isinstance(ctx.get("inputs", {}), dict) else {},
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
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "status": self.status,
            "output": self.output,
            "error": self.error,
            "tool_calls": self.tool_calls,
            "files_modified": self.files_modified,
            "files_created": self.files_created,
        }
        if self.attachments:
            payload["attachments"] = self.attachments
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


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
        runtime_surface: Optional[str] = None,
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
        self.runtime_surface = (runtime_surface or "").strip().lower()
        if not self.runtime_surface:
            raise ValueError("runtime_surface is required for HostBridgeTaskExecutor")

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
        runtime_surface = self.runtime_surface
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
        timeout_seconds = self._parse_env_float(
            "MINDSCAPE_CLI_AUTH_BUNDLE_TIMEOUT_SECONDS",
            DEFAULT_AUTH_BUNDLE_TIMEOUT_SECONDS,
            minimum=1.0,
        )
        max_attempts = self._parse_env_int(
            "MINDSCAPE_CLI_AUTH_BUNDLE_MAX_ATTEMPTS",
            DEFAULT_AUTH_BUNDLE_MAX_ATTEMPTS,
            minimum=1,
        )
        retry_delay_seconds = self._parse_env_float(
            "MINDSCAPE_CLI_AUTH_BUNDLE_RETRY_DELAY_SECONDS",
            DEFAULT_AUTH_BUNDLE_RETRY_DELAY_SECONDS,
            minimum=0.0,
        )
        last_exc: Optional[BaseException] = None
        for attempt in range(1, max_attempts + 1):
            try:
                req = urllib.request.Request(url, method="GET")
                req.add_header("Accept", "application/json")
                with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
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
                last_exc = exc
                if attempt < max_attempts and self._is_retryable_http_error(exc):
                    time.sleep(retry_delay_seconds)
                    continue
                break

        logger.warning(
            "[TaskExecutor] Failed to fetch auth bundle for %s: %s",
            runtime_name,
            last_exc,
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

    def _report_runtime_quota_exhausted_sync(
        self,
        runtime_name: str,
        runtime_id: str,
    ) -> None:
        backend_url = self._resolve_backend_api_url()
        if not backend_url:
            return
        url = (
            f"{backend_url}/api/v1/auth/runtime-quota-exhausted?"
            f"{urllib.parse.urlencode({'surface': runtime_name, 'runtime_id': runtime_id})}"
        )
        timeout_seconds = self._parse_env_float(
            "MINDSCAPE_CLI_RUNTIME_QUOTA_REPORT_TIMEOUT_SECONDS",
            DEFAULT_QUOTA_REPORT_TIMEOUT_SECONDS,
            minimum=1.0,
        )
        max_attempts = self._parse_env_int(
            "MINDSCAPE_CLI_RUNTIME_QUOTA_REPORT_MAX_ATTEMPTS",
            DEFAULT_QUOTA_REPORT_MAX_ATTEMPTS,
            minimum=1,
        )
        last_exc: Optional[BaseException] = None
        for attempt in range(1, max_attempts + 1):
            try:
                req = urllib.request.Request(url, method="POST")
                req.add_header("Accept", "application/json")
                with urllib.request.urlopen(req, timeout=timeout_seconds):
                    return
            except (urllib.error.URLError, OSError) as exc:
                last_exc = exc
                if attempt < max_attempts and self._is_retryable_http_error(exc):
                    continue
                break
        logger.warning(
            "[TaskExecutor] Failed to report quota exhaustion for %s runtime %s",
            runtime_name,
            runtime_id,
        )

    @staticmethod
    def _parse_env_float(name: str, default: float, *, minimum: float) -> float:
        raw = os.environ.get(name, "").strip()
        if not raw:
            return default
        try:
            return max(minimum, float(raw))
        except ValueError:
            logger.warning(
                "[TaskExecutor] Invalid %s=%r; using %.1f",
                name,
                raw,
                default,
            )
            return default

    @staticmethod
    def _parse_env_int(name: str, default: int, *, minimum: int) -> int:
        raw = os.environ.get(name, "").strip()
        if not raw:
            return default
        try:
            return max(minimum, int(raw))
        except ValueError:
            logger.warning(
                "[TaskExecutor] Invalid %s=%r; using %d",
                name,
                raw,
                default,
            )
            return default

    @staticmethod
    def _is_retryable_http_error(exc: BaseException) -> bool:
        if isinstance(exc, TimeoutError | socket.timeout):
            return True
        if isinstance(exc, urllib.error.URLError):
            reason = exc.reason
            if isinstance(reason, TimeoutError | socket.timeout):
                return True
            if isinstance(reason, OSError) and "timed out" in str(reason).lower():
                return True
            return "timed out" in str(exc).lower()
        if isinstance(exc, OSError):
            return "timed out" in str(exc).lower()
        return False

    async def _report_runtime_quota_exhausted(
        self,
        runtime_name: str,
        runtime_id: str,
    ) -> None:
        if not runtime_id:
            return
        await asyncio.to_thread(
            self._report_runtime_quota_exhausted_sync,
            runtime_name,
            runtime_id,
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
        cwd, snapshot_root, snapshot_paths = self._resolve_cli_runtime_paths(ctx)
        stall_timeout = min(
            float(timeout),
            self._parse_env_float(
                "MINDSCAPE_CLI_STALL_TIMEOUT_SECONDS",
                DEFAULT_CLI_STALL_TIMEOUT_SECONDS,
                minimum=5.0,
            ),
        )

        control_cmd = self._build_codex_control_command(binary, ctx.control_action)
        if control_cmd:
            await self._report_progress(ctx.execution_id, 15, "Calling Codex CLI")
            return await asyncio.wait_for(
                self._run_cli_agent_subprocess(
                    ctx,
                    control_cmd,
                    cwd,
                    runtime_name="codex_cli",
                    snapshot_root=snapshot_root,
                    snapshot_paths=snapshot_paths,
                    stall_timeout=stall_timeout,
                ),
                timeout=timeout,
            )

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
        try:
            last_quota_error = ""
            attempt = 1
            while attempt <= max_attempts:
                auth_bundle = await self._fetch_runtime_auth_env("codex_cli", ctx)
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
                        metadata={"selected_runtime_id": None},
                    )
                if selected_runtime_id and selected_runtime_id in attempted_runtime_ids:
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
                        metadata={"selected_runtime_id": selected_runtime_id},
                    )

                progress_message = "Calling Codex CLI"
                if attempt > 1:
                    progress_message = f"Retrying Codex CLI via pool failover ({attempt}/{max_attempts})"
                await self._report_progress(ctx.execution_id, 15, progress_message)

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
                        stall_timeout=stall_timeout,
                    ),
                    timeout=timeout,
                )
                if result.status == "completed":
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
        cwd, snapshot_root, snapshot_paths = self._resolve_cli_runtime_paths(ctx)
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
        stall_timeout = min(
            float(timeout),
            self._parse_env_float(
                "MINDSCAPE_CLI_STALL_TIMEOUT_SECONDS",
                DEFAULT_CLI_STALL_TIMEOUT_SECONDS,
                minimum=5.0,
            ),
        )
        return await asyncio.wait_for(
            self._run_cli_agent_subprocess(
                ctx,
                cmd,
                cwd,
                runtime_name="claude_code_cli",
                snapshot_root=snapshot_root,
                snapshot_paths=snapshot_paths,
                extra_env=extra_env if isinstance(extra_env, dict) else None,
                stall_timeout=stall_timeout,
            ),
            timeout=timeout,
        )

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

        stdout = stdout_bytes.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE].strip()
        stderr = stderr_bytes.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE].strip()
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
                },
            )
        if synthesized_error:
            if selected_runtime_id and self._looks_like_quota_exhaustion(synthesized_error):
                await self._report_runtime_quota_exhausted(
                    runtime_name,
                    selected_runtime_id,
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
                },
            )
        if selected_runtime_id and self._looks_like_quota_exhaustion(stderr or stdout):
            await self._report_runtime_quota_exhausted(
                runtime_name,
                selected_runtime_id,
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
            error=f"Exit code {proc.returncode}: {stderr[:500] or stdout[:500]}",
            files_modified=files_modified,
            files_created=files_created,
            attachments=attachments,
            metadata={
                "effective_sandbox_path": resolved_snapshot_root or cwd,
                "selected_runtime_id": selected_runtime_id or None,
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
        communicate_task = asyncio.create_task(proc.communicate())
        if not stall_timeout or stall_timeout <= 0:
            return await communicate_task

        poll_interval = min(5.0, max(0.5, stall_timeout / 6.0))
        last_activity_at = time.monotonic()
        last_activity_signature = self._cli_activity_signature(
            last_message_path=last_message_path,
            snapshot_root=snapshot_root,
            snapshot_paths=snapshot_paths,
        )

        while True:
            done, _ = await asyncio.wait({communicate_task}, timeout=poll_interval)
            if communicate_task in done:
                return await communicate_task

            current_signature = self._cli_activity_signature(
                last_message_path=last_message_path,
                snapshot_root=snapshot_root,
                snapshot_paths=snapshot_paths,
            )
            if current_signature != last_activity_signature:
                last_activity_signature = current_signature
                last_activity_at = time.monotonic()
                continue

            if time.monotonic() - last_activity_at < stall_timeout:
                continue

            logger.warning(
                "[TaskExecutor] %s subprocess pid=%s stalled for %ss without message/file activity (%s)",
                runtime_name,
                proc.pid,
                int(stall_timeout),
                execution_id,
            )
            proc.kill()
            await communicate_task
            raise asyncio.TimeoutError(
                f"{runtime_name} subprocess stalled after {int(stall_timeout)}s without file or message activity"
            )

    @staticmethod
    def _cli_activity_signature(
        *,
        last_message_path: Optional[str],
        snapshot_root: str,
        snapshot_paths: Optional[List[str]],
    ) -> tuple[tuple[str, int, int], ...]:
        observed: List[tuple[str, int, int]] = []

        def _record(path: Path) -> None:
            try:
                stat = path.stat()
            except OSError:
                return
            observed.append((str(path), int(stat.st_size), int(stat.st_mtime_ns)))

        if last_message_path:
            candidate = Path(last_message_path)
            if candidate.is_file():
                _record(candidate)

        root_path = Path(snapshot_root) if snapshot_root else None
        if root_path and root_path.is_dir() and isinstance(snapshot_paths, list):
            seen_paths: set[str] = set()
            for raw_path in snapshot_paths:
                if not isinstance(raw_path, str):
                    continue
                normalized = raw_path.replace("\\", "/").lstrip("./")
                filename = os.path.basename(normalized)
                for probe in (normalized, filename):
                    if not probe:
                        continue
                    candidate = root_path / probe
                    candidate_str = str(candidate)
                    if candidate_str in seen_paths or not candidate.is_file():
                        continue
                    _record(candidate)
                    seen_paths.add(candidate_str)
                    break

        observed.sort()
        return tuple(observed)

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
        """Prefer Codex's final agent message; reject transcript-only fallbacks."""
        last_message = ""
        if last_message_path and os.path.isfile(last_message_path):
            try:
                last_message = Path(last_message_path).read_text(
                    encoding="utf-8"
                ).strip()
            except OSError:
                last_message = ""
        if last_message:
            return last_message, None

        transcript_only = "OpenAI Codex v" in stdout and "User instructions:" in stdout
        no_last_message = "no last agent message" in stderr.lower()
        codex_error = cls._extract_codex_cli_error(stdout=stdout, stderr=stderr)

        if codex_error:
            return "", codex_error
        if no_last_message or transcript_only:
            detail = "Codex CLI completed without producing a final agent message"
            if stderr:
                detail = f"{detail}; {stderr[:400]}"
            return "", detail

        output = stdout or stderr
        return output, None

    @staticmethod
    def _extract_codex_cli_error(*, stdout: str, stderr: str) -> Optional[str]:
        """Pull the most relevant Codex CLI error line from stderr/stdout."""
        for source in (stderr, stdout):
            if not source:
                continue
            matches = re.findall(
                r"(?:^|\n)(?:\[[^\n]*\]\s*)?ERROR:\s*(.+)",
                source,
                flags=re.MULTILINE,
            )
            if matches:
                return matches[-1].strip()
        return None

    @staticmethod
    def _looks_like_quota_exhaustion(message: str) -> bool:
        normalized = str(message or "").lower()
        if not normalized:
            return False
        markers = (
            "usage limit",
            "rate limit",
            "quota",
            "too many requests",
            "resource_exhausted",
            "429",
        )
        return any(marker in normalized for marker in markers)

    @classmethod
    def _should_retry_codex_runtime_fault(cls, result: ExecutionResult) -> bool:
        message = str((result.error or "") or (result.output or "")).strip()
        if cls._looks_like_quota_exhaustion(message):
            return True
        if result.status == "timeout":
            return True
        normalized = message.lower()
        return "subprocess stalled after" in normalized

    @staticmethod
    def _snapshot_files(
        root: str,
        *,
        only_paths: Optional[List[str]] = None,
    ) -> Dict[str, tuple[int, int]]:
        if not root or not os.path.isdir(root):
            return {}
        snapshot: Dict[str, tuple[int, int]] = {}
        if only_paths:
            for rel_path in only_paths:
                if not isinstance(rel_path, str):
                    continue
                normalized = rel_path.replace("\\", "/").lstrip("./")
                if not normalized:
                    continue
                full_path = os.path.join(root, normalized)
                if not os.path.isfile(full_path):
                    continue
                try:
                    stat = os.stat(full_path)
                except OSError:
                    continue
                snapshot[normalized] = (stat.st_mtime_ns, stat.st_size)
            return snapshot
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
