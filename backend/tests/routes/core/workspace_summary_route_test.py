from datetime import datetime, timezone
import importlib

from fastapi import FastAPI
from fastapi.testclient import TestClient


class FakeWorkspaceStore:
    def __init__(self):
        self.calls = []
        self.db_path = ":memory:"

    def list_workspace_summaries(self, owner_user_id, primary_project_id=None, limit=50):
        self.calls.append(
            {
                "owner_user_id": owner_user_id,
                "primary_project_id": primary_project_id,
                "limit": limit,
            }
        )
        now = datetime(2026, 5, 8, tzinfo=timezone.utc)
        return [
            {
                "id": "ws-1",
                "owner_user_id": owner_user_id,
                "title": "Workspace 1",
                "description": "Summary only",
                "workspace_type": "personal",
                "primary_project_id": primary_project_id,
                "execution_mode": "hybrid",
                "meeting_enabled": False,
                "expected_artifacts": [],
                "execution_priority": "medium",
                "project_assignment_mode": "auto_silent",
                "launch_status": "active",
                "visibility": "private",
                "created_at": now,
                "updated_at": now,
                "data_sources": {"heavy": "must not leak into summary response"},
                "metadata": {"heavy": "must not leak into summary response"},
            }
        ]


def test_workspace_summary_uses_lightweight_store_and_omits_heavy_fields(monkeypatch):
    fake_store = FakeWorkspaceStore()
    import backend.app.services.mindscape_store as mindscape_store

    monkeypatch.setattr(mindscape_store, "MindscapeStore", lambda: fake_store)
    crud = importlib.import_module("backend.app.routes.core.workspace.crud")
    monkeypatch.setattr(crud, "store", fake_store)

    app = FastAPI()
    app.include_router(crud.router, prefix="/api/v1/workspaces")
    client = TestClient(app)

    response = client.get(
        "/api/v1/workspaces/summary?owner_user_id=default-user&primary_project_id=project-1&limit=1"
    )

    assert response.status_code == 200
    assert fake_store.calls == [
        {
            "owner_user_id": "default-user",
            "primary_project_id": "project-1",
            "limit": 1,
        }
    ]
    body = response.json()
    assert body[0]["id"] == "ws-1"
    assert body[0]["title"] == "Workspace 1"
    assert "data_sources" not in body[0]
    assert "metadata" not in body[0]
