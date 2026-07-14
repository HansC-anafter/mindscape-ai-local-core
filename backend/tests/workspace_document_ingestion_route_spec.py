from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.app.routes.core.workspace import files as files_route


class FakeStore:
    async def get_workspace(self, _workspace_id):
        return SimpleNamespace(owner_user_id="user-1")


class FakeUpload:
    filename = "oversized.pdf"
    content_type = "application/pdf"

    def __init__(self):
        self.read_called = False

    async def read(self):
        self.read_called = True
        return b""


@pytest.mark.asyncio
async def test_declared_oversized_document_is_rejected_before_body_read(monkeypatch):
    monkeypatch.setattr(files_route, "store", FakeStore())
    upload = FakeUpload()

    with pytest.raises(HTTPException) as exc_info:
        await files_route.upload_file(
            workspace_id="workspace-1",
            file=upload,
            file_name="oversized.pdf",
            file_type="application/pdf",
            file_size=files_route.MAX_DOCUMENT_UPLOAD_BYTES + 1,
        )

    assert exc_info.value.status_code == 413
    assert upload.read_called is False


@pytest.mark.asyncio
async def test_analyze_response_adds_document_summary_without_removing_legacy_keys(
    monkeypatch,
):
    monkeypatch.setattr(files_route, "store", FakeStore())
    monkeypatch.setattr(files_route, "PostgresTimelineItemsStore", lambda: object())
    monkeypatch.setattr(files_route, "TasksStore", lambda: object())

    class FakeService:
        def __init__(self, *_args):
            pass

        async def analyze_file(self, **_kwargs):
            return {
                "file_id": "file-1",
                "file_path": "/tmp/file-1.pdf",
                "event_id": "event-1",
                "collaboration_results": {"semantic_seeds": {}},
                "document_ingestion": {
                    "state": "ready",
                    "document_id": "file-1",
                },
            }

    monkeypatch.setattr(files_route, "FileAnalysisService", FakeService)

    result = await files_route.analyze_file(
        workspace_id="workspace-1",
        request={"file_id": "file-1", "file_name": "sample.pdf"},
    )

    assert result["file_id"] == "file-1"
    assert result["saved_file_path"] == "/tmp/file-1.pdf"
    assert result["collaboration_results"] == {"semantic_seeds": {}}
    assert result["document_ingestion"]["state"] == "ready"
