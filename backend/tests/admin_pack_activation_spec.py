from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.routes.core import admin_pack_activation


@pytest.mark.asyncio
async def test_runtime_activation_runs_outside_api_event_loop(monkeypatch) -> None:
    calls = []

    def fake_activate(**kwargs):
        calls.append(kwargs)
        return {"state": "activated"}

    async def fake_to_thread(func, *args, **kwargs):
        calls.append({"thread_bridge": True})
        return func(*args, **kwargs)

    monkeypatch.setattr(
        admin_pack_activation,
        "activate_installed_capability_routes",
        fake_activate,
    )
    monkeypatch.setattr(admin_pack_activation.asyncio, "to_thread", fake_to_thread)

    result = await admin_pack_activation.activate_capability_runtime(
        SimpleNamespace(app="test-app"),
        admin_pack_activation.CapabilityRuntimeActivationRequest(
            capability_code="yogacoach",
            install_id="install-1",
            reason="install_job_completed",
        ),
    )

    assert calls[0] == {"thread_bridge": True}
    assert calls[1]["app"] == "test-app"
    assert calls[1]["capability_code"] == "yogacoach"
    assert result["state"] == "activated"
    assert result["install_id"] == "install-1"
