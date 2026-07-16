from __future__ import annotations

import json

from backend.app.routes.core.workspace.tasks_core.progress_snapshot_contract import (
    PROGRESS_SNAPSHOT_MAX_BYTES,
    fresh_snapshot,
)


def test_optional_progress_detail_moves_to_pointer_under_15kb_budget() -> None:
    payload = fresh_snapshot(
        {
            "workspace_id": "ws-1",
            "execution_id": "exec-1",
            "task_status": "running",
            "progress": {"phase": "render", "frames": ["x" * 1000] * 20},
            "artifact_metadata": {"blob": "x" * 20_000},
            "content_metadata": {"blob": "x" * 20_000},
        }
    )

    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    assert len(encoded) <= PROGRESS_SNAPSHOT_MAX_BYTES
    assert payload["task_status"] == "running"
    assert payload["progress"] == {"phase": "render"}
    assert set(payload["detail_pointers"]) == {
        "artifact_metadata",
        "content_metadata",
        "progress_detail",
    }
