import asyncio
import sys
import types
import json
import time

import pytest

from backend.app.runner import dependency_check
from backend.app.runner.dependency_check import DependencyChecker


@pytest.mark.asyncio
async def test_dependency_checker_uses_declared_runner_dependencies(monkeypatch):
    checker = DependencyChecker()

    async def fake_check(dep: str) -> bool:
        return dep != "mlx"

    monkeypatch.setattr(checker, "_check_dep", fake_check)

    unmet = await checker.check_playbook_deps(
        "vision_analysis",
        execution_context={"runner_dependencies": ["mlx"]},
    )

    assert unmet == ["mlx"]


@pytest.mark.asyncio
async def test_dependency_checker_uses_declared_capability_resolver(monkeypatch):
    module = types.ModuleType("capabilities.example.deps")

    def resolve_dependencies(**kwargs):
        assert kwargs["dependencies"] == ["mlx"]
        assert kwargs["playbook_code"] == "vision_analysis"
        return []

    module.resolve_dependencies = resolve_dependencies
    monkeypatch.setitem(sys.modules, "capabilities.example.deps", module)
    checker = DependencyChecker()

    async def fake_check(dep: str) -> bool:
        return dep != "mlx"

    monkeypatch.setattr(checker, "_check_dep", fake_check)

    unmet = await checker.check_playbook_deps(
        "vision_analysis",
        execution_context={
            "runner_dependencies": ["mlx"],
            "dependency_resolver": {
                "backend": "capabilities.example.deps:resolve_dependencies",
            },
        },
    )

    assert unmet == []


def test_mlx_watchdog_accepts_current_vlm_state_schema(monkeypatch, tmp_path):
    state_file = tmp_path / "inflight_request.json"
    now = time.time()
    state_file.write_text(
        json.dumps(
            {
                "status": "active",
                "phase": "generating",
                "started_at": now - 300,
                "heartbeat_at": now - 5,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dependency_check, "_WATCHDOG_STATE_FILE", state_file)

    assert DependencyChecker(cache_ttl=0)._mlx_watchdog_is_fresh() is True


def test_mlx_watchdog_prefers_lane_specific_runner_state_file(monkeypatch, tmp_path):
    state_file = tmp_path / "runner_decision_synthesis_35b.json"
    now = time.time()
    state_file.write_text(
        json.dumps(
            {
                "status": "active",
                "phase": "generating",
                "started_at": now - 120,
                "heartbeat_at": now - 3,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dependency_check, "_WATCHDOG_STATE_DIR", tmp_path)
    monkeypatch.setenv("LOCAL_CORE_HOST_RESOURCE_LANE_ID", "runner:decision_synthesis_35b")
    monkeypatch.setenv("VLM_WATCHDOG_STATE_FILE", str(state_file))

    assert DependencyChecker(cache_ttl=0)._mlx_watchdog_is_fresh() is True


def test_mlx_watchdog_rejects_stale_current_vlm_state(monkeypatch, tmp_path):
    state_file = tmp_path / "inflight_request.json"
    now = time.time()
    state_file.write_text(
        json.dumps(
            {
                "status": "active",
                "phase": "generating",
                "started_at": now - 800,
                "heartbeat_at": now - 500,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(dependency_check, "_WATCHDOG_STATE_FILE", state_file)
    monkeypatch.setattr(dependency_check, "_WATCHDOG_HARD_TIMEOUT_SECONDS", 720)
    monkeypatch.setattr(dependency_check, "_WATCHDOG_HEARTBEAT_TTL_SECONDS", 45)

    assert DependencyChecker(cache_ttl=0)._mlx_watchdog_is_fresh() is False


def test_resolve_mlx_probe_target_prefers_runtime_endpoint(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_RUNTIME_ENDPOINT", "http://host.docker.internal:8212")
    monkeypatch.setenv("MLX_BASE_URL", "http://host.docker.internal:8210")
    monkeypatch.setenv("MLX_PORT", "8210")
    monkeypatch.setenv("MLX_HOST_FROM_RUNNER", "legacy-host")

    assert dependency_check._resolve_mlx_probe_target() == (
        "host.docker.internal",
        8212,
    )


def test_resolve_mlx_probe_target_falls_back_to_legacy_host_and_port(monkeypatch):
    monkeypatch.delenv("LOCAL_CORE_RUNTIME_ENDPOINT", raising=False)
    monkeypatch.delenv("MLX_BASE_URL", raising=False)
    monkeypatch.setenv("MLX_PORT", "8210")
    monkeypatch.setenv("MLX_HOST_FROM_RUNNER", "legacy-host")

    assert dependency_check._resolve_mlx_probe_target() == ("legacy-host", 8210)


@pytest.mark.asyncio
async def test_mlx_dependency_probe_uses_health_endpoint(monkeypatch):
    captured: dict[str, bytes] = {}

    class FakeReader:
        async def readline(self) -> bytes:
            return b"HTTP/1.1 200 OK\r\n"

    class FakeWriter:
        def write(self, request: bytes) -> None:
            captured["request"] = request

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            return None

        async def wait_closed(self) -> None:
            return None

    async def fake_open_connection(host: str, port: int):
        assert host == "runtime-host"
        assert port == 8212
        return FakeReader(), FakeWriter()

    monkeypatch.setenv("LOCAL_CORE_RUNTIME_ENDPOINT", "http://runtime-host:8212")
    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)

    available, error = await DependencyChecker(cache_ttl=0)._check_mlx()

    assert available is True
    assert error is None
    assert captured["request"].startswith(b"GET /health HTTP/1.1")
    assert b"/v1/models" not in captured["request"]
