"""
Moltbot Agent Adapter

Adapter for executing Moltbot/OpenClaw within Mindscape's governance layer.
This adapter extends BaseAgentAdapter with Moltbot-specific implementation.
"""

import asyncio
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.services.external_agents.core.base_adapter import (
    BaseAgentAdapter,
    AgentRequest,
    AgentResponse,
)

logger = logging.getLogger(__name__)


class MoltbotAdapter(BaseAgentAdapter):
    """
    Moltbot/Claude Code Execution Adapter

    Extends BaseAgentAdapter with Claude Code CLI functionality:
    - CLI invocation via 'claude' or 'openclaw' command
    - Sandbox configuration generation
    - Execution trace collection

    Usage:
        adapter = MoltbotAdapter()
        if await adapter.is_available():
            response = await adapter.execute(request)
    """

    AGENT_NAME = "openclaw"
    AGENT_VERSION = "1.0.0"

    # CLI commands to try (in order of preference)
    CLI_COMMANDS = ["openclaw"]

    # Moltbot-specific denied tools
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
        Initialize Moltbot adapter.

        Args:
            cli_command: Command to invoke CLI (auto-detected if None)
            default_model: Default LLM model for Moltbot
        """
        super().__init__()
        self.cli_command = cli_command
        self.default_model = default_model
        self._detected_cli = None

    async def is_available(self) -> bool:
        """Check if any supported CLI is installed and accessible."""
        if self._available_cache is not None:
            return self._available_cache

        try:
            import subprocess

            # Try each CLI command in order
            commands_to_try = (
                [self.cli_command] if self.cli_command else self.CLI_COMMANDS
            )

            for cmd in commands_to_try:
                cli_path = shutil.which(cmd)
                if not cli_path:
                    continue

                result = subprocess.run(
                    [cmd, "--version"],
                    capture_output=True,
                    timeout=5,
                    text=True,
                )

                if result.returncode == 0:
                    self._detected_cli = cmd
                    self._version_cache = result.stdout.strip()
                    self._available_cache = True
                    logger.info(f"Agent CLI available: {cmd} ({self._version_cache})")
                    return True

            logger.warning(f"No supported CLI found. Tried: {commands_to_try}")
            self._available_cache = False
            return False

        except Exception as e:
            logger.warning(f"CLI availability check failed: {e}")
            self._available_cache = False
            return False

    def _get_cli_command(self) -> str:
        """Get the CLI command to use (detected or configured)."""
        return self._detected_cli or self.cli_command or "claude"

    async def execute(self, request: AgentRequest) -> AgentResponse:
        """
        Execute a Moltbot task within the sandbox.

        Args:
            request: The execution request with task and constraints

        Returns:
            AgentResponse with results and execution trace
        """
        self.log_execution_start(request)
        start_time = datetime.now()
        sandbox_path = Path(request.sandbox_path)

        # Validate sandbox path
        if not self.validate_sandbox_path(request.sandbox_path):
            return AgentResponse(
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

        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                self._run_moltbot(request, config_path),
                timeout=request.max_duration_seconds,
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Moltbot execution timed out after {request.max_duration_seconds}s"
            )
            return AgentResponse(
                success=False,
                output="",
                duration_seconds=request.max_duration_seconds,
                error=f"Execution timed out after {request.max_duration_seconds} seconds",
                exit_code=-1,
            )
        except Exception as e:
            logger.exception("Moltbot execution failed with exception")
            return AgentResponse(
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

        response = AgentResponse(
            success=result["returncode"] == 0,
            output=result["stdout"],
            duration_seconds=duration,
            tool_calls=trace.get("tool_calls", []),
            files_modified=files_modified,
            files_created=files_created,
            error=result["stderr"] if result["returncode"] != 0 else None,
            exit_code=result["returncode"],
        )

        self.log_execution_end(response)
        return response

    def _generate_sandbox_config(self, request: AgentRequest) -> Dict[str, Any]:
        """Generate a restricted Moltbot config for sandbox execution."""
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

    async def _run_moltbot(
        self, request: AgentRequest, config_path: Path
    ) -> Dict[str, Any]:
        """Actually run the CLI process."""
        cli = self._get_cli_command()
        cmd = [
            cli,
            "run",
            request.task,
            "--workspace",
            request.sandbox_path,
            "--config",
            str(config_path),
        ]

        logger.debug(f"Running {cli} command: {' '.join(cmd)}")

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=request.sandbox_path,
        )

        stdout, stderr = await proc.communicate()

        return {
            "returncode": proc.returncode,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
        }

    def _collect_trace(self, sandbox_path: Path) -> Dict[str, Any]:
        """Collect execution trace from Moltbot output files."""
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
