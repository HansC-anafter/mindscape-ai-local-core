from pathlib import Path


def test_progress_snapshot_route_offloads_blocking_loader():
    source = Path("backend/app/routes/core/workspace/tasks.py").read_text()

    assert "def _load_execution_progress_snapshot_payload(" in source
    assert "run_ui_read(" in source
    assert "_load_execution_progress_snapshot_payload," in source
