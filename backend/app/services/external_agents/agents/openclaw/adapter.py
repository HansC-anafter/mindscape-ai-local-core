"""
OpenClaw Runtime Adapter

Adapter for executing OpenClaw within Mindscape's governance layer.
This adapter extends BaseRuntimeAdapter with OpenClaw-specific implementation.
"""

import asyncio
import json
import logging
import os
import shutil
import signal
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.app.services.external_agents.core.base_adapter import (
    BaseRuntimeAdapter,
    RuntimeExecRequest,
    RuntimeExecResponse,
)

logger = logging.getLogger(__name__)


class OpenClawAdapter(BaseRuntimeAdapter):
    """
    OpenClaw Code Execution Adapter

    Extends BaseRuntimeAdapter with OpenClaw CLI functionality:
    - CLI invocation via 'openclaw' command
    - Sandbox configuration generation
    - Execution trace collection

    Usage:
        adapter = OpenClawAdapter()
        if await adapter.is_available():
            response = await adapter.execute(request)
    """

    RUNTIME_NAME = "openclaw"
    RUNTIME_VERSION = "1.0.0"

    # CLI commands to try (in order of preference)
    CLI_COMMANDS = ["openclaw"]

    # OpenClaw-specific denied tools
    ALWAYS_DENIED_TOOLS = [
        "system.run",
        "gateway",
        "docker",
    ]

    def __init__(
        self,
        cli_command: str = None,  # Auto-detect if not specified
        default_model: str = "anthropic/claude-sonnet-4-20250514",
    ):
        """
        Initialize OpenClaw adapter.

        Args:
            cli_command: Command to invoke CLI (auto-detected if None)
            default_model: Default LLM model for OpenClaw
        """
        super().__init__()
        self.cli_command = cli_command
        self.default_model = default_model
        self._detected_cli = None
        self._availability_detail_cache: Optional[Dict[str, Any]] = None

    async def is_available(self, **kwargs) -> bool:
        """Check if OpenClaw is installed and has runnable auth."""
        detail = self.get_availability_detail()
        return bool(detail.get("available"))

    def get_availability_detail(self, workspace_id: str = None) -> Dict[str, Any]:
        """Return CLI and auth readiness without hanging the API."""
        if self._availability_detail_cache is not None:
            return self._availability_detail_cache

        commands_to_try = [self.cli_command] if self.cli_command else self.CLI_COMMANDS
        for cmd in commands_to_try:
            cli_path = shutil.which(cmd)
            if not cli_path:
                continue

            version_probe = self._run_cli_probe([cmd, "--version"], timeout=3.0)
            if version_probe["returncode"] != 0 or version_probe["timed_out"]:
                continue

            self._detected_cli = cmd
            self._version_cache = (version_probe["stdout"].strip().splitlines() or [""])[0]

            auth_probe = self._run_cli_probe([cmd, "models", "status"], timeout=3.0)
            output = f"{auth_probe['stdout']}\n{auth_probe['stderr']}".lower()
            if (
                "missing auth" in output
                or "no api key" in output
                or "providers w/ oauth/tokens (0)" in output
                or "providers with oauth/tokens (0)" in output
            ):
                return self._cache_availability(
                    available=False,
                    reason="missing_auth",
                    transport="cli",
                    version=self._version_cache,
                )
            if auth_probe["timed_out"]:
                return self._cache_availability(
                    available=False,
                    reason="auth_probe_timeout",
                    transport="cli",
                    version=self._version_cache,
                )
            if auth_probe["returncode"] != 0:
                return self._cache_availability(
                    available=False,
                    reason="auth_probe_failed",
                    transport="cli",
                    version=self._version_cache,
                )

            logger.info("OpenClaw CLI available: %s (%s)", cmd, self._version_cache)
            return self._cache_availability(
                available=True,
                reason="cli_auth_ready",
                transport="cli",
                version=self._version_cache,
            )

        logger.warning("No supported OpenClaw CLI found. Tried: %s", commands_to_try)
        return self._cache_availability(
            available=False,
            reason="no_cli",
            transport=None,
            version=None,
        )

    def _cache_availability(
        self,
        *,
        available: bool,
        reason: str,
        transport: Optional[str],
        version: Optional[str],
    ) -> Dict[str, Any]:
        self._available_cache = available
        if version:
            self._version_cache = version
        else:
            self._version_cache = reason
        self._availability_detail_cache = {
            "available": available,
            "transport": transport,
            "reason": reason,
            "version": version,
        }
        return self._availability_detail_cache

    @staticmethod
    def _run_cli_probe(args: List[str], timeout: float) -> Dict[str, Any]:
        """Run a short CLI readiness probe and kill its process group on timeout."""
        try:
            import subprocess

            proc = subprocess.Popen(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                start_new_session=True,
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout)
                return {
                    "returncode": proc.returncode,
                    "stdout": stdout or "",
                    "stderr": stderr or "",
                    "timed_out": False,
                }
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    proc.kill()
                stdout, stderr = proc.communicate()
                return {
                    "returncode": proc.returncode,
                    "stdout": stdout or "",
                    "stderr": stderr or "",
                    "timed_out": True,
                }
        except Exception as exc:
            return {
                "returncode": -1,
                "stdout": "",
                "stderr": str(exc),
                "timed_out": False,
            }

    def _get_cli_command(self) -> str:
        """Get the CLI command to use (detected or configured)."""
        return self._detected_cli or self.cli_command or "openclaw"

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

    def _build_cli_command(self, request: RuntimeExecRequest) -> Tuple[List[str], str]:
        """Build a current OpenClaw CLI command for headless execution."""
        cli = self._get_cli_command()
        config = request.agent_config or {}
        surface = str(
            config.get("openclaw_surface")
            or config.get("openclaw_execution_surface")
            or "agent"
        ).strip().lower()

        if surface == "agent":
            session_id = str(
                config.get("meeting_session_id")
                or config.get("session_id")
                or request.intent_id
                or request.workspace_id
                or "mindscape"
            )
            cmd = [
                cli,
                "agent",
                "--message",
                request.task,
                "--session-id",
                session_id,
                "--json",
                "--timeout",
                str(max(1, int(request.max_duration_seconds or 300))),
            ]
            agent_id = config.get("openclaw_agent_id") or config.get("agent")
            if agent_id:
                cmd.extend(["--agent", str(agent_id)])
            thinking = config.get("thinking") or config.get("openclaw_thinking")
            if thinking:
                cmd.extend(["--thinking", str(thinking)])
            if bool(config.get("openclaw_local")):
                cmd.append("--local")
            return cmd, "agent"

        cmd = [
            cli,
            "infer",
            "model",
            "run",
            "--prompt",
            request.task,
            "--json",
        ]
        model = config.get("openclaw_model") or config.get("model")
        provider = config.get("openclaw_provider") or config.get("provider")
        if model:
            cmd.extend(["--model", str(model)])
        elif provider:
            cmd.extend(["--provider", str(provider)])
        return cmd, "infer.model.run"

    @staticmethod
    def _redact_command(cmd: List[str]) -> List[str]:
        redacted: List[str] = []
        redact_next = False
        for part in cmd:
            if redact_next:
                redacted.append("<redacted>")
                redact_next = False
                continue
            redacted.append(part)
            if part in {"--message", "--prompt"}:
                redact_next = True
        return redacted

    async def _terminate_process(self, proc: asyncio.subprocess.Process) -> None:
        """Terminate a timed-out OpenClaw subprocess and its children."""
        if proc.returncode is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except Exception:
            logger.warning("Failed to SIGTERM OpenClaw process group", exc_info=True)
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
            return
        except asyncio.TimeoutError:
            pass
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            return
        except Exception:
            logger.warning("Failed to SIGKILL OpenClaw process group", exc_info=True)
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except Exception:
            logger.warning("OpenClaw subprocess did not exit cleanly after SIGKILL")

    @staticmethod
    def _parse_openclaw_json_output(stdout: str) -> Dict[str, Any]:
        text = (stdout or "").strip()
        if not text:
            return {}
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return {"output": text}

        output = (
            payload.get("output")
            or payload.get("text")
            or payload.get("message")
            or payload.get("result")
        )
        outputs = payload.get("outputs")
        if not output and isinstance(outputs, list):
            for item in outputs:
                if isinstance(item, str) and item.strip():
                    output = item
                    break
                if isinstance(item, dict):
                    candidate = (
                        item.get("text")
                        or item.get("content")
                        or item.get("output")
                        or item.get("message")
                    )
                    if candidate:
                        output = candidate
                        break

        error = payload.get("error")
        if isinstance(error, dict):
            error = error.get("message") or json.dumps(error, ensure_ascii=False)

        return {
            "ok": payload.get("ok"),
            "output": output or json.dumps(payload, ensure_ascii=False),
            "error": error,
            "raw_json": payload,
        }

    def _collect_trace(self, sandbox_path: Path) -> Dict[str, Any]:
        """Collect execution trace from OpenClaw output files."""
        trace_file = sandbox_path / ".openclaw" / "execution_trace.json"

        if trace_file.exists():
            try:
                return json.loads(trace_file.read_text())
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse execution trace: {trace_file}")

        return {"tool_calls": [], "files_modified": []}

    def _snapshot_files(self, sandbox_path: Path) -> Dict[str, float]:
        """Take a snapshot of file mtimes in the sandbox."""
        snapshot = {}
        try:
            for file_path in sandbox_path.rglob("*"):
                if file_path.is_file() and ".openclaw" not in str(file_path):
                    rel_path = str(file_path.relative_to(sandbox_path))
                    snapshot[rel_path] = file_path.stat().st_mtime
        except Exception as e:
            logger.warning(f"Failed to snapshot files: {e}")
        return snapshot

    def _diff_files(
        self, before: Dict[str, float], after: Dict[str, float]
    ) -> tuple[List[str], List[str]]:
        """Compare file snapshots to find created and modified files."""
        created = []
        modified = []

        for path, mtime in after.items():
            if path not in before:
                created.append(path)
            elif before[path] != mtime:
                modified.append(path)

        return created, modified
