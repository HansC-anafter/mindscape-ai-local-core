from .base import *
from .schemas import ExecutionContext, ExecutionResult


class SubprocessMixin:

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
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
        )

        self._active[ctx.execution_id] = proc

        # Report progress while waiting
        progress_task = asyncio.create_task(
            self._progress_ticker(ctx.execution_id, proc, runtime_name="subprocess")
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
        *,
        runtime_name: str = "runtime",
        interval_seconds: float = 5.0,
    ) -> None:
        """Send periodic progress updates while the subprocess runs."""
        pct = 15
        elapsed = 0
        interval = max(0.1, float(interval_seconds))
        while True:
            await asyncio.sleep(interval)
            elapsed += int(interval)
            if proc.returncode is not None:
                break
            readable_runtime = "Codex CLI" if runtime_name == "codex_cli" else runtime_name
            await self._report_progress(
                execution_id,
                pct,
                f"Waiting for {readable_runtime} output ({elapsed}s elapsed)",
            )
            pct = min(pct + 10, 85)

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
