from backend.app.runner import worker_loop


def test_runner_startup_reconcile_enabled_by_default(monkeypatch):
    monkeypatch.delenv("LOCAL_CORE_RUNNER_STARTUP_RECONCILE_ENABLED", raising=False)

    assert worker_loop._runner_startup_reconcile_enabled() is True


def test_runner_startup_reconcile_can_be_disabled(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_RUNNER_STARTUP_RECONCILE_ENABLED", "false")

    assert worker_loop._runner_startup_reconcile_enabled() is False
