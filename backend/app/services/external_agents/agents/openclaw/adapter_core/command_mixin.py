from .base import *


class OpenClawCommandMixin:

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
