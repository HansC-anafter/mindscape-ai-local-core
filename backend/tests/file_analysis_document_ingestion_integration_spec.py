import hashlib

import pytest

from backend.app.services.file_analysis_service import FileAnalysisService
from backend.app.services.file_analysis_service_core.document_ingestion_facade import (
    DocumentIngestionHostResult,
)


class FakeStore:
    def __init__(self):
        self.events = []

    def create_event(self, event, generate_embedding):
        self.events.append((event, generate_embedding))


class FakeDocumentFacade:
    def __init__(self, order):
        self.order = order
        self.calls = []

    async def compile_and_index(self, **kwargs):
        self.order.append("document")
        self.calls.append(kwargs)
        return DocumentIngestionHostResult(
            summary={
                "state": "ready",
                "document_id": "file-1",
                "retrievable_preview": "compiled preview",
                "index": {"state": "indexed", "indexed_chunks": 1},
            },
            file_info_override={
                "name": "sample.pdf",
                "detected_type": "document",
                "text_content": "compiled preview",
            },
        )


class FakeCollaboration:
    def __init__(self, order):
        self.order = order
        self.calls = []

    async def analyze_file(self, **kwargs):
        self.order.append("collaboration")
        self.calls.append(kwargs)
        return {
            "file_info": kwargs["file_info_override"],
            "collaboration_results": {
                "semantic_seeds": {"enabled": False},
                "daily_planning": {"enabled": False},
                "content_drafting": {"enabled": False},
            },
        }


@pytest.mark.asyncio
async def test_file_analysis_uses_one_compiler_projection_before_collaboration(
    tmp_path, monkeypatch
):
    source = tmp_path / "sample.pdf"
    source.write_bytes(b"pdf")
    order = []
    store = FakeStore()
    document_facade = FakeDocumentFacade(order)
    service = FileAnalysisService(
        store=store,
        timeline_items_store=object(),
        tasks_store=object(),
        document_ingestion_facade=document_facade,
    )
    collaboration = FakeCollaboration(order)
    service.collaboration_service = collaboration

    async def message(*_args, **_kwargs):
        return "uploaded"

    async def no_op(*_args, **_kwargs):
        return None

    monkeypatch.setattr(service, "_get_i18n_message", message)
    monkeypatch.setattr(service, "_create_intents_from_analysis", no_op)
    monkeypatch.setattr(service, "_create_timeline_item_from_analysis", no_op)

    result = await service.analyze_file(
        workspace_id="workspace-1",
        profile_id="user-1",
        file_id="file-1",
        file_data=None,
        file_name="sample.pdf",
        file_type="application/pdf",
        file_size=3,
        file_path=str(source),
    )

    assert order == ["document", "collaboration"]
    assert document_facade.calls[0]["checksum"] == hashlib.sha256(b"pdf").hexdigest()
    assert collaboration.calls[0]["file_info_override"]["text_content"] == (
        "compiled preview"
    )
    assert result["document_ingestion"]["index"]["state"] == "indexed"
    event = store.events[0][0]
    assert event.metadata["file_analysis"]["document_ingestion"]["state"] == "ready"
    assert store.events[0][1] is True
