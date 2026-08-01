from .base import *


class HostBridgeRegistrationMixin:

    @staticmethod
    def _host_session_registration_fingerprint(
        payloads: list[Dict[str, Any]],
    ) -> str:
        normalized: list[Dict[str, Any]] = []
        for payload in payloads:
            item = copy.deepcopy(payload)
            metadata = item.get("metadata")
            if isinstance(metadata, dict):
                metadata.pop("seed_last_seen_at", None)
            normalized.append(item)
        serialized = json.dumps(
            normalized,
            sort_keys=True,
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return hashlib.sha1(serialized.encode("utf-8")).hexdigest()

    def _host_session_registration_backoff_seconds(self) -> float:
        failures = max(0, self._host_session_runtime_registration_failure_count - 1)
        return min(
            self.HOST_SESSION_REGISTER_RETRY_INTERVAL * (2**failures),
            self.HOST_SESSION_REGISTER_REFRESH_INTERVAL,
        )

    def _register_host_session_runtime_sync(
        self,
        payloads: Optional[list[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        if not self.backend_api_urls:
            raise RuntimeError("MINDSCAPE_BACKEND_API_URL is not configured")

        runtime_payloads = (
            payloads
            if payloads is not None
            else self._build_host_session_runtime_registration_payloads()
        )
        if not runtime_payloads:
            return {}

        _backend_url, body = self._backend_request_sync(
            lambda backend_url: urllib.request.Request(
                f"{backend_url}/api/v1/auth/cli-runtime/register-host-sessions",
                data=json.dumps({"runtimes": runtime_payloads}).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            ),
            timeout=self.HOST_SESSION_REGISTER_TIMEOUT,
        )
        return json.loads(body) if body else {}

    async def _maybe_register_host_session_runtime(self) -> None:
        if not self._should_auto_register_host_session_runtime():
            return
        payloads = self._build_host_session_runtime_registration_payloads()
        fingerprint = self._host_session_registration_fingerprint(payloads)
        now = time.monotonic()
        if (
            self._host_session_runtime_registered
            and fingerprint == self._host_session_runtime_last_registered_fingerprint
            and now
            < (
                self._host_session_runtime_last_success_at
                + self.HOST_SESSION_REGISTER_REFRESH_INTERVAL
            )
        ):
            return
        if (
            fingerprint == self._host_session_runtime_last_attempt_fingerprint
            and now < self._host_session_runtime_next_attempt_at
        ):
            return
        self._host_session_runtime_last_attempt_fingerprint = fingerprint
        try:
            response = await asyncio.to_thread(
                self._register_host_session_runtime_sync,
                payloads,
            )
        except Exception as exc:
            self._host_session_runtime_registration_failure_count += 1
            retry_in = self._host_session_registration_backoff_seconds()
            self._host_session_runtime_next_attempt_at = now + retry_in
            logger.warning(
                (
                    "Host-session runtime auto-registration failed for "
                    "workspace=%s surface=%s: %s (retry in %.1fs)"
                ),
                self.workspace_id,
                self.surface,
                exc,
                retry_in,
            )
            return

        runtime_id = response.get("runtime_id")
        runtime_count = int(response.get("registered_runtime_count") or 1)
        self._host_session_runtime_registered = bool(response.get("registered"))
        if self._host_session_runtime_registered:
            self._host_session_runtime_last_registered_fingerprint = fingerprint
            self._host_session_runtime_last_success_at = now
            self._host_session_runtime_next_attempt_at = (
                now + self.HOST_SESSION_REGISTER_REFRESH_INTERVAL
            )
            self._host_session_runtime_registration_failure_count = 0
        logger.info(
            "Host-session runtime registered for workspace=%s surface=%s runtime_id=%s count=%s",
            self.workspace_id,
            self.surface,
            runtime_id or "-",
            runtime_count,
        )
