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
