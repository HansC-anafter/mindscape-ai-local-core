from .base import *


class HostBridgeTransportMixin:

    @property
    def ws_url(self) -> str:
        """Build WebSocket URL."""
        return (
            f"ws://{self.host}/ws/agent/{self.workspace_id}"
            f"?client_id={self.client_id}&surface={self.surface}"
        )

    def _preflight_check(self) -> None:
        """Validate runtime env before connecting.

        For gemini_cli, verify the provider-specific bridge command exists.
        For all surfaces, ensure some auth path or backend token endpoint
        is available so the process never registers as "connected" in the
        backend with an unusable runtime.
        """
        runtime_cmd = ""
        if self.surface == "gemini_cli":
            runtime_cmd = os.environ.get("GEMINI_CLI_RUNTIME_CMD", "").strip()
            if not runtime_cmd:
                raise RuntimeError(
                    "GEMINI_CLI_RUNTIME_CMD is not set. "
                    "Start this client via "
                    "scripts/start_cli_bridge_supervisor.sh "
                    "--surfaces gemini_cli --all, which sets the required "
                    "Gemini bridge command."
                )

            import shlex as _shlex
            import os as _os

            # posix=False on Windows: preserve backslashes in paths
            argv = _shlex.split(runtime_cmd, posix=(_os.name != 'nt'))
            # Must have at least 2 tokens: interpreter + script path
            if len(argv) < 2:
                raise RuntimeError(
                    f"GEMINI_CLI_RUNTIME_CMD is incomplete ('{runtime_cmd}'). "
                    "Expected format: "
                    "'python3 /path/to/gemini_cli_runtime_bridge.py'."
                )

        has_backend = bool(os.environ.get("MINDSCAPE_BACKEND_API_URL", "").strip())
        auth_mode = "backend_api" if has_backend else ""
        if self.surface == "codex_cli":
            if os.environ.get("OPENAI_API_KEY", "").strip():
                auth_mode = "api_key"
        elif self.surface == "claude_code_cli":
            if os.environ.get("ANTHROPIC_API_KEY", "").strip():
                auth_mode = "api_key"
        else:
            if os.environ.get("GEMINI_API_KEY", "").strip():
                auth_mode = "api_key"
            elif (
                os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").strip().lower()
                == "true"
            ):
                auth_mode = "vertex_ai"
            elif (
                os.environ.get("GOOGLE_GENAI_USE_GCA", "").strip().lower() == "true"
            ):
                auth_mode = "gca"

        if not auth_mode:
            raise RuntimeError(
                f"No auth configured for surface '{self.surface}'. "
                "Provide the provider-specific API key or configure "
                "MINDSCAPE_BACKEND_API_URL so the backend can issue CLI auth."
            )

        logger.info(
            "Preflight OK: surface=%s runtime_cmd=%r auth_mode=%s",
            self.surface,
            runtime_cmd or None,
            auth_mode,
        )

    def _start_background_task(
        self,
        coro: Coroutine[Any, Any, Any],
    ) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def run(self) -> None:
        """Main entry point -- connect with auto-reconnect."""
        self._preflight_check()
        self._running = True
        runtime_identity = _runtime_identity()
        logger.info(
            (
                "Starting host bridge WS client "
                "(workspace=%s surface=%s pid=%s ppid=%s pgid=%s xpc_service=%s)"
            ),
            self.workspace_id,
            self.surface,
            runtime_identity.get("pid"),
            runtime_identity.get("ppid"),
            runtime_identity.get("pgid"),
            runtime_identity.get("xpc_service_name") or "-",
        )

        if self._should_auto_register_host_session_runtime():
            self._start_background_task(
                self._ensure_host_session_runtime_registered_loop()
            )

        while self._running:
            try:
                if self._transport_mode == "polling":
                    await self._run_polling_transport()
                    continue
                await self._connect_and_listen()
                self._ws_forbidden_count = 0
                if not self._running:
                    break
                delay = self._clean_reconnect_delay()
                logger.info(
                    "WebSocket session ended cleanly for workspace=%s surface=%s; "
                    "reconnecting in %.1fs (active_tasks=%s pending_result_acks=%s)",
                    self.workspace_id,
                    self.surface,
                    delay,
                    self._active_tasks,
                    self._pending_result_ack_count(),
                )
                await asyncio.sleep(delay)
            except Exception as e:
                if not self._running:
                    break
                if self._should_fallback_to_polling(e):
                    self._transport_mode = "polling"
                    self._reconnect_attempt = 0
                    logger.warning(
                        "WebSocket transport rejected for workspace=%s surface=%s; "
                        "switching to REST polling fallback after %d consecutive 403s",
                        self.workspace_id,
                        self.surface,
                        self._ws_forbidden_count,
                    )
                    continue
                delay = self._backoff_delay()
                logger.warning(
                    f"Connection lost: {e}. "
                    f"Reconnecting in {delay:.1f}s "
                    f"(attempt {self._reconnect_attempt})..."
                )
                await asyncio.sleep(delay)

    async def stop(self) -> None:
        """Graceful shutdown."""
        self._running = False
        if self._ws:
            await self._ws.close()
        pending_background = list(self._background_tasks)
        for task in pending_background:
            task.cancel()
        if pending_background:
            await asyncio.gather(*pending_background, return_exceptions=True)
        logger.info("Host bridge WS client stopped")

    async def _ensure_host_session_runtime_registered_loop(self) -> None:
        while self._running:
            await self._maybe_register_host_session_runtime()
            if not self._running:
                return
            await asyncio.sleep(self.HOST_SESSION_REGISTER_RETRY_INTERVAL)

    # ============================================================
    #  Connection
    # ============================================================

    async def _connect_and_listen(self) -> None:
        """Single connection lifecycle."""
        logger.info(f"Connecting to {self.ws_url}")

        # Use protocol-level ping/pong as a safety net for dead TCP.
        # If backend restarts and TCP silently dies, the protocol
        # ping will timeout → ConnectionClosed → reconnect.
        async with websockets.connect(
            self.ws_url,
            open_timeout=self.WS_OPEN_TIMEOUT,
            ping_interval=20,
            ping_timeout=120,  # long timeout to survive task execution
        ) as ws:
            self._ws = ws
            self._reconnect_attempt = 0
            pong_received = asyncio.Event()
            self._pong_received = pong_received
            logger.info("Connected!")

            # Start heartbeat task
            heartbeat = asyncio.create_task(self._heartbeat_loop(pong_received))

            try:
                async for raw_msg in ws:
                    try:
                        msg = json.loads(raw_msg)
                        # Handle server pong for app-level liveness
                        if msg.get("type") == "pong":
                            pong_received.set()
                            continue
                        await self._handle_message(msg)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid JSON: {raw_msg[:100]}")
            finally:
                heartbeat.cancel()
                self._pong_received = None
                self._ws = None

    async def _heartbeat_loop(
        self,
        pong_received: Optional[asyncio.Event] = None,
    ) -> None:
        """Send periodic pings and verify server responds.

        After backend restart, TCP may stay alive but the server-side
        WS state is gone. We send an app-level ping and wait for a
        pong response within PONG_TIMEOUT. If no pong arrives, we
        force-close the WebSocket to trigger reconnect.

        IMPORTANT: During active task execution, we skip the pong-or-die
        check because the server may be busy and slow to respond.
        """
        pong_event = pong_received or self._pong_received or asyncio.Event()
        while True:
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)
            if not self._ws:
                break
            try:
                pong_event.clear()
                await self._ws.send(json.dumps({"type": "ping"}))
                # Wait for server pong within timeout
                try:
                    await asyncio.wait_for(
                        pong_event.wait(),
                        timeout=self.PONG_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    pending_result_acks = self._pending_result_ack_count()
                    if self._has_pending_transport_work():
                        if self._active_tasks == 0 and pending_result_acks > 0:
                            logger.warning(
                                "Pong timeout while awaiting %s result_ack(s) "
                                "with no active task — forcing REST recovery and reconnect",
                                pending_result_acks,
                            )
                            await self._recover_pending_result_acks_due_to_stale_connection()
                            await self._ws.close()
                            break
                        logger.info(
                            "Pong timeout but transport work is still pending "
                            "(active_tasks=%s pending_result_acks=%s) — "
                            "keeping connection alive",
                            self._active_tasks,
                            pending_result_acks,
                        )
                        continue
                    logger.info(
                        "Application pong lagged beyond %.1fs for workspace=%s "
                        "surface=%s; keeping the idle socket and relying on "
                        "WebSocket protocol liveness",
                        self.PONG_TIMEOUT,
                        self.workspace_id,
                        self.surface,
                    )
                    continue
            except Exception:
                logger.warning(
                    "Heartbeat loop failed for workspace=%s surface=%s; forcing reconnect",
                    self.workspace_id,
                    self.surface,
                    exc_info=True,
                )
                try:
                    await self._ws.close()
                except Exception:
                    pass
                break

    def _backoff_delay(self) -> float:
        """Exponential backoff with per-client fleet spreading."""
        import random

        self._reconnect_attempt += 1
        delay = min(
            self.RECONNECT_BASE_DELAY * (2 ** (self._reconnect_attempt - 1)),
            self.RECONNECT_MAX_DELAY,
        )
        spread = (
            self.CLEAN_BUSY_RECONNECT_SPREAD
            if self._has_pending_transport_work()
            else self.CLEAN_IDLE_RECONNECT_SPREAD
        )
        return (
            delay
            + random.uniform(0, delay * 0.1)
            + self._stable_client_offset(spread)
        )

    def _clean_reconnect_delay(self) -> float:
        """Jittered reconnect delay after a graceful WebSocket close."""
        base_delay = (
            self.CLEAN_BUSY_RECONNECT_DELAY
            if self._has_pending_transport_work()
            else self.CLEAN_IDLE_RECONNECT_DELAY
        )
        spread = (
            self.CLEAN_BUSY_RECONNECT_SPREAD
            if self._has_pending_transport_work()
            else self.CLEAN_IDLE_RECONNECT_SPREAD
        )
        return base_delay + self._stable_client_offset(spread)

    def _stable_client_offset(self, spread_window: float) -> float:
        if spread_window <= 0:
            return 0.0
        digest = hashlib.sha1(self.client_id.encode("utf-8")).hexdigest()
        fraction = int(digest[:8], 16) / 0xFFFFFFFF
        return round(fraction * spread_window, 3)

    def _supports_polling_fallback(self) -> bool:
        return self.surface == "codex_cli" and _env_flag(
            "MINDSCAPE_HOST_BRIDGE_POLLING_FALLBACK",
            True,
        )

    @staticmethod
    def _websocket_status_code(exc: BaseException) -> Optional[int]:
        status = getattr(exc, "status_code", None)
        if isinstance(status, int):
            return status
        response = getattr(exc, "response", None)
        response_status = getattr(response, "status_code", None)
        if isinstance(response_status, int):
            return response_status
        return None

    def _should_fallback_to_polling(self, exc: BaseException) -> bool:
        if not self._supports_polling_fallback():
            return False

        status_code = self._websocket_status_code(exc)
        transport_denied = (
            status_code == 403
            or "HTTP 403" in str(exc)
        )
        if not transport_denied:
            self._ws_forbidden_count = 0
            return False

        self._ws_forbidden_count += 1
        return self._ws_forbidden_count >= self.WS_FORBIDDEN_POLLING_THRESHOLD

    def _polling_reserve_failure_delay(self, consecutive_failures: int) -> float:
        if consecutive_failures <= 0:
            return 0.0
        exponent = max(0, consecutive_failures - 1)
        return min(
            self.RECONNECT_BASE_DELAY * (2 ** exponent),
            self.POLLING_RESERVE_MAX_DELAY,
        )
