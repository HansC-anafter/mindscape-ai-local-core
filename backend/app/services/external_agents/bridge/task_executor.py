"""Host bridge task executor compatibility entrypoint."""

from .task_executor_core.base import *
from .task_executor_core.cli_paths_mixin import CliPathsMixin
from .task_executor_core.codex_control_mixin import CodexControlMixin
from .task_executor_core.claude_execution_mixin import ClaudeExecutionMixin
from .task_executor_core.codex_execution_mixin import CodexExecutionMixin
from .task_executor_core.runtime_execution_mixin import RuntimeExecutionMixin
from .task_executor_core.runtime_reporting_mixin import RuntimeReportingMixin
from .task_executor_core.schemas import (
    ExecutionContext,
    ExecutionResult,
    ProgressCallback,
)
from .task_executor_core.subprocess_mixin import SubprocessMixin


class HostBridgeTaskExecutor(
    RuntimeReportingMixin,
    CodexControlMixin,
    RuntimeExecutionMixin,
    CodexExecutionMixin,
    ClaudeExecutionMixin,
    CliPathsMixin,
    SubprocessMixin,
):
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
