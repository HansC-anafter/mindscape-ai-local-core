"""PgBouncer pressure sampling for runner database admission control."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from app.database.config import get_pgbouncer_admin_url

logger = logging.getLogger(__name__)

PRESSURE_CACHE_KEY = "mindscape:runtime_db_pressure:v1"
PRESSURE_SAMPLE_LOCK_KEY = "mindscape:runtime_db_pressure:sample_lock"
WATCHED_DATABASES = frozenset({"mindscape_core", "mindscape_vectors"})


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def pressure_enabled() -> bool:
    return os.getenv("LOCAL_CORE_DB_PRESSURE_ENABLED", "true").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def pressure_sample_interval_seconds() -> int:
    return max(1, _env_int("LOCAL_CORE_DB_PRESSURE_SAMPLE_INTERVAL_SECONDS", 5))


def pressure_stale_seconds() -> int:
    return max(1, _env_int("LOCAL_CORE_DB_PRESSURE_STALE_SECONDS", 10))


def pressure_stale_grace_seconds() -> int:
    return max(1, _env_int("LOCAL_CORE_DB_PRESSURE_STALE_GRACE_SECONDS", 5))


def pressure_cache_ttl_seconds() -> int:
    return pressure_stale_seconds() + pressure_stale_grace_seconds()


def pressure_wait_seconds() -> int:
    return max(1, _env_int("LOCAL_CORE_DB_PRESSURE_WAIT_SECONDS", 2))


def pressure_query_timeout_seconds() -> int:
    return max(1, _env_int("LOCAL_CORE_DB_PRESSURE_QUERY_TIMEOUT_SECONDS", 1))


def heartbeat_min_interval_seconds() -> int:
    return max(
        1,
        _env_int("LOCAL_CORE_DB_PRESSURE_HEARTBEAT_MIN_INTERVAL_SECONDS", 30),
    )


@dataclass(frozen=True)
class DbPoolPressureDecision:
    state: str
    reason: str
    wait_seconds: int = field(default_factory=pressure_wait_seconds)
    checked_at_epoch: float = field(default_factory=time.time)
    pools: list[dict[str, Any]] = field(default_factory=list)
    database_state: str = "write_ready"

    @property
    def paused(self) -> bool:
        return self.state == "paused"

    def to_cache_payload(self) -> str:
        return json.dumps(asdict(self), sort_keys=True)

    @classmethod
    def open(
        cls,
        *,
        reason: str = "pgbouncer_pressure_open",
        checked_at_epoch: float | None = None,
        pools: list[dict[str, Any]] | None = None,
        database_state: str = "write_ready",
    ) -> "DbPoolPressureDecision":
        return cls(
            state="open",
            reason=reason,
            wait_seconds=0,
            checked_at_epoch=time.time() if checked_at_epoch is None else checked_at_epoch,
            pools=pools or [],
            database_state=database_state,
        )

    @classmethod
    def paused_for(
        cls,
        reason: str,
        *,
        checked_at_epoch: float | None = None,
        pools: list[dict[str, Any]] | None = None,
        database_state: str = "unknown",
    ) -> "DbPoolPressureDecision":
        return cls(
            state="paused",
            reason=reason,
            wait_seconds=pressure_wait_seconds(),
            checked_at_epoch=time.time() if checked_at_epoch is None else checked_at_epoch,
            pools=pools or [],
            database_state=database_state,
        )


def _row_to_dict(row: Any) -> dict[str, Any]:
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    if isinstance(row, dict):
        return dict(row)
    return dict(row or {})


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        return 0


def classify_pgbouncer_pools(
    rows: Iterable[Any],
    *,
    watched_databases: set[str] | frozenset[str] = WATCHED_DATABASES,
    checked_at_epoch: float | None = None,
    database_state: str = "write_ready",
) -> DbPoolPressureDecision:
    pools: list[dict[str, Any]] = []
    for row in rows:
        pool = _row_to_dict(row)
        database = str(pool.get("database") or "").strip()
        if database not in watched_databases:
            continue
        normalized = {
            "database": database,
            "user": str(pool.get("user") or "").strip(),
            "cl_waiting": _int_value(pool.get("cl_waiting")),
            "cl_active": _int_value(pool.get("cl_active")),
            "sv_active": _int_value(pool.get("sv_active")),
            "sv_idle": _int_value(pool.get("sv_idle")),
            "sv_used": _int_value(pool.get("sv_used")),
            "sv_login": _int_value(pool.get("sv_login")),
            "maxwait": _int_value(pool.get("maxwait")),
            "maxwait_us": _int_value(pool.get("maxwait_us")),
            "pool_mode": str(pool.get("pool_mode") or "").strip(),
        }
        pools.append(normalized)

    if any(pool["cl_waiting"] > 0 for pool in pools):
        return DbPoolPressureDecision.paused_for(
            "pgbouncer_client_waiting",
            checked_at_epoch=checked_at_epoch,
            pools=pools,
            database_state=database_state,
        )
    if any(pool["maxwait"] > 0 or pool["maxwait_us"] > 0 for pool in pools):
        return DbPoolPressureDecision.paused_for(
            "pgbouncer_client_maxwait",
            checked_at_epoch=checked_at_epoch,
            pools=pools,
            database_state=database_state,
        )
    if any(pool["sv_login"] > 0 for pool in pools):
        return DbPoolPressureDecision.paused_for(
            "pgbouncer_server_login_in_progress",
            checked_at_epoch=checked_at_epoch,
            pools=pools,
            database_state=database_state,
        )
    if any(
        pool["cl_active"] > 0
        and (
            pool["sv_active"]
            + pool["sv_idle"]
            + pool["sv_used"]
            + pool["sv_login"]
        )
        == 0
        for pool in pools
    ):
        return DbPoolPressureDecision.paused_for(
            "pgbouncer_no_server_connection",
            checked_at_epoch=checked_at_epoch,
            pools=pools,
            database_state=database_state,
        )
    if database_state != "write_ready":
        return DbPoolPressureDecision.paused_for(
            database_state,
            checked_at_epoch=checked_at_epoch,
            pools=pools,
            database_state=database_state,
        )
    return DbPoolPressureDecision.open(
        checked_at_epoch=checked_at_epoch,
        pools=pools,
        database_state=database_state,
    )


def sample_pgbouncer_pressure() -> DbPoolPressureDecision:
    """Query PgBouncer admin console once and classify the pool state."""

    if not pressure_enabled():
        return DbPoolPressureDecision.open(reason="pgbouncer_pressure_disabled")

    admin_url = get_pgbouncer_admin_url(required=False)
    if not admin_url:
        return DbPoolPressureDecision.open(reason="pgbouncer_pressure_unconfigured")

    timeout_seconds = pressure_query_timeout_seconds()
    conn = None
    try:
        import psycopg2

        conn = psycopg2.connect(admin_url, connect_timeout=timeout_seconds)
        conn.autocommit = True
        cursor = conn.cursor()
        try:
            cursor.execute("SHOW POOLS")
            columns = [column[0] for column in cursor.description or []]
            rows = [
                dict(zip(columns, row, strict=False))
                for row in cursor.fetchall()
            ]
        finally:
            cursor.close()
        from backend.app.database.write_readiness import check_core_write_readiness

        readiness = check_core_write_readiness(
            operation="runner_pgbouncer_pressure_probe"
        )
        database_state = "write_ready" if readiness.ready else readiness.reason
        return classify_pgbouncer_pools(
            rows,
            checked_at_epoch=time.time(),
            database_state=database_state,
        )
    except Exception as exc:
        logger.warning("PgBouncer pressure probe failed: %s", exc)
        return DbPoolPressureDecision.paused_for("pgbouncer_pressure_probe_failed")
    finally:
        if conn is not None:
            conn.close()


def _decode_cached_decision(
    raw_value: Any,
    *,
    max_age_seconds: int | None = None,
) -> DbPoolPressureDecision | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, bytes):
        raw_value = raw_value.decode("utf-8", errors="ignore")
    try:
        payload = json.loads(str(raw_value))
        checked_at = float(payload.get("checked_at_epoch") or 0.0)
        max_age = pressure_stale_seconds() if max_age_seconds is None else max_age_seconds
        if time.time() - checked_at > max_age:
            return None
        return DbPoolPressureDecision(
            state=str(payload.get("state") or "paused"),
            reason=str(payload.get("reason") or "pgbouncer_pressure_cache_invalid"),
            wait_seconds=_int_value(payload.get("wait_seconds")) or pressure_wait_seconds(),
            checked_at_epoch=checked_at,
            pools=list(payload.get("pools") or []),
            database_state=str(payload.get("database_state") or "unknown"),
        )
    except Exception:
        return None


def _refresh_in_progress_decision(
    decision: DbPoolPressureDecision,
) -> DbPoolPressureDecision:
    reason = f"{decision.reason}_refresh_in_progress"
    if decision.paused:
        return DbPoolPressureDecision.paused_for(
            reason,
            checked_at_epoch=decision.checked_at_epoch,
            pools=decision.pools,
            database_state=decision.database_state,
        )
    return DbPoolPressureDecision.open(
        reason=reason,
        checked_at_epoch=decision.checked_at_epoch,
        pools=decision.pools,
        database_state=decision.database_state,
    )


async def check_db_pool_pressure(
    redis_queue: Any,
    *,
    owner_id: str,
    sampler=sample_pgbouncer_pressure,
) -> DbPoolPressureDecision:
    """Return the shared PgBouncer pressure decision for this runner loop."""

    if not pressure_enabled():
        return DbPoolPressureDecision.open(reason="pgbouncer_pressure_disabled")

    try:
        client = await redis_queue._get_client()
    except Exception:
        client = None
    if not client:
        return DbPoolPressureDecision.paused_for("pgbouncer_pressure_cache_unavailable")

    raw_cached = await client.get(PRESSURE_CACHE_KEY)
    cached = _decode_cached_decision(raw_cached)
    if cached is not None:
        return cached

    lock_token = f"{owner_id}:{time.time()}"
    lock_acquired = await client.set(
        PRESSURE_SAMPLE_LOCK_KEY,
        lock_token,
        nx=True,
        ex=pressure_sample_interval_seconds(),
    )
    if not lock_acquired:
        stale_cached = _decode_cached_decision(
            raw_cached,
            max_age_seconds=pressure_cache_ttl_seconds(),
        )
        if stale_cached is not None:
            return _refresh_in_progress_decision(stale_cached)
        return DbPoolPressureDecision.paused_for("pgbouncer_pressure_cache_miss")

    decision = await asyncio.to_thread(sampler)
    await client.setex(
        PRESSURE_CACHE_KEY,
        pressure_cache_ttl_seconds(),
        decision.to_cache_payload(),
    )
    return decision


def should_write_postgres_heartbeat(
    decision: DbPoolPressureDecision,
    *,
    now_epoch: float,
    last_write_epoch: float,
) -> bool:
    """Throttle optional Postgres heartbeat while PgBouncer is pressured."""

    if not decision.paused:
        return True
    return (now_epoch - last_write_epoch) >= heartbeat_min_interval_seconds()
