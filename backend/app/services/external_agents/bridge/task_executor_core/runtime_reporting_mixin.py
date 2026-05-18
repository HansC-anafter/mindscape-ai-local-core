from .base import *
from .schemas import ExecutionContext, ExecutionResult


class RuntimeReportingMixin:

    @staticmethod
    def _resolve_backend_api_url() -> str:
        backend_url = os.environ.get("MINDSCAPE_BACKEND_API_URL", "").strip()
        if not backend_url:
            ws_host = os.environ.get("MINDSCAPE_WS_HOST", "").strip()
            if ws_host:
                backend_url = (
                    ws_host
                    if ws_host.startswith("http://") or ws_host.startswith("https://")
                    else f"http://{ws_host}"
                )
        return backend_url.rstrip("/")

    @classmethod
    def _resolve_backend_api_urls(cls) -> List[str]:
        base_url = cls._resolve_backend_api_url()
        if not base_url:
            return []

        parsed = urllib.parse.urlsplit(base_url)
        scheme = parsed.scheme or "http"
        host = (parsed.hostname or "").strip()
        port = parsed.port
        path = parsed.path.rstrip("/")

        hosts: List[str] = []
        if host:
            hosts.append(host)
            if host in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}:
                hosts.extend(["localhost", "127.0.0.1", "0.0.0.0", "host.docker.internal"])

        def _format_host(candidate_host: str) -> str:
            if ":" in candidate_host and not candidate_host.startswith("["):
                candidate_host = f"[{candidate_host}]"
            if port is None:
                return candidate_host
            return f"{candidate_host}:{port}"

        candidates: List[str] = []
        for candidate_host in hosts:
            candidate = f"{scheme}://{_format_host(candidate_host)}{path}"
            if candidate not in candidates:
                candidates.append(candidate)
        return candidates or [base_url]

    def _fetch_runtime_auth_bundle_sync(
        self,
        runtime_name: str,
        ctx: ExecutionContext,
        *,
        excluded_runtime_ids: Optional[set[str]] = None,
    ) -> Dict[str, Any]:
        backend_urls = self._resolve_backend_api_urls()
        if not backend_urls:
            return {
                "error": f"No backend API available for {runtime_name} auth bundle resolution",
            }

        params = {"surface": runtime_name}
        if ctx.workspace_id:
            params["workspace_id"] = ctx.workspace_id
        if ctx.auth_workspace_id:
            params["auth_workspace_id"] = ctx.auth_workspace_id
        if ctx.source_workspace_id:
            params["source_workspace_id"] = ctx.source_workspace_id
        if excluded_runtime_ids:
            params["exclude_runtime_ids"] = ",".join(sorted(excluded_runtime_ids))
        query = urllib.parse.urlencode(params)
        timeout_seconds = self._parse_env_float(
            "MINDSCAPE_CLI_AUTH_BUNDLE_TIMEOUT_SECONDS",
            DEFAULT_AUTH_BUNDLE_TIMEOUT_SECONDS,
            minimum=1.0,
        )
        max_attempts = self._parse_env_int(
            "MINDSCAPE_CLI_AUTH_BUNDLE_MAX_ATTEMPTS",
            DEFAULT_AUTH_BUNDLE_MAX_ATTEMPTS,
            minimum=1,
        )
        retry_delay_seconds = self._parse_env_float(
            "MINDSCAPE_CLI_AUTH_BUNDLE_RETRY_DELAY_SECONDS",
            DEFAULT_AUTH_BUNDLE_RETRY_DELAY_SECONDS,
            minimum=0.0,
        )
        last_exc: Optional[BaseException] = None
        for attempt in range(1, max_attempts + 1):
            for backend_url in backend_urls:
                try:
                    req = urllib.request.Request(
                        f"{backend_url}/api/v1/auth/cli-token?{query}",
                        method="GET",
                    )
                    req.add_header("Accept", "application/json")
                    with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                        data = json.loads(resp.read().decode())
                    env = data.get("env")
                    data["env"] = (
                        {
                            str(key): str(value)
                            for key, value in env.items()
                            if value is not None and str(value) != ""
                        }
                        if isinstance(env, dict)
                        else {}
                    )
                    return data
                except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
                    last_exc = exc
                    continue
            if attempt < max_attempts and last_exc and self._is_retryable_http_error(last_exc):
                time.sleep(retry_delay_seconds)
                continue
            break

        logger.warning(
            "[TaskExecutor] Failed to fetch auth bundle for %s: %s",
            runtime_name,
            last_exc,
        )
        return {
            "error": f"Failed to fetch auth bundle for {runtime_name}: {last_exc}",
        }

    async def _fetch_runtime_auth_env(
        self,
        runtime_name: str,
        ctx: ExecutionContext,
        *,
        excluded_runtime_ids: Optional[set[str]] = None,
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(
            self._fetch_runtime_auth_bundle_sync,
            runtime_name,
            ctx,
            excluded_runtime_ids=excluded_runtime_ids,
        )

    @staticmethod
    def _codex_cli_model_hint(model: str) -> str:
        candidate = str(model or "").strip()
        if not candidate:
            return ""
        lowered = candidate.lower()
        if lowered.startswith(("gpt-", "o", "codex")):
            return candidate
        return ""

    def _report_runtime_quota_exhausted_sync(
        self,
        runtime_name: str,
        runtime_id: str,
        *,
        workspace_id: str = "",
        effective_workspace_id: str = "",
        error_text: str = "",
    ) -> None:
        backend_urls = self._resolve_backend_api_urls()
        if not backend_urls:
            return
        params = {"surface": runtime_name, "runtime_id": runtime_id}
        if workspace_id:
            params["workspace_id"] = workspace_id
        if effective_workspace_id:
            params["effective_workspace_id"] = effective_workspace_id
        if error_text:
            params["error_text"] = error_text[:1000]
        query = urllib.parse.urlencode(params)
        timeout_seconds = self._parse_env_float(
            "MINDSCAPE_CLI_RUNTIME_QUOTA_REPORT_TIMEOUT_SECONDS",
            DEFAULT_QUOTA_REPORT_TIMEOUT_SECONDS,
            minimum=1.0,
        )
        max_attempts = self._parse_env_int(
            "MINDSCAPE_CLI_RUNTIME_QUOTA_REPORT_MAX_ATTEMPTS",
            DEFAULT_QUOTA_REPORT_MAX_ATTEMPTS,
            minimum=1,
        )
        last_exc: Optional[BaseException] = None
        for attempt in range(1, max_attempts + 1):
            for backend_url in backend_urls:
                try:
                    req = urllib.request.Request(
                        f"{backend_url}/api/v1/auth/runtime-quota-exhausted?{query}",
                        method="POST",
                    )
                    req.add_header("Accept", "application/json")
                    with urllib.request.urlopen(req, timeout=timeout_seconds):
                        return
                except (urllib.error.URLError, OSError) as exc:
                    last_exc = exc
                    continue
            if attempt < max_attempts and last_exc and self._is_retryable_http_error(last_exc):
                continue
            break
        logger.warning(
            "[TaskExecutor] Failed to report quota exhaustion for %s runtime %s",
            runtime_name,
            runtime_id,
        )

    def _report_runtime_auth_failure_sync(
        self,
        runtime_name: str,
        runtime_id: str,
        *,
        error_code: str = "401",
        workspace_id: str = "",
        effective_workspace_id: str = "",
    ) -> None:
        backend_urls = self._resolve_backend_api_urls()
        if not backend_urls:
            return
        params = {
            "surface": runtime_name,
            "runtime_id": runtime_id,
            "error_code": error_code,
        }
        if workspace_id:
            params["workspace_id"] = workspace_id
        if effective_workspace_id:
            params["effective_workspace_id"] = effective_workspace_id
        query = urllib.parse.urlencode(params)
        timeout_seconds = self._parse_env_float(
            "MINDSCAPE_CLI_RUNTIME_QUOTA_REPORT_TIMEOUT_SECONDS",
            DEFAULT_QUOTA_REPORT_TIMEOUT_SECONDS,
            minimum=1.0,
        )
        max_attempts = self._parse_env_int(
            "MINDSCAPE_CLI_RUNTIME_QUOTA_REPORT_MAX_ATTEMPTS",
            DEFAULT_QUOTA_REPORT_MAX_ATTEMPTS,
            minimum=1,
        )
        last_exc: Optional[BaseException] = None
        for attempt in range(1, max_attempts + 1):
            for backend_url in backend_urls:
                try:
                    req = urllib.request.Request(
                        f"{backend_url}/api/v1/auth/runtime-auth-failure?{query}",
                        method="POST",
                    )
                    req.add_header("Accept", "application/json")
                    with urllib.request.urlopen(req, timeout=timeout_seconds):
                        return
                except (urllib.error.URLError, OSError) as exc:
                    last_exc = exc
                    continue
            if attempt < max_attempts and last_exc and self._is_retryable_http_error(last_exc):
                continue
            break
        logger.warning(
            "[TaskExecutor] Failed to report auth failure for %s runtime %s: %s",
            runtime_name,
            runtime_id,
            last_exc,
        )

    def _report_runtime_success_sync(
        self,
        runtime_name: str,
        runtime_id: str,
    ) -> None:
        backend_urls = self._resolve_backend_api_urls()
        if not backend_urls:
            return
        params = {"surface": runtime_name, "runtime_id": runtime_id}
        query = urllib.parse.urlencode(params)
        timeout_seconds = self._parse_env_float(
            "MINDSCAPE_CLI_RUNTIME_QUOTA_REPORT_TIMEOUT_SECONDS",
            DEFAULT_QUOTA_REPORT_TIMEOUT_SECONDS,
            minimum=1.0,
        )
        max_attempts = self._parse_env_int(
            "MINDSCAPE_CLI_RUNTIME_QUOTA_REPORT_MAX_ATTEMPTS",
            DEFAULT_QUOTA_REPORT_MAX_ATTEMPTS,
            minimum=1,
        )
        last_exc: Optional[BaseException] = None
        for attempt in range(1, max_attempts + 1):
            for backend_url in backend_urls:
                try:
                    req = urllib.request.Request(
                        f"{backend_url}/api/v1/auth/runtime-success?{query}",
                        method="POST",
                    )
                    req.add_header("Accept", "application/json")
                    with urllib.request.urlopen(req, timeout=timeout_seconds):
                        return
                except (urllib.error.URLError, OSError) as exc:
                    last_exc = exc
                    continue
            if attempt < max_attempts and last_exc and self._is_retryable_http_error(last_exc):
                continue
            break
        logger.warning(
            "[TaskExecutor] Failed to report runtime success for %s runtime %s: %s",
            runtime_name,
            runtime_id,
            last_exc,
        )

    @staticmethod
    def _parse_env_float(name: str, default: float, *, minimum: float) -> float:
        raw = os.environ.get(name, "").strip()
        if not raw:
            return default
        try:
            return max(minimum, float(raw))
        except ValueError:
            logger.warning(
                "[TaskExecutor] Invalid %s=%r; using %.1f",
                name,
                raw,
                default,
            )
            return default

    @staticmethod
    def _parse_env_int(name: str, default: int, *, minimum: int) -> int:
        raw = os.environ.get(name, "").strip()
        if not raw:
            return default
        try:
            return max(minimum, int(raw))
        except ValueError:
            logger.warning(
                "[TaskExecutor] Invalid %s=%r; using %d",
                name,
                raw,
                default,
            )
            return default

    @staticmethod
    def _is_retryable_http_error(exc: BaseException) -> bool:
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return True
        if isinstance(exc, urllib.error.URLError):
            reason = exc.reason
            if isinstance(reason, (TimeoutError, socket.timeout)):
                return True
            if isinstance(reason, OSError) and "timed out" in str(reason).lower():
                return True
            return "timed out" in str(exc).lower()
        if isinstance(exc, OSError):
            return "timed out" in str(exc).lower()
        return False

    async def _report_runtime_quota_exhausted(
        self,
        runtime_name: str,
        runtime_id: str,
        *,
        workspace_id: str = "",
        effective_workspace_id: str = "",
        error_text: str = "",
    ) -> None:
        if not runtime_id:
            return
        await asyncio.to_thread(
            self._report_runtime_quota_exhausted_sync,
            runtime_name,
            runtime_id,
            workspace_id=workspace_id,
            effective_workspace_id=effective_workspace_id,
            error_text=error_text,
        )

    async def _report_runtime_auth_failure(
        self,
        runtime_name: str,
        runtime_id: str,
        *,
        error_code: str = "401",
        workspace_id: str = "",
        effective_workspace_id: str = "",
    ) -> None:
        if not runtime_id:
            return
        await asyncio.to_thread(
            self._report_runtime_auth_failure_sync,
            runtime_name,
            runtime_id,
            error_code=error_code,
            workspace_id=workspace_id,
            effective_workspace_id=effective_workspace_id,
        )

    async def _report_runtime_success(
        self,
        runtime_name: str,
        runtime_id: str,
    ) -> None:
        if not runtime_id:
            return
        await asyncio.to_thread(
            self._report_runtime_success_sync,
            runtime_name,
            runtime_id,
        )
