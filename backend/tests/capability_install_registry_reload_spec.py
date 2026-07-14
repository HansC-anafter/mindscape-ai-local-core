from pathlib import Path
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / "backend"
for candidate in (PROJECT_ROOT, BACKEND_ROOT):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from app.services import capability_registry
from app.routes.core.capability_install_core.pipeline_registry_reload import (
    reload_capability_registry_modules,
)


@pytest.mark.asyncio
async def test_install_registry_reload_targets_only_installed_capability(
    monkeypatch,
) -> None:
    observed = []

    def fake_reload(capability_code: str) -> bool:
        observed.append(capability_code)
        return True

    async def fake_run(func, *args, **kwargs):
        return func(*args, **kwargs)

    monkeypatch.setattr(capability_registry, "reload_capability", fake_reload)

    await reload_capability_registry_modules(
        capability_code="motion_runtime",
        run_in_threadpool_func=fake_run,
    )

    assert observed == ["motion_runtime"]
