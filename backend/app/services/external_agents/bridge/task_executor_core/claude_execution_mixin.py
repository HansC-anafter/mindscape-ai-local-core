from .base import *
from .schemas import ExecutionContext, ExecutionResult


class ClaudeExecutionMixin:

    async def _execute_via_claude_code_cli(
        self,
        ctx: ExecutionContext,
        timeout: int,
    ) -> ExecutionResult:
        binary = self._resolve_runtime_binary("claude_code_cli")
        prompt = self._build_runtime_prompt(ctx)
        cwd, snapshot_root, snapshot_paths = self._resolve_cli_runtime_paths(ctx)
        auth_bundle = await self._fetch_runtime_auth_env("claude_code_cli", ctx)
        if isinstance(auth_bundle, dict) and auth_bundle.get("error"):
            return ExecutionResult(
                status="failed",
                output="",
                error=str(auth_bundle.get("error")),
                metadata={"selected_runtime_id": None},
            )
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
        cmd.append("--")
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
