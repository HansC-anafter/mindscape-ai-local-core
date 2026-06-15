"""TasksStore runner heartbeat table and read-model methods."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text


class TasksStoreRunnerHeartbeatMixin:
    """Runner heartbeat persistence and listing operations."""

    def ensure_runner_heartbeats_table(self) -> None:
        """Create runner_heartbeats table if it does not exist."""
        from app.database.config import get_postgres_url_core_session
        from app.database.engine_factory import create_session_semantics_engine

        engine = create_session_semantics_engine(
            get_postgres_url_core_session(),
            "local-core-runner-heartbeat-schema",
        )
        try:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        CREATE TABLE IF NOT EXISTS runner_heartbeats (
                            runner_id TEXT PRIMARY KEY,
                            profile_code TEXT,
                            hostname TEXT,
                            inflight INTEGER NOT NULL DEFAULT 0,
                            heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                        )
                        """
                    )
                )
                for statement in (
                    "ALTER TABLE runner_heartbeats ADD COLUMN IF NOT EXISTS profile_code TEXT",
                    "ALTER TABLE runner_heartbeats ADD COLUMN IF NOT EXISTS hostname TEXT",
                    "ALTER TABLE runner_heartbeats ADD COLUMN IF NOT EXISTS inflight INTEGER NOT NULL DEFAULT 0",
                    "ALTER TABLE runner_heartbeats ADD COLUMN IF NOT EXISTS resource_snapshot JSONB",
                ):
                    try:
                        conn.execute(text(statement))
                    except Exception:
                        pass
        finally:
            engine.dispose()

    def _upsert_runner_heartbeat_legacy(self, runner_id: str) -> None:
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO runner_heartbeats (runner_id, heartbeat_at)
                    VALUES (:runner_id, NOW())
                    ON CONFLICT (runner_id)
                    DO UPDATE SET heartbeat_at = NOW()
                    """
                ),
                {"runner_id": runner_id},
            )

    def upsert_runner_heartbeat(
        self,
        runner_id: str,
        *,
        profile_code: str | None = None,
        hostname: str | None = None,
        inflight: int = 0,
        resource_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record that a runner is alive (called every poll cycle)."""
        resource_snapshot_payload = (
            json.dumps(resource_snapshot, separators=(",", ":"))
            if isinstance(resource_snapshot, dict)
            else None
        )
        try:
            with self.transaction() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO runner_heartbeats (
                            runner_id,
                            profile_code,
                            hostname,
                            inflight,
                            resource_snapshot,
                            heartbeat_at
                        )
                        VALUES (
                            :runner_id,
                            :profile_code,
                            :hostname,
                            :inflight,
                            CAST(:resource_snapshot AS JSONB),
                            NOW()
                        )
                        ON CONFLICT (runner_id)
                        DO UPDATE SET
                            profile_code = EXCLUDED.profile_code,
                            hostname = EXCLUDED.hostname,
                            inflight = EXCLUDED.inflight,
                            resource_snapshot = EXCLUDED.resource_snapshot,
                            heartbeat_at = NOW()
                        """
                    ),
                    {
                        "runner_id": runner_id,
                        "profile_code": profile_code,
                        "hostname": hostname,
                        "inflight": max(0, int(inflight or 0)),
                        "resource_snapshot": resource_snapshot_payload,
                    },
                )
        except Exception:
            # Table might not exist yet; create it and retry.
            try:
                self.ensure_runner_heartbeats_table()
                try:
                    with self.transaction() as conn:
                        conn.execute(
                            text(
                                """
                                INSERT INTO runner_heartbeats (
                                    runner_id,
                                    profile_code,
                                    hostname,
                                    inflight,
                                    resource_snapshot,
                                    heartbeat_at
                                )
                                VALUES (
                                    :runner_id,
                                    :profile_code,
                                    :hostname,
                                    :inflight,
                                    CAST(:resource_snapshot AS JSONB),
                                    NOW()
                                )
                                ON CONFLICT (runner_id)
                                DO UPDATE SET
                                    profile_code = EXCLUDED.profile_code,
                                    hostname = EXCLUDED.hostname,
                                    inflight = EXCLUDED.inflight,
                                    resource_snapshot = EXCLUDED.resource_snapshot,
                                    heartbeat_at = NOW()
                                """
                            ),
                            {
                                "runner_id": runner_id,
                                "profile_code": profile_code,
                                "hostname": hostname,
                                "inflight": max(0, int(inflight or 0)),
                                "resource_snapshot": resource_snapshot_payload,
                            },
                        )
                except Exception:
                    self._upsert_runner_heartbeat_legacy(runner_id)
            except Exception:
                try:
                    self._upsert_runner_heartbeat_legacy(runner_id)
                except Exception:
                    pass

    def has_active_runner(self, max_age_seconds: float = 120.0) -> bool:
        """Check if any runner has sent a heartbeat within max_age_seconds."""
        return bool(
            self.list_runner_heartbeats(
                max_age_seconds=max_age_seconds,
                limit=1,
            )
        )

    def _list_runner_resource_heartbeats_from_redis(
        self,
        *,
        max_age_seconds: Optional[float],
        limit: int,
    ) -> List[Dict[str, Any]]:
        try:
            from backend.app.services.cache.redis_cache import get_cache_service

            cache = get_cache_service()
            ensure_connected = getattr(cache, "_ensure_connected", None)
            if callable(ensure_connected) and not ensure_connected():
                return []
            client = getattr(cache, "_client", None)
            if client is None:
                return []
            now_epoch = datetime.now(timezone.utc).timestamp()
            max_age = (
                float(max_age_seconds)
                if isinstance(max_age_seconds, (int, float)) and max_age_seconds > 0
                else None
            )
            heartbeats: List[Dict[str, Any]] = []
            for key in client.scan_iter(
                match="mindscape:runner_resources:heartbeat:v1:*",
                count=max(100, int(limit or 50)),
            ):
                raw = client.get(key)
                if raw is None:
                    continue
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="ignore")
                try:
                    payload = json.loads(str(raw))
                except Exception:
                    continue
                if not isinstance(payload, dict):
                    continue
                captured_at = payload.get("captured_at_epoch")
                if not isinstance(captured_at, (int, float)):
                    continue
                if max_age is not None and now_epoch - float(captured_at) > max_age:
                    continue
                capacity = (
                    payload.get("capacity")
                    if isinstance(payload.get("capacity"), dict)
                    else {}
                )
                heartbeat_at = datetime.fromtimestamp(float(captured_at), timezone.utc)
                heartbeats.append(
                    {
                        "runner_id": str(payload.get("runner_id") or ""),
                        "profile_code": payload.get("profile_code"),
                        "hostname": None,
                        "inflight": int(capacity.get("inflight") or 0),
                        "resource_snapshot": payload.get("resource_snapshot")
                        if isinstance(payload.get("resource_snapshot"), dict)
                        else {},
                        "heartbeat_at": heartbeat_at.isoformat(),
                    }
                )
            heartbeats.sort(
                key=lambda row: str(row.get("heartbeat_at") or ""),
                reverse=True,
            )
            return heartbeats[:limit]
        except Exception:
            return []

    def list_runner_heartbeats(
        self,
        *,
        max_age_seconds: Optional[float] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Return recent runner heartbeats with profile metadata when available."""
        limit = max(1, int(limit or 50))
        redis_heartbeats = self._list_runner_resource_heartbeats_from_redis(
            max_age_seconds=max_age_seconds,
            limit=limit,
        )
        if redis_heartbeats:
            return redis_heartbeats

        query_parts = [
            """
            SELECT runner_id, profile_code, hostname, inflight, resource_snapshot, heartbeat_at
            FROM runner_heartbeats
            """
        ]
        params: Dict[str, Any] = {"limit": limit}
        if isinstance(max_age_seconds, (int, float)) and max_age_seconds > 0:
            query_parts.append(
                "WHERE heartbeat_at > NOW() - INTERVAL '1 second' * :max_age"
            )
            params["max_age"] = float(max_age_seconds)
        query_parts.append("ORDER BY heartbeat_at DESC")
        query_parts.append("LIMIT :limit")

        try:
            with self.get_connection() as conn:
                rows = conn.execute(text(" ".join(query_parts)), params).fetchall()
        except Exception:
            try:
                fallback_query = [
                    "SELECT runner_id, heartbeat_at FROM runner_heartbeats"
                ]
                fallback_params: Dict[str, Any] = {"limit": limit}
                if isinstance(max_age_seconds, (int, float)) and max_age_seconds > 0:
                    fallback_query.append(
                        "WHERE heartbeat_at > NOW() - INTERVAL '1 second' * :max_age"
                    )
                    fallback_params["max_age"] = float(max_age_seconds)
                fallback_query.append("ORDER BY heartbeat_at DESC")
                fallback_query.append("LIMIT :limit")
                with self.get_connection() as conn:
                    rows = conn.execute(
                        text(" ".join(fallback_query)),
                        fallback_params,
                    ).fetchall()
            except Exception:
                return []

        heartbeats: List[Dict[str, Any]] = []
        for row in rows:
            mapping = getattr(row, "_mapping", None)
            runner_id = mapping["runner_id"] if mapping is not None else row[0]
            heartbeat_at = (
                mapping["heartbeat_at"]
                if mapping is not None and "heartbeat_at" in mapping
                else row[-1]
            )
            profile_code = (
                mapping["profile_code"]
                if mapping is not None and "profile_code" in mapping
                else None
            )
            hostname = (
                mapping["hostname"]
                if mapping is not None and "hostname" in mapping
                else None
            )
            inflight = (
                mapping["inflight"]
                if mapping is not None and "inflight" in mapping
                else 0
            )
            resource_snapshot = (
                mapping["resource_snapshot"]
                if mapping is not None and "resource_snapshot" in mapping
                else None
            )
            if isinstance(resource_snapshot, str):
                try:
                    resource_snapshot = json.loads(resource_snapshot)
                except Exception:
                    resource_snapshot = None
            heartbeats.append(
                {
                    "runner_id": runner_id,
                    "profile_code": profile_code,
                    "hostname": hostname,
                    "inflight": int(inflight or 0),
                    "resource_snapshot": resource_snapshot,
                    "heartbeat_at": (
                        heartbeat_at.isoformat()
                        if hasattr(heartbeat_at, "isoformat")
                        else str(heartbeat_at)
                    ),
                }
            )
        return heartbeats
