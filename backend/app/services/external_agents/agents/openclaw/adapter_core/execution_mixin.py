from .base import *


class OpenClawExecutionMixin:

    async def execute(self, request: RuntimeExecRequest) -> RuntimeExecResponse:
        """
        Execute an OpenClaw task within the sandbox.

        Args:
            request: The execution request with task and constraints

        Returns:
            RuntimeExecResponse with results and execution trace
        """
        self.log_execution_start(request)
        start_time = datetime.now()
        sandbox_path = Path(request.sandbox_path)

        # Validate sandbox path
        if not self.validate_sandbox_path(request.sandbox_path):
            return RuntimeExecResponse(
                success=False,
                output="",
                duration_seconds=0,
                error=f"Invalid sandbox path: {request.sandbox_path}",
            )

        # Ensure sandbox exists
        sandbox_path.mkdir(parents=True, exist_ok=True)

        # Take snapshot of files before execution
        files_before = self._snapshot_files(sandbox_path)

        # Generate restricted config
        config = self._generate_sandbox_config(request)
        config_dir = sandbox_path / ".openclaw"
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / "openclaw.json"
        config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False))

        try:
            result = await self._run_openclaw(request, config_path)
        except Exception as e:
            logger.exception("OpenClaw execution failed with exception")
            return RuntimeExecResponse(
                success=False,
                output="",
                duration_seconds=(datetime.now() - start_time).total_seconds(),
                error=str(e),
                exit_code=-1,
            )

        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds()

        # Collect execution trace
        trace = self._collect_trace(sandbox_path)
        files_after = self._snapshot_files(sandbox_path)
        files_created, files_modified = self._diff_files(files_before, files_after)
        parsed_output = self._parse_openclaw_json_output(result["stdout"])
        output = parsed_output.get("output") or result["stdout"]
        cli_reported_ok = parsed_output.get("ok")
        success = result["returncode"] == 0 and cli_reported_ok is not False
        error = (
            result["stderr"]
            or parsed_output.get("error")
            or ("OpenClaw returned empty output" if success and not output else None)
        )
        if success and error:
            success = False

        response = RuntimeExecResponse(
            success=success,
            output=output,
            duration_seconds=duration,
            tool_calls=trace.get("tool_calls", []),
            files_modified=files_modified,
            files_created=files_created,
            error=error if not success else None,
            exit_code=result["returncode"],
            agent_metadata={
                "openclaw_surface": result.get("surface"),
                "openclaw_command": result.get("command"),
                "openclaw_json": parsed_output.get("raw_json"),
            },
        )

        self.log_execution_end(response)
        return response

    def _generate_sandbox_config(self, request: RuntimeExecRequest) -> Dict[str, Any]:
        """Generate a restricted OpenClaw config for sandbox execution."""
        all_denied = self.merge_denied_tools(request.denied_tools)

        return {
            "agent": {
                "model": self.default_model,
                "workspace": request.sandbox_path,
            },
            "sandbox": {
                "mode": "always",
                "allowedTools": request.allowed_tools,
                "deniedTools": all_denied,
            },
            "_mindscape": {
                "controlled": True,
                "project_id": request.project_id,
                "workspace_id": request.workspace_id,
                "intent_id": request.intent_id,
                "lens_id": request.lens_id,
                "execution_started_at": datetime.now().isoformat(),
            },
        }

    async def _run_openclaw(
        self, request: RuntimeExecRequest, config_path: Path
    ) -> Dict[str, Any]:
        """Actually run the CLI process."""
        cmd, surface = self._build_cli_command(request)

        logger.debug("Running OpenClaw command: %s", " ".join(cmd))

        env = os.environ.copy()
        env.setdefault("NO_COLOR", "1")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=request.sandbox_path,
            env=env,
            start_new_session=True,
        )

        timeout_seconds = max(1, int(request.max_duration_seconds or 300))
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_seconds,
            )
        except asyncio.TimeoutError:
            await self._terminate_process(proc)
            return {
                "returncode": -9,
                "stdout": "",
                "stderr": (
                    f"OpenClaw {surface} command timed out after "
                    f"{timeout_seconds} seconds"
                ),
                "surface": surface,
                "command": self._redact_command(cmd),
            }

        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "surface": surface,
            "command": self._redact_command(cmd),
        }
