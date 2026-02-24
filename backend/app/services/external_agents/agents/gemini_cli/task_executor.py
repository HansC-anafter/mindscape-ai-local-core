"""
TaskExecutor — IDE-side task execution engine for Gemini CLI Agent

Receives dispatch payloads from the WebSocket client and executes coding
tasks. Supports progress reporting via a callback function.

Architecture:
    GeminiCLIWSClient -> _handle_dispatch -> TaskExecutor.__call__
                                                   |
                                              execute task
                                                   |
                                              return result dict

Usage:
    executor = TaskExecutor(workspace_root="/path/to/project")
    client = GeminiCLIWSClient(
        workspace_id="ws-123",
        task_handler=executor,
    )
"""

import asyncio
import json
import logging
import os
import shlex
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
    project_id: str = ""
    intent_id: str = ""
    lens_id: str = ""
    sandbox_path: str = ""
    issued_at: str = ""
    conversation_context: str = ""
    thread_id: str = ""

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
            project_id=ctx.get("project_id", ""),
            intent_id=ctx.get("intent_id", ""),
            lens_id=ctx.get("lens_id", ""),
            sandbox_path=ctx.get("sandbox_path", ""),
            issued_at=msg.get("issued_at", ""),
            conversation_context=ctx.get("conversation_context", ""),
            thread_id=ctx.get("thread_id", ""),
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
#  TaskExecutor
# ============================================================


class TaskExecutor:
    """
    IDE-side task executor for Gemini CLI dispatch payloads.

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

        # Track active executions for cancellation
        self._active: Dict[str, asyncio.subprocess.Process] = {}

    async def __call__(
        self,
        dispatch_msg: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute a dispatch payload and return a result dict.

        This is the interface expected by GeminiCLIWSClient.task_handler.
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

        return result.to_dict()

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
            # Natural-language task path: delegate to IDE runtime bridge.
            return await self._execute_via_ide_runtime(ctx, timeout=timeout)

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

    async def _execute_via_ide_runtime(
        self,
        ctx: ExecutionContext,
        timeout: int,
    ) -> ExecutionResult:
        """
        Execute NL task via IDE runtime bridge command.

        The bridge command must be provided by env `GEMINI_CLI_RUNTIME_CMD`.
        It receives one JSON payload from stdin and should return JSON on stdout.
        """
        # Auto-discover bridge script: env override > project-relative path
        runtime_cmd = os.environ.get("GEMINI_CLI_RUNTIME_CMD", "").strip()
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
                    runtime_cmd = f"python3 {bridge_path}"
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

        argv = shlex.split(runtime_cmd)
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
            "task": ctx.task,
            "allowed_tools": ctx.allowed_tools,
            "max_duration": timeout,
            "backend_api_url": backend_url,
            "context": {
                "project_id": ctx.project_id,
                "intent_id": ctx.intent_id,
                "lens_id": ctx.lens_id,
                "sandbox_path": ctx.sandbox_path,
                "issued_at": ctx.issued_at,
                "conversation_context": ctx.conversation_context,
                "thread_id": ctx.thread_id,
            },
        }

        await self._report_progress(ctx.execution_id, 15, "Calling IDE runtime")
        cwd = self.workspace_root if os.path.isdir(self.workspace_root) else os.getcwd()

        # Inject per-task env vars so the MCP gateway can RAG-filter tools
        # for this specific task (not the parent process's stale env).
        sub_env = os.environ.copy()
        sub_env["MINDSCAPE_TASK_HINT"] = ctx.task[:500]
        sub_env["MINDSCAPE_WORKSPACE_ID"] = ctx.workspace_id

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
                error=f"IDE runtime command timed out after {timeout}s",
            )

        stdout = stdout_b.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE].strip()
        stderr = stderr_b.decode("utf-8", errors="replace")[:MAX_OUTPUT_SIZE].strip()
        if proc.returncode != 0:
            return ExecutionResult(
                status="failed",
                output=stdout,
                error=f"IDE runtime exit code {proc.returncode}: {stderr[:500]}",
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
        return result_dict

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
        Default command builder: always delegates to IDE runtime bridge.

        All tasks (shell commands and NL prompts alike) are routed through
        _execute_via_ide_runtime() which invokes GEMINI_CLI_RUNTIME_CMD.
        The runtime bridge handles prompt construction and subprocess
        management safely.

        Previous implementation used prefix matching (e.g. "python", "git")
        to detect shell commands and run them via bash -c, which was
        dangerous: NL tasks starting with those prefixes would be
        misinterpreted as raw shell commands.
        """
        return []
