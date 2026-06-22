from .base import *
from backend.app.services.external_agents.bridge.polling_budget_metadata import (
    attach_polling_budget_metadata,
)


class HostBridgePollingMixin:

    async def _run_polling_transport(self) -> None:
        logger.info(
            "Starting REST polling fallback for workspace=%s surface=%s",
            self.workspace_id,
            self.surface,
        )
        self._ws_forbidden_count = 0
        consecutive_poll_failures = 0

        while self._running and self._transport_mode == "polling":
            try:
                tasks = await asyncio.to_thread(self._reserve_pending_tasks_via_rest_sync)
                consecutive_poll_failures = 0
            except Exception as exc:
                consecutive_poll_failures += 1
                delay = self._polling_reserve_failure_delay(consecutive_poll_failures)
                logger.warning(
                    "Polling reserve failed for workspace=%s surface=%s: %s "
                    "(retrying in %.1fs)",
                    self.workspace_id,
                    self.surface,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)
                continue

            if not tasks:
                continue

            for task in tasks:
                if not self._running or self._transport_mode != "polling":
                    return
                await self._handle_polled_dispatch(task)

    def _reserve_pending_tasks_via_rest_sync(self) -> List[Dict[str, Any]]:
        if not self.backend_api_urls:
            raise RuntimeError("MINDSCAPE_BACKEND_API_URL is not configured")

        query = urllib.parse.urlencode(
            {
                "workspace_id": self.workspace_id,
                "client_id": self.client_id,
                "surface": self.surface,
                "limit": 1,
                "lease_seconds": self.POLLING_LEASE_SECONDS,
                "wait_seconds": self.POLLING_WAIT_SECONDS,
            }
        )
        _backend_url, body = self._backend_request_sync(
            lambda backend_url: urllib.request.Request(
                f"{backend_url}/api/v1/mcp/agent/pending?{query}",
                headers={"Accept": "application/json"},
                method="GET",
            ),
            timeout=self.POLLING_WAIT_SECONDS + 10.0,
        )
        payload = json.loads(body) if body else {}
        tasks = payload.get("tasks")
        return tasks if isinstance(tasks, list) else []

    def _ack_reserved_task_via_rest_sync(self, execution_id: str, lease_id: str) -> Dict[str, Any]:
        if not self.backend_api_urls:
            raise RuntimeError("MINDSCAPE_BACKEND_API_URL is not configured")

        payload = {
            "execution_id": execution_id,
            "lease_id": lease_id,
            "client_id": self.client_id,
        }
        _backend_url, body = self._backend_request_sync(
            lambda backend_url: urllib.request.Request(
                f"{backend_url}/api/v1/mcp/agent/ack",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            ),
            timeout=30,
        )
        return json.loads(body) if body else {}

    def _report_progress_via_rest_sync(
        self,
        execution_id: str,
        lease_id: str,
        *,
        progress_pct: Optional[float] = None,
        message: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not self.backend_api_urls:
            raise RuntimeError("MINDSCAPE_BACKEND_API_URL is not configured")

        payload = {
            "execution_id": execution_id,
            "lease_id": lease_id,
            "client_id": self.client_id,
            "progress_pct": progress_pct,
            "message": message,
        }
        _backend_url, body = self._backend_request_sync(
            lambda backend_url: urllib.request.Request(
                f"{backend_url}/api/v1/mcp/agent/progress",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            ),
            timeout=30,
        )
        return json.loads(body) if body else {}

    async def _polling_heartbeat_loop(
        self,
        execution_id: str,
        lease_id: str,
        stop_event: asyncio.Event,
    ) -> None:
        while self._running and not stop_event.is_set():
            try:
                await asyncio.to_thread(
                    self._report_progress_via_rest_sync,
                    execution_id,
                    lease_id,
                    progress_pct=None,
                    message="heartbeat",
                )
            except Exception as exc:
                logger.warning(
                    "Polling heartbeat failed for %s: %s",
                    execution_id,
                    exc,
                )
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=self.POLLING_HEARTBEAT_INTERVAL,
                )
            except asyncio.TimeoutError:
                continue

    async def _handle_polled_dispatch(self, msg: Dict[str, Any]) -> None:
        execution_id = str(msg.get("execution_id") or "").strip()
        lease_id = str(msg.get("lease_id") or "").strip()
        task = msg.get("task", "")
        if not execution_id or not lease_id:
            logger.warning("Ignoring malformed polled task: %s", msg)
            return

        logger.info(
            "Polled task received: exec=%s, task=%s...",
            execution_id,
            str(task)[:80],
        )

        await asyncio.to_thread(
            self._ack_reserved_task_via_rest_sync,
            execution_id,
            lease_id,
        )

        cached_result = self._get_recent_result(execution_id)
        if cached_result is not None:
            cached_result["lease_id"] = lease_id
            cached_result["client_id"] = self.client_id
            cached_result["metadata"] = attach_polling_budget_metadata(
                {
                    **(
                        cached_result.get("metadata")
                        if isinstance(cached_result.get("metadata"), dict)
                        else {}
                    ),
                    "transport": "polling",
                    "client_id": self.client_id,
                    "surface_type": self.surface,
                },
                reason="cached_result_redelivery",
                client=self,
            )
            await self._submit_result_via_rest(cached_result)
            logger.warning(
                "Duplicate polled task for %s; re-delivered cached result via REST",
                execution_id,
            )
            return

        self._active_tasks += 1
        start_time = time.monotonic()
        heartbeat_stop = asyncio.Event()
        heartbeat_task = self._start_background_task(
            self._polling_heartbeat_loop(execution_id, lease_id, heartbeat_stop)
        )
        try:
            result = await self.task_handler(msg)
            duration = time.monotonic() - start_time
            result_message = {
                "type": "result",
                "execution_id": execution_id,
                "status": result.get("status", "completed"),
                "output": result.get("output", ""),
                "duration_seconds": duration,
                "tool_calls": result.get("tool_calls", []),
                "attachments": result.get("attachments", []),
                "files_modified": result.get("files_modified", []),
                "files_created": result.get("files_created", []),
                "error": result.get("error"),
                "lease_id": lease_id,
                "client_id": self.client_id,
                "metadata": attach_polling_budget_metadata(
                    {
                        **(
                            result.get("metadata")
                            if isinstance(result.get("metadata"), dict)
                            else {}
                        ),
                        "transport": "polling",
                        "runtime_id": result.get("runtime_id"),
                        "client_id": self.client_id,
                        "surface_type": self.surface,
                    },
                    reason="task_result",
                    client=self,
                ),
                "governance": {
                    "output_hash": hashlib.sha256(
                        result.get("output", "").encode()
                    ).hexdigest(),
                    "summary": result.get("output", "")[:200],
                },
            }
            self._remember_result(execution_id, result_message)
            await self._submit_result_via_rest(result_message)
            logger.info(
                "Polled task completed: exec=%s duration=%.1fs status=%s",
                execution_id,
                duration,
                result.get("status", "completed"),
            )
        except Exception as exc:
            duration = time.monotonic() - start_time
            logger.error("Polled task failed for %s: %s", execution_id, exc)
            result_message = {
                "type": "result",
                "execution_id": execution_id,
                "status": "failed",
                "output": "",
                "duration_seconds": duration,
                "error": str(exc),
                "lease_id": lease_id,
                "client_id": self.client_id,
                "metadata": attach_polling_budget_metadata(
                    {
                        "transport": "polling",
                        "client_id": self.client_id,
                        "surface_type": self.surface,
                    },
                    reason="task_failed",
                    client=self,
                ),
            }
            self._remember_result(execution_id, result_message)
            await self._submit_result_via_rest(result_message)
        finally:
            heartbeat_stop.set()
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
            self._active_tasks = max(0, self._active_tasks - 1)

    # ============================================================
    #  Message handling
    # ============================================================
