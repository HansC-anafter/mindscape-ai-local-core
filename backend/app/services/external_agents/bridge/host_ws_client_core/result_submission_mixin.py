from .base import *


class HostBridgeResultSubmissionMixin:

    def _submit_result_via_rest_sync(self, result_message: Dict[str, Any]) -> Dict[str, Any]:
        if not self.backend_api_urls:
            raise RuntimeError("MINDSCAPE_BACKEND_API_URL is not configured")

        payload = {
            "execution_id": result_message.get("execution_id", ""),
            "status": result_message.get("status", "completed"),
            "output": result_message.get("output", ""),
            "duration_seconds": result_message.get("duration_seconds", 0),
            "tool_calls": result_message.get("tool_calls", []),
            "attachments": result_message.get("attachments", []),
            "files_modified": result_message.get("files_modified", []),
            "files_created": result_message.get("files_created", []),
            "error": result_message.get("error"),
            "governance": result_message.get("governance", {}),
            "metadata": {
                **(result_message.get("metadata") or {}),
                "transport": (
                    (result_message.get("metadata") or {}).get("transport")
                    or "rest_fallback"
                ),
                "client_id": self.client_id,
                "surface_type": self.surface,
            },
            "client_id": self.client_id,
            "lease_id": result_message.get("lease_id"),
        }
        _backend_url, body = self._backend_request_sync(
            lambda backend_url: urllib.request.Request(
                f"{backend_url}/api/v1/mcp/agent/result",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                method="POST",
            ),
            timeout=10,
        )
        return json.loads(body) if body else {}

    async def _submit_result_via_rest(
        self,
        result_message: Dict[str, Any],
        *,
        queue_on_failure: bool = True,
    ) -> bool:
        execution_id = result_message.get("execution_id", "")
        max_attempts = max(1, int(self.RESULT_REST_RETRY_ATTEMPTS))
        base_delay = max(0.1, float(self.RESULT_REST_RETRY_BASE_DELAY))

        for attempt in range(1, max_attempts + 1):
            try:
                response = await asyncio.to_thread(
                    self._submit_result_via_rest_sync,
                    result_message,
                )
                logger.info(
                    "REST result fallback accepted for %s: %s",
                    execution_id,
                    response.get("message", "accepted"),
                )
                self._pending_rest_results.pop(execution_id, None)
                self._persist_result_spool()
                return True
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    logger.info(
                        "REST result fallback for %s returned 404; "
                        "backend likely already accepted or resolved the execution.",
                        execution_id,
                    )
                    self._pending_rest_results.pop(execution_id, None)
                    self._persist_result_spool()
                    return True
                if exc.code >= 500 and attempt < max_attempts:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "REST result fallback for %s failed with HTTP %s "
                        "(attempt %d/%d); retrying in %.1fs",
                        execution_id,
                        exc.code,
                        attempt,
                        max_attempts,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.error(
                    "REST result fallback failed for %s: HTTP %s",
                    execution_id,
                    exc.code,
                )
                break
            except (urllib.error.URLError, OSError, json.JSONDecodeError, RuntimeError) as exc:
                if attempt < max_attempts:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "REST result fallback transient failure for %s "
                        "(attempt %d/%d): %s. Retrying in %.1fs",
                        execution_id,
                        attempt,
                        max_attempts,
                        exc,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                logger.error(
                    "REST result fallback failed for %s after %d attempts: %s",
                    execution_id,
                    max_attempts,
                    exc,
                )
                break

        if queue_on_failure:
            self._remember_pending_rest_result(execution_id, result_message)
            logger.warning(
                "Queued result %s for retry after reconnect; pending=%d",
                execution_id,
                len(self._pending_rest_results),
            )
        return False

    def _remember_pending_rest_result(
        self,
        execution_id: str,
        result_message: Dict[str, Any],
    ) -> None:
        self._pending_rest_results[execution_id] = copy.deepcopy(result_message)
        self._pending_rest_results.move_to_end(execution_id)
        while len(self._pending_rest_results) > self.RECENT_RESULT_MAX_SIZE:
            self._pending_rest_results.popitem(last=False)
        self._persist_result_spool()

    def _schedule_pending_result_flush(self) -> None:
        if not self._pending_rest_results:
            return
        task = self._pending_rest_flush_task
        if task and not task.done():
            return
        task = self._start_background_task(self._flush_pending_results())
        self._pending_rest_flush_task = task
        task.add_done_callback(lambda _: setattr(self, "_pending_rest_flush_task", None))

    async def _flush_pending_results(self) -> None:
        if not self._pending_rest_results:
            return
        pending_items = list(self._pending_rest_results.items())
        logger.info("Flushing %d pending result(s) after reconnect", len(pending_items))
        for execution_id, result_message in pending_items:
            delivered = await self._submit_result_via_rest(
                result_message,
                queue_on_failure=False,
            )
            if delivered:
                self._pending_rest_results.pop(execution_id, None)

    def _prune_recent_results(self) -> None:
        now = time.monotonic()
        changed = False
        while self._recent_results:
            execution_id, (stored_at, _stored_at_wall, _result) = next(
                iter(self._recent_results.items())
            )
            if (
                len(self._recent_results) > self.RECENT_RESULT_MAX_SIZE
                or now - stored_at > self.RECENT_RESULT_TTL
            ):
                self._recent_results.pop(execution_id, None)
                changed = True
                continue
            break
        if changed:
            self._persist_result_spool()

    def _remember_result(
        self,
        execution_id: str,
        result_message: Dict[str, Any],
    ) -> None:
        self._recent_results[execution_id] = (
            time.monotonic(),
            time.time(),
            copy.deepcopy(result_message),
        )
        self._recent_results.move_to_end(execution_id)
        self._prune_recent_results()
        self._persist_result_spool()

    def _get_recent_result(self, execution_id: str) -> Optional[Dict[str, Any]]:
        self._prune_recent_results()
        cached = self._recent_results.get(execution_id)
        if not cached:
            return None
        _stored_at, _stored_at_wall, result_message = cached
        self._recent_results.move_to_end(execution_id)
        return copy.deepcopy(result_message)

    # ============================================================
    #  Send helpers
    # ============================================================
