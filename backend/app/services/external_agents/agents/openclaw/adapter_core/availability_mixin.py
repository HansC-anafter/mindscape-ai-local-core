from .base import *


class OpenClawAvailabilityMixin:

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
