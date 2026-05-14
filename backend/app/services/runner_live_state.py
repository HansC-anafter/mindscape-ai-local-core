"""Redis-backed live state for runner heartbeats and inflight tasks."""

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.services.cache.redis_cache import get_cache_service


DEFAULT_RUNNER_LIVE_TTL_SECONDS = 180


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", str(value or "").strip()) or "unknown"


class RunnerLiveStateStore:
    """Store ephemeral runner task heartbeat state in Redis TTL keys."""

    def __init__(self, cache_service: Optional[Any] = None):
        self._cache = cache_service

    @staticmethod
    def task_key(task_id: str) -> str:
        return f"mindscape:runner_live:task:{_key_part(task_id)}"

    @staticmethod
    def runner_task_key(runner_id: str, task_id: str) -> str:
        return (
            f"mindscape:runner_live:runner:{_key_part(runner_id)}:"
            f"task:{_key_part(task_id)}"
        )

    def renew_task_heartbeat(
        self,
        *,
        task_id: str,
        runner_id: str,
        workspace_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        playbook_code: Optional[str] = None,
        queue_shard: Optional[str] = None,
        ttl_seconds: int = DEFAULT_RUNNER_LIVE_TTL_SECONDS,
    ) -> bool:
        payload = {
            "task_id": str(task_id),
            "runner_id": str(runner_id),
            "workspace_id": workspace_id,
            "execution_id": execution_id,
            "playbook_code": playbook_code,
            "queue_shard": queue_shard,
            "heartbeat_at": _utc_now_iso(),
            "ttl_seconds": int(ttl_seconds),
        }
        return self._set_live_payload(
            task_id=task_id,
            runner_id=runner_id,
            payload=payload,
            ttl_seconds=ttl_seconds,
        )

    def clear_task_heartbeat(self, *, task_id: str, runner_id: str) -> bool:
        cache = self._cache_service()
        deleted_task = cache.delete(self.task_key(task_id))
        deleted_runner_task = cache.delete(self.runner_task_key(runner_id, task_id))
        return bool(deleted_task or deleted_runner_task)

    def get_task_heartbeat(self, task_id: str) -> Optional[Dict[str, Any]]:
        cache = self._cache_service()
        raw = cache.get(self.task_key(task_id))
        if not raw:
            return None
        try:
            value = json.loads(raw)
        except (TypeError, ValueError):
            return None
        return value if isinstance(value, dict) else None

    def _set_live_payload(
        self,
        *,
        task_id: str,
        runner_id: str,
        payload: Dict[str, Any],
        ttl_seconds: int,
    ) -> bool:
        cache = self._cache_service()
        ttl = max(30, int(ttl_seconds or DEFAULT_RUNNER_LIVE_TTL_SECONDS))
        task_ok = cache.set_json(self.task_key(task_id), payload, ttl=ttl)
        runner_task_ok = cache.set_json(
            self.runner_task_key(runner_id, task_id),
            payload,
            ttl=ttl,
        )
        return bool(task_ok and runner_task_ok)

    def _cache_service(self):
        if self._cache is None:
            self._cache = get_cache_service()
        return self._cache
