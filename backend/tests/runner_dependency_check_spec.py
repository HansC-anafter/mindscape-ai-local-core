import sys
import types

import pytest

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
