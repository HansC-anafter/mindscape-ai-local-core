import pytest
import time

from backend.app.runner import db_pool_pressure


class _FakeRedis:
    def __init__(self):
        self.values = {}
        self.sample_locks = 0

    async def get(self, key):
        return self.values.get(key)

    async def set(self, key, value, *, nx=False, ex=None):
        if nx and key in self.values:
            return False
        self.values[key] = value
        if key == db_pool_pressure.PRESSURE_SAMPLE_LOCK_KEY:
            self.sample_locks += 1
        return True

    async def setex(self, key, _ttl, value):
        self.values[key] = value
        return True


class _FakeQueue:
    def __init__(self, client):
        self.client = client

    async def _get_client(self):
        return self.client


def test_classify_pgbouncer_waiting_clients_as_paused():
    decision = db_pool_pressure.classify_pgbouncer_pools(
        [
            {
                "database": "mindscape_core",
                "cl_waiting": 1,
                "cl_active": 30,
                "sv_active": 30,
                "sv_idle": 0,
                "pool_mode": "transaction",
            }
        ],
        checked_at_epoch=100.0,
    )

    assert decision.paused is True
    assert decision.reason == "pgbouncer_client_waiting"


def test_classify_open_when_no_clients_waiting():
    decision = db_pool_pressure.classify_pgbouncer_pools(
        [{"database": "mindscape_core", "cl_waiting": 0}],
        checked_at_epoch=100.0,
    )

    assert decision.paused is False
    assert decision.reason == "pgbouncer_pressure_open"


@pytest.mark.parametrize(
    ("pool", "reason"),
    [
        (
            {"database": "mindscape_core", "cl_waiting": 0, "maxwait": 1},
            "pgbouncer_client_maxwait",
        ),
        (
            {"database": "mindscape_core", "cl_waiting": 0, "sv_login": 1},
            "pgbouncer_server_login_in_progress",
        ),
        (
            {
                "database": "mindscape_core",
                "cl_waiting": 0,
                "cl_active": 1,
                "sv_active": 0,
                "sv_idle": 0,
                "sv_used": 0,
                "sv_login": 0,
            },
            "pgbouncer_no_server_connection",
        ),
    ],
)
def test_composite_pool_state_pauses_without_changing_capacity(pool, reason):
    decision = db_pool_pressure.classify_pgbouncer_pools([pool])

    assert decision.paused is True
    assert decision.reason == reason


def test_database_recovery_pauses_even_when_pgbouncer_has_no_waiters():
    decision = db_pool_pressure.classify_pgbouncer_pools(
        [{"database": "mindscape_core", "cl_waiting": 0}],
        database_state="postgres_startup_recovery",
    )

    assert decision.paused is True
    assert decision.reason == "postgres_startup_recovery"


@pytest.mark.asyncio
async def test_redis_cache_prevents_duplicate_sampling(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_DB_PRESSURE_ENABLED", "true")
    client = _FakeRedis()
    queue = _FakeQueue(client)
    calls = {"count": 0}

    def sampler():
        calls["count"] += 1
        return db_pool_pressure.DbPoolPressureDecision.open()

    first = await db_pool_pressure.check_db_pool_pressure(
        queue,
        owner_id="runner-a",
        sampler=sampler,
    )
    second = await db_pool_pressure.check_db_pool_pressure(
        queue,
        owner_id="runner-b",
        sampler=sampler,
    )

    assert first.paused is False
    assert second.paused is False
    assert calls["count"] == 1
    assert client.sample_locks == 1


@pytest.mark.asyncio
async def test_stale_open_cache_is_used_while_refresh_is_in_progress(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_DB_PRESSURE_ENABLED", "true")
    monkeypatch.setenv("LOCAL_CORE_DB_PRESSURE_STALE_SECONDS", "1")
    monkeypatch.setenv("LOCAL_CORE_DB_PRESSURE_STALE_GRACE_SECONDS", "10")
    client = _FakeRedis()
    queue = _FakeQueue(client)
    client.values[db_pool_pressure.PRESSURE_CACHE_KEY] = (
        db_pool_pressure.DbPoolPressureDecision.open(
            checked_at_epoch=time.time() - 2,
        ).to_cache_payload()
    )
    client.values[db_pool_pressure.PRESSURE_SAMPLE_LOCK_KEY] = "runner-a"

    decision = await db_pool_pressure.check_db_pool_pressure(
        queue,
        owner_id="runner-b",
    )

    assert decision.paused is False
    assert decision.reason == "pgbouncer_pressure_open_refresh_in_progress"


@pytest.mark.asyncio
async def test_stale_paused_cache_stays_paused_while_refresh_is_in_progress(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_DB_PRESSURE_ENABLED", "true")
    monkeypatch.setenv("LOCAL_CORE_DB_PRESSURE_STALE_SECONDS", "1")
    monkeypatch.setenv("LOCAL_CORE_DB_PRESSURE_STALE_GRACE_SECONDS", "10")
    client = _FakeRedis()
    queue = _FakeQueue(client)
    client.values[db_pool_pressure.PRESSURE_CACHE_KEY] = (
        db_pool_pressure.DbPoolPressureDecision.paused_for(
            "pgbouncer_client_waiting",
            checked_at_epoch=time.time() - 2,
        ).to_cache_payload()
    )
    client.values[db_pool_pressure.PRESSURE_SAMPLE_LOCK_KEY] = "runner-a"

    decision = await db_pool_pressure.check_db_pool_pressure(
        queue,
        owner_id="runner-b",
    )

    assert decision.paused is True
    assert decision.reason == "pgbouncer_client_waiting_refresh_in_progress"
