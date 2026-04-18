import pytest

from backend.app.runner import dependency_check as dep_mod
from backend.app.runner.dependency_check import DependencyChecker


@pytest.mark.asyncio
async def test_cloud_policy_skips_local_mlx_dependency(monkeypatch):
    checker = DependencyChecker()
    monkeypatch.setattr(
        checker,
        "_resolve_reference_runtime_scope",
        lambda workspace_id, execution_context=None: "cloud",
    )

    async def _should_not_run():
        raise AssertionError("local mlx probe should be skipped in cloud mode")

    monkeypatch.setattr(checker, "_check_mlx", _should_not_run)

    unmet = await checker.check_playbook_deps(
        "ig_analyze_pinned_reference",
        execution_context={
            "workspace_id": "ws-cloud",
            "inputs": {"workspace_id": "ws-cloud"},
        },
    )

    assert unmet == []


@pytest.mark.asyncio
async def test_local_policy_keeps_local_mlx_dependency(monkeypatch):
    checker = DependencyChecker()
    monkeypatch.setattr(
        checker,
        "_resolve_reference_runtime_scope",
        lambda workspace_id, execution_context=None: "local",
    )

    async def _mlx_unavailable():
        return False, "mlx unavailable"

    monkeypatch.setattr(checker, "_check_mlx", _mlx_unavailable)

    unmet = await checker.check_playbook_deps(
        "ig_analyze_pinned_reference",
        execution_context={
            "workspace_id": "ws-local",
            "inputs": {"workspace_id": "ws-local"},
        },
    )

    assert unmet == ["mlx"]


@pytest.mark.asyncio
async def test_check_mlx_requires_http_200(monkeypatch):
    checker = DependencyChecker(cache_ttl=0)

    class _FakeReader:
        async def readline(self):
            return b"HTTP/1.1 503 Service Unavailable\r\n"

    class _FakeWriter:
        def write(self, _data):
            return None

        async def drain(self):
            return None

        def close(self):
            return None

        async def wait_closed(self):
            return None

    async def _fake_open_connection(_host, _port):
        return _FakeReader(), _FakeWriter()

    monkeypatch.setattr(dep_mod.asyncio, "open_connection", _fake_open_connection)

    available, error = await checker._check_mlx()

    assert available is False
    assert "503" in str(error)


@pytest.mark.asyncio
async def test_check_mlx_timeout_accepts_fresh_watchdog(monkeypatch):
    checker = DependencyChecker(cache_ttl=0)

    async def _fake_open_connection(_host, _port):
        raise TimeoutError

    monkeypatch.setattr(dep_mod.asyncio, "open_connection", _fake_open_connection)
    monkeypatch.setattr(checker, "_mlx_watchdog_is_fresh", lambda: True)

    available, error = await checker._check_mlx()

    assert available is True
    assert error is None
