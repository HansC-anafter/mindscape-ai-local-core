"""
Agent Dispatch -- completion cache and resume-state helpers.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

logger = logging.getLogger("backend.app.routes.agent_dispatch.message_handlers")


class MessageCompletionStateMixin:
    """Mixin: completed-result replay and resume sync state."""

    @staticmethod
    def _normalize_completed_entry(
        execution_id: str,
        entry: Any,
    ) -> Dict[str, Any]:
        if isinstance(entry, dict):
            normalized = dict(entry)
        else:
            normalized = {}

        normalized.setdefault("execution_id", execution_id)

        if "completed_at" not in normalized:
            if isinstance(entry, (int, float)):
                normalized["completed_at"] = float(entry)
            else:
                normalized["completed_at"] = None

        if "status" not in normalized:
            normalized["status"] = "completed"

        return normalized

    def _mark_completed_execution(
        self,
        execution_id: str,
        *,
        result: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
        landing_succeeded: Optional[bool] = None,
        error: Optional[str] = None,
    ) -> None:
        existing = self._completed.get(execution_id)
        normalized = self._normalize_completed_entry(execution_id, existing)
        normalized["status"] = (
            str(status).strip()
            if isinstance(status, str) and status.strip()
            else str(normalized.get("status") or "completed")
        )
        normalized["completed_at"] = time.time()

        if isinstance(result, dict) and result:
            normalized["result"] = result

        if landing_succeeded is not None:
            normalized["landing_succeeded"] = bool(landing_succeeded)

        if isinstance(error, str) and error.strip():
            normalized["error"] = error.strip()

        self._completed[execution_id] = normalized
        while len(self._completed) > self.COMPLETED_MAX_SIZE:
            self._completed.popitem(last=False)

    def _build_resume_sync(
        self,
        *,
        workspace_id: str,
        recent_execution_ids: list[str],
        pending_rest_execution_ids: list[str],
        last_completed_at: Optional[float],
    ) -> Dict[str, Any]:
        known_ids: set[str] = set()
        for raw_execution_id in recent_execution_ids:
            execution_id = str(raw_execution_id or "").strip()
            if execution_id:
                known_ids.add(execution_id)
        for raw_execution_id in pending_rest_execution_ids:
            execution_id = str(raw_execution_id or "").strip()
            if execution_id:
                known_ids.add(execution_id)

        replayed_completions = []
        duplicates_to_ignore = []
        seen_replayed: set[str] = set()

        for execution_id in known_ids:
            entry = self._completed.get(execution_id)
            if entry is None:
                continue
            normalized = self._normalize_completed_entry(execution_id, entry)
            replayed_completions.append(
                {
                    "execution_id": execution_id,
                    "status": normalized.get("status") or "completed",
                    "completed_at": normalized.get("completed_at"),
                    "landing_succeeded": normalized.get("landing_succeeded"),
                    "error": normalized.get("error"),
                }
            )
            duplicates_to_ignore.append(execution_id)
            seen_replayed.add(execution_id)

        if isinstance(last_completed_at, (int, float)):
            cutoff = float(last_completed_at)
            for execution_id, entry in self._completed.items():
                normalized = self._normalize_completed_entry(execution_id, entry)
                completed_at = normalized.get("completed_at")
                if not isinstance(completed_at, (int, float)):
                    continue
                if completed_at <= cutoff or execution_id in seen_replayed:
                    continue
                replayed_completions.append(
                    {
                        "execution_id": execution_id,
                        "status": normalized.get("status") or "completed",
                        "completed_at": completed_at,
                        "landing_succeeded": normalized.get("landing_succeeded"),
                        "error": normalized.get("error"),
                    }
                )
                seen_replayed.add(execution_id)

        tasks_to_requeue: list[Dict[str, Any]] = []
        seen_requeue: set[str] = set()
        for pending in self._pending_queue.get(workspace_id, []):
            execution_id = str(getattr(pending, "execution_id", "") or "").strip()
            if not execution_id or execution_id in seen_requeue:
                continue
            tasks_to_requeue.append({"execution_id": execution_id})
            seen_requeue.add(execution_id)
        for execution_id, inflight in self._inflight.items():
            if (
                getattr(inflight, "workspace_id", None) == workspace_id
                and getattr(inflight, "client_id", None) == "pending"
                and execution_id not in seen_requeue
            ):
                tasks_to_requeue.append({"execution_id": execution_id})
                seen_requeue.add(execution_id)

        return {
            "type": "resume_sync",
            "workspace_id": workspace_id,
            "replayed_completions": replayed_completions,
            "duplicates_to_ignore": duplicates_to_ignore,
            "tasks_to_requeue": tasks_to_requeue,
        }

    @staticmethod
    def _log_background_task_failure(task: asyncio.Task) -> None:
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("[AgentWS] Background result task inspection failed")
            return
        if exc is not None:
            logger.exception("[AgentWS] Background result task failed", exc_info=exc)
