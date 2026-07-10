import pytest

from backend.app.runner import worker


def test_worker_main_enters_managed_loop_without_preloop_reaper(monkeypatch):
    calls = []

    monkeypatch.setattr(
        worker,
        "_initialize_capability_packages_for_runner",
        lambda: calls.append("initialize"),
    )

    async def _run_forever():
        calls.append("run_forever")

    monkeypatch.setattr(worker, "run_forever", _run_forever)
    monkeypatch.setattr(
        worker,
        "_reap_stale_running_tasks",
        lambda *args, **kwargs: pytest.fail("pre-loop reaper must not run"),
    )

    worker.main()

    assert calls == ["initialize", "run_forever"]
