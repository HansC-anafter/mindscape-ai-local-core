from .base import *


class HostBridgeDispatchMixin:

    async def _handle_message(self, msg: Dict[str, Any]) -> None:
        """Route incoming messages by type."""
        msg_type = msg.get("type", "")

        if msg_type == "auth_challenge":
            await self._handle_auth_challenge(msg)
        elif msg_type == "welcome":
            logger.info(
                f"Welcome! client_id={msg.get('client_id')}, "
                f"flushed={msg.get('flushed_tasks', 0)} pending tasks"
            )
            self._schedule_pending_result_flush()
            await self._send_resume_state()
        elif msg_type == "auth_ok":
            logger.info(f"Authenticated! flushed={msg.get('flushed_tasks', 0)} tasks")
            self._schedule_pending_result_flush()
            await self._send_resume_state()
        elif msg_type == "auth_failed":
            logger.error(f"Auth failed: {msg.get('error')}")
            await self.stop()
        elif msg_type == "dispatch":
            await self._handle_dispatch(msg)
        elif msg_type == "pong":
            pass  # Heartbeat response
        elif msg_type == "result_ack":
            execution_id = msg.get("execution_id", "")
            waiter = self._result_ack_waiters.pop(execution_id, None)
            if waiter and not waiter.done():
                waiter.set_result(True)
            self._pending_rest_results.pop(execution_id, None)
            self._persist_result_spool()
            logger.debug(f"Result acknowledged: {msg.get('execution_id')}")
        elif msg_type == "resume_sync":
            self._handle_resume_sync(msg)
        elif msg_type == "error":
            error_message = str(msg.get("error") or "")
            logger.error(f"Server error: {error_message}")
            self._start_background_task(
                self._recover_unknown_execution_via_rest(error_message)
            )
        else:
            logger.warning(f"Unknown message type: {msg_type}")

    async def _handle_auth_challenge(self, msg: Dict[str, Any]) -> None:
        """Respond to HMAC auth challenge."""
        nonce = msg.get("nonce", "")

        if not self.auth_secret:
            logger.warning("Auth challenge received but no auth_secret configured")
            return

        nonce_response = hmac.new(
            self.auth_secret.encode(),
            (nonce + self.client_id).encode(),
            hashlib.sha256,
        ).hexdigest()

        await self._send(
            {
                "type": "auth_response",
                "token": self.auth_secret,  # Pre-shared token
                "nonce_response": nonce_response,
            }
        )
        logger.info("Auth response sent")

    def _build_resume_state_message(self) -> Dict[str, Any]:
        self._prune_recent_results()
        return {
            "type": "resume_state",
            "recent_execution_ids": list(self._recent_results.keys()),
            "pending_rest_execution_ids": list(self._pending_rest_results.keys()),
            # Exact execution identities are sufficient to reconcile this client's
            # durable result spool. A timestamp cannot express workspace ownership
            # and made older servers sweep their process-global completion cache.
            "last_completed_at": None,
        }

    async def _send_resume_state(self) -> None:
        await self._send(self._build_resume_state_message())

    def _handle_resume_sync(self, msg: Dict[str, Any]) -> None:
        replayed = msg.get("replayed_completions") or []
        duplicates = msg.get("duplicates_to_ignore") or []
        reconciled: set[str] = set()

        for entry in replayed:
            if not isinstance(entry, dict):
                continue
            execution_id = str(entry.get("execution_id") or "").strip()
            if execution_id:
                reconciled.add(execution_id)

        for raw_execution_id in duplicates:
            execution_id = str(raw_execution_id or "").strip()
            if execution_id:
                reconciled.add(execution_id)

        if not reconciled:
            logger.info(
                "Resume sync received: replay=%d dup=%d requeue=%d",
                len(replayed),
                len(duplicates),
                len(msg.get("tasks_to_requeue") or []),
            )
            return

        for execution_id in reconciled:
            waiter = self._result_ack_waiters.pop(execution_id, None)
            if waiter and not waiter.done():
                waiter.set_result(True)
            self._pending_rest_results.pop(execution_id, None)

        self._persist_result_spool()
        logger.info(
            "Resume sync reconciled %d execution(s); replay=%d dup=%d requeue=%d",
            len(reconciled),
            len(replayed),
            len(duplicates),
            len(msg.get("tasks_to_requeue") or []),
        )

    async def _handle_dispatch(self, msg: Dict[str, Any]) -> None:
        """
        Handle a dispatched task.

        1. Send ack
        2. Execute task via task_handler
        3. Send result
        """
        execution_id = msg.get("execution_id", "")
        task = msg.get("task", "")

        logger.info(f"Task received: exec={execution_id}, task={task[:80]}...")

        # 1. Acknowledge
        await self._send(
            {
                "type": "ack",
                "execution_id": execution_id,
            }
        )

        cached_result = self._get_recent_result(execution_id)
        if cached_result is not None:
            delivery = await self._deliver_result(execution_id, cached_result)
            logger.warning(
                "Duplicate dispatch for %s after prior completion; "
                "skipping re-execution and re-delivering cached result "
                "(delivery=%s)",
                execution_id,
                delivery,
            )
            return

        existing_task = self._dispatch_tasks.get(execution_id)
        if existing_task and not existing_task.done():
            logger.warning(
                "Duplicate dispatch for %s while a local execution is "
                "already queued or running; keeping the original run",
                execution_id,
            )
            return

        task = self._start_background_task(
            self._execute_dispatched_task(execution_id, msg)
        )
        self._dispatch_tasks[execution_id] = task
        task.add_done_callback(
            lambda _done, eid=execution_id: self._dispatch_tasks.pop(eid, None)
        )

    async def _execute_dispatched_task(
        self,
        execution_id: str,
        msg: Dict[str, Any],
    ) -> None:
        # Serialize local dispatch execution so the receive loop can keep
        # draining/acking new dispatches without running multiple CLI jobs
        # concurrently for the same host bridge client.
        async with self._get_dispatch_lock():
            await self._run_dispatch_task(execution_id, msg)

    def _get_dispatch_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        if self._dispatch_lock is None or self._dispatch_lock_loop is not loop:
            self._dispatch_lock = asyncio.Lock()
            self._dispatch_lock_loop = loop
        return self._dispatch_lock

    async def _run_dispatch_task(
        self,
        execution_id: str,
        msg: Dict[str, Any],
    ) -> None:
        self._active_tasks += 1
        start_time = time.monotonic()
        try:
            result = await self.task_handler(msg)
            duration = time.monotonic() - start_time

            # 3. Send result
            delivery = await self._deliver_result(
                execution_id,
                {
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
                    "metadata": {
                        **(
                            result.get("metadata")
                            if isinstance(result.get("metadata"), dict)
                            else {}
                        ),
                        "runtime_id": result.get("runtime_id"),
                    },
                    "governance": {
                        "output_hash": hashlib.sha256(
                            result.get("output", "").encode()
                        ).hexdigest(),
                        "summary": result.get("output", "")[:200],
                    },
                },
            )

            logger.info(
                f"Task completed: exec={execution_id}, "
                f"duration={duration:.1f}s, "
                f"status={result.get('status', 'completed')}, "
                f"delivery={delivery}"
            )

            # Auth failure = runtime is broken, disconnect so UI
            # shows unavailable instead of a false "connected".
            error_str = result.get("error", "") or ""
            if "Exit code 41" in error_str or "auth not set" in error_str.lower():
                logger.error(
                    "AUTH FAILURE detected (exit 41). "
                    "Disconnecting so status shows unavailable. "
                    "Restart with scripts/start_cli_bridge_supervisor.sh "
                    f"--surfaces {self.surface} --all to fix."
                )
                await self.stop()

        except Exception as e:
            duration = time.monotonic() - start_time
            logger.error(f"Task failed: {e}")
            await self._deliver_result(
                execution_id,
                {
                    "type": "result",
                    "execution_id": execution_id,
                    "status": "failed",
                    "output": "",
                    "duration_seconds": duration,
                    "error": str(e),
                },
            )
        finally:
            self._active_tasks = max(0, self._active_tasks - 1)

    async def _deliver_result(
        self,
        execution_id: str,
        result_message: Dict[str, Any],
    ) -> str:
        """Send result over WS and fall back to REST if the ACK never arrives."""
        self._remember_result(execution_id, result_message)
        loop = asyncio.get_running_loop()
        waiter: asyncio.Future[bool] = loop.create_future()
        self._result_ack_waiters[execution_id] = waiter

        try:
            await self._send(result_message)
        except Exception as exc:
            self._result_ack_waiters.pop(execution_id, None)
            logger.warning(
                "WS result send failed for %s: %s. Falling back to REST result submit.",
                execution_id,
                exc,
            )
            await self._submit_result_via_rest(result_message)
            return "rest_fallback_send_error"

        task = self._start_background_task(
            self._wait_for_result_ack_or_fallback(
                execution_id,
                waiter,
                result_message,
            )
        )
        return "ws_push"

    async def _wait_for_result_ack_or_fallback(
        self,
        execution_id: str,
        waiter: asyncio.Future[bool],
        result_message: Dict[str, Any],
    ) -> None:
        try:
            await asyncio.wait_for(waiter, timeout=self.RESULT_ACK_TIMEOUT)
        except asyncio.TimeoutError:
            self._result_ack_waiters.pop(execution_id, None)
            logger.warning(
                "No result_ack for %s within %.1fs. Falling back to REST result submit.",
                execution_id,
                self.RESULT_ACK_TIMEOUT,
            )
            await self._submit_result_via_rest(result_message)
        except Exception as exc:
            self._result_ack_waiters.pop(execution_id, None)
            logger.warning(
                "Result ACK wait failed for %s: %s. Falling back to REST result submit.",
                execution_id,
                exc,
            )
            await self._submit_result_via_rest(result_message)
        else:
            self._result_ack_waiters.pop(execution_id, None)

    async def _recover_pending_result_acks_due_to_stale_connection(self) -> None:
        pending_execution_ids = [
            execution_id
            for execution_id, waiter in self._result_ack_waiters.items()
            if not waiter.done()
        ]
        if not pending_execution_ids:
            return

        logger.warning(
            "Recovering %d pending result_ack(s) via REST fallback after stale connection: %s",
            len(pending_execution_ids),
            pending_execution_ids,
        )

        for execution_id in pending_execution_ids:
            waiter = self._result_ack_waiters.pop(execution_id, None)
            if waiter and not waiter.done():
                waiter.set_result(True)

            result_message = self._get_recent_result(execution_id)
            if result_message is None:
                logger.warning(
                    "Missing cached result for %s during stale-connection recovery",
                    execution_id,
                )
                continue
            await self._submit_result_via_rest(result_message)

    async def _recover_unknown_execution_via_rest(self, error_message: str) -> None:
        match = UNKNOWN_EXECUTION_ERROR_RE.search(str(error_message or ""))
        if not match:
            return
        execution_id = str(match.group(1) or "").strip()
        if not execution_id:
            return

        result_message = self._get_recent_result(execution_id)
        if result_message is None:
            return

        waiter = self._result_ack_waiters.pop(execution_id, None)
        if waiter and not waiter.done():
            waiter.set_result(True)

        logger.warning(
            "Server rejected WS result for %s as unknown execution; attempting immediate REST recovery",
            execution_id,
        )
        await self._submit_result_via_rest(result_message)
