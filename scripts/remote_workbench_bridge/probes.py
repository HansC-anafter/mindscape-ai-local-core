"""Bounded probes for Remote Workbench bridge liveness."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


@dataclass(frozen=True)
class ProbeResult:
    """Sanitized result from one bounded liveness probe."""

    ok: bool
    code: str
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible representation."""

        return asdict(self)


class BridgeProbes:
    """Probe Docker, the local origin, connector, and public edge."""

    def __init__(
        self,
        *,
        launcher_path: Path,
        local_origin_url: str,
        connector_ready_url: str,
        public_origin_url: str,
        probe_timeout_seconds: float,
        public_timeout_seconds: float,
    ) -> None:
        self.launcher_path = launcher_path
        self.local_origin_url = local_origin_url
        self.connector_ready_url = connector_ready_url
        self.public_origin_url = public_origin_url
        self.probe_timeout_seconds = probe_timeout_seconds
        self.public_timeout_seconds = public_timeout_seconds

    def _command(self, args: Sequence[str]) -> ProbeResult:
        try:
            result = subprocess.run(
                list(args),
                check=False,
                capture_output=True,
                text=True,
                timeout=self.probe_timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ProbeResult(False, "command_unavailable")
        if result.returncode != 0:
            return ProbeResult(False, "command_failed")
        return ProbeResult(True, "ok")

    def docker(self) -> ProbeResult:
        """Check whether the Docker API is available."""

        return self._command(["docker", "info", "--format", "{{.ServerVersion}}"])

    def tunnel(self) -> ProbeResult:
        """Read the canonical launcher's sanitized tunnel status."""

        try:
            result = subprocess.run(
                [str(self.launcher_path), "status", "--json"],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.probe_timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ProbeResult(False, "launcher_unavailable")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return ProbeResult(False, "launcher_status_malformed")
        if result.returncode != 0 or payload.get("running") is not True:
            return ProbeResult(False, "tunnel_not_running")
        if payload.get("contract_conformant") is not True:
            return ProbeResult(False, "tunnel_contract_mismatch")
        return ProbeResult(True, "ok")

    def _http(self, url: str, *, timeout: float, allow_redirect: bool) -> ProbeResult:
        opener = (
            urllib.request.build_opener()
            if allow_redirect
            else urllib.request.build_opener(_NoRedirect())
        )
        request = urllib.request.Request(url, method="GET")
        try:
            with opener.open(request, timeout=timeout) as response:
                status = int(response.status)
        except urllib.error.HTTPError as error:
            status = int(error.code)
        except (urllib.error.URLError, TimeoutError, OSError):
            return ProbeResult(False, "http_unreachable")
        if 200 <= status < 400:
            return ProbeResult(True, "ok", str(status))
        return ProbeResult(False, "http_status", str(status))

    def local_origin(self) -> ProbeResult:
        """Check dependency-light local frontend liveness."""

        return self._http(
            self.local_origin_url,
            timeout=self.probe_timeout_seconds,
            allow_redirect=False,
        )

    def connector(self) -> ProbeResult:
        """Check the cloudflared connector readiness endpoint."""

        return self._http(
            self.connector_ready_url,
            timeout=self.probe_timeout_seconds,
            allow_redirect=False,
        )

    def public_origin(self) -> ProbeResult:
        """Require the exact Cloudflare Access redirect from the public edge."""

        result = self._http(
            self.public_origin_url,
            timeout=self.public_timeout_seconds,
            allow_redirect=False,
        )
        if result.ok and result.detail == "302":
            return result
        if result.ok:
            return ProbeResult(False, "access_redirect_missing", result.detail)
        return result
