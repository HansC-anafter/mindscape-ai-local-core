import pytest


@pytest.fixture(autouse=True)
def stub_incremental_backup_runtime_admission(monkeypatch, request):
    incremental = getattr(request.module, "incremental", None)
    if incremental is None or not hasattr(incremental, "inspect_backup_runtime_admission"):
        return
    monkeypatch.setattr(
        incremental,
        "inspect_backup_runtime_admission",
        lambda **_kwargs: {
            "schema_version": "backup_runtime_admission.v3",
            "admitted": True,
            "active_meeting_sessions": 0,
            "active_postgres_base_backups": 0,
            "active_runner_tasks": 0,
            "active_runner_heartbeats": 0,
            "active_runner_inflight": 0,
            "active_runner_capacity": 0,
            "active_live_media_receivers": [],
            "receiver_state_root": "/runtime/live-media-receivers",
            "blocking_reasons": [],
            "inspection_errors": [],
        },
    )
