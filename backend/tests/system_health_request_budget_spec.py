from __future__ import annotations

import asyncio
from pathlib import Path

from backend.app.services.readiness_request_coordinator import (
    ReadinessRequestCoordinator,
)
from backend.app.services.system_health_resources import SystemHealthResourceMixin
from backend.app.services.vector_readiness_probe import VectorReadinessResult


def test_system_health_uses_shared_vector_probe_without_route_fallback(monkeypatch) -> None:
    from backend.app.services import vector_readiness_probe

    calls = 0

    def fake_readiness(*, force: bool = False):
        nonlocal calls
        calls += 1
        assert force is False
        return VectorReadinessResult(True, True, "0.8.0")

    monkeypatch.setattr(vector_readiness_probe, "get_vector_readiness", fake_readiness)
    issues = []

    result = asyncio.run(SystemHealthResourceMixin()._check_vector_db(issues))

    assert result["connected"] is True
    assert result["pgvector_version"] == "0.8.0"
    assert calls == 1
    assert issues == []


def test_request_coordinator_joins_force_to_existing_inflight_and_caches() -> None:
    async def scenario():
        coordinator = ReadinessRequestCoordinator()
        started = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def producer():
            nonlocal calls
            calls += 1
            started.set()
            await release.wait()
            return {"generation": calls}

        first = asyncio.create_task(
            coordinator.run(
                key=("workspace-health", "profile-1"),
                producer=producer,
                ttl_seconds=30,
            )
        )
        await started.wait()
        forced = asyncio.create_task(
            coordinator.run(
                key=("workspace-health", "profile-1"),
                producer=producer,
                ttl_seconds=30,
                force=True,
            )
        )
        release.set()
        first_result, forced_result = await asyncio.gather(first, forced)
        cached_result = await coordinator.run(
            key=("workspace-health", "profile-1"),
            producer=producer,
            ttl_seconds=30,
        )
        return calls, first_result, forced_result, cached_result

    calls, first_result, forced_result, cached_result = asyncio.run(scenario())

    assert calls == 1
    assert first_result == forced_result == cached_result == {"generation": 1}
    assert first_result is not forced_result


def test_global_readiness_is_inflight_only_without_new_ttl() -> None:
    async def scenario():
        coordinator = ReadinessRequestCoordinator()
        calls = 0

        async def producer():
            nonlocal calls
            calls += 1
            await asyncio.sleep(0)
            return calls

        first, joined = await asyncio.gather(
            coordinator.run(key="global", producer=producer),
            coordinator.run(key="global", producer=producer),
        )
        later = await coordinator.run(key="global", producer=producer)
        return calls, first, joined, later

    calls, first, joined, later = asyncio.run(scenario())

    assert (first, joined, later) == (1, 1, 2)
    assert calls == 2


def test_health_route_seams_use_profile_coalescing_and_preserve_liveness() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    workspace_health = (
        backend_root / "app/routes/core/workspace/health.py"
    ).read_text(encoding="utf-8")
    main = (backend_root / "app/main.py").read_text(encoding="utf-8")
    resources = (
        backend_root / "app/services/system_health_resources.py"
    ).read_text(encoding="utf-8")

    assert 'key=("workspace-health", profile_id)' in workspace_health
    assert "workspace_id" not in workspace_health.split("key=", 1)[1].split(",", 1)[0]
    assert 'key=("global-health", "default-user")' in main
    healthz_body = main.split('async def healthz():', 1)[1].split(
        "# Connect modular bootstrap components", 1
    )[0]
    assert "SystemHealthChecker" not in healthz_body
    assert "vector_readiness" not in healthz_body
    assert "backend.app.routes.vector_db" not in resources
    assert "psycopg2" not in resources
