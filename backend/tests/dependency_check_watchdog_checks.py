import json
import time
from pathlib import Path

import pytest

from backend.app.runner.dependency_check import DependencyChecker


def _write_watchdog(path: Path, **overrides):
    now = time.time()
    payload = {
        "status": "active",
        "progress_phase": "model_ready",
        "started_at_epoch": now - 10,
        "phase_entered_at_epoch": now - 5,
        "heartbeat_at_epoch": now - 2,
        "progress_at_epoch": now - 2,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_mlx_watchdog_is_fresh_accepts_recent_active_state(tmp_path, monkeypatch):
    state_file = tmp_path / "inflight_request.json"
    _write_watchdog(state_file)
    monkeypatch.setattr(
        "backend.app.runner.dependency_check._WATCHDOG_STATE_FILE",
        state_file,
    )

    checker = DependencyChecker()
    assert checker._mlx_watchdog_is_fresh() is True


@pytest.mark.asyncio
async def test_check_mlx_uses_watchdog_fallback_on_timeout(tmp_path, monkeypatch):
    state_file = tmp_path / "inflight_request.json"
    _write_watchdog(state_file)
    monkeypatch.setattr(
        "backend.app.runner.dependency_check._WATCHDOG_STATE_FILE",
        state_file,
    )

    async def _timeout(*args, **kwargs):
        raise TimeoutError()

    monkeypatch.setattr(
        "backend.app.runner.dependency_check.asyncio.open_connection",
        _timeout,
    )

    checker = DependencyChecker()
    available, error = await checker._check_mlx()
    assert available is True
    assert error is None
