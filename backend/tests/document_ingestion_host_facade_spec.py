import hashlib

import pytest

from backend.app.services.document_chunk_index_store import DocumentIndexWriteResult
from backend.app.services.file_analysis_service_core.document_ingestion_facade import (
    DocumentIngestionHostFacade,
)


class FakeToolExecutor:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    async def execute_tool(self, tool_name, **kwargs):
        self.calls.append((tool_name, kwargs))
        if self.error:
            raise self.error
        return self.result


class FakeVectorService:
    def __init__(self, embedding=None, model="bge-m3", error=None):
        self.embedding = embedding if embedding is not None else [0.1, 0.2]
        self.model = model
        self.error = error
        self.calls = []

    async def _generate_embedding_with_model(self, text, *, is_query):
        self.calls.append((text, is_query))
        if self.error:
            raise self.error
        return self.embedding, self.model


class FakeIndexStore:
    def __init__(self, reused=None, find_error=None):
        self.reused = reused
        self.find_error = find_error
        self.find_calls = []
        self.replace_calls = []

    def find_active_revision(self, **kwargs):
        self.find_calls.append(kwargs)
        if self.find_error:
            raise self.find_error
        return self.reused

    def replace_active_revision(self, **kwargs):
        self.replace_calls.append(kwargs)
        return DocumentIndexWriteResult(
            state="indexed",
            indexed_chunks=len(kwargs["records"]),
            revision_id=kwargs["revision_id"],
            embedding_model="bge-m3",
        )


def _compilation(*, state="ready"):
    return {
        "contract_version": "document_compilation_result.v1",
        "state": state,
        "schema_artifact": {
            "schema_version": "document_schema.v1",
            "document_id": "file-1",
            "revision_id": "sha256-aaaaaaaaaaaaaaaa",
            "checksum": "a" * 64,
            "pipeline_version": "document-ingestion-1.0.0",
            "nodes": [{"node_id": "node-1"}],
        },
        "chunk_manifest": {
            "retrieval_ready": state == "ready",
            "chunks": [
                {
                    "chunk_id": "chunk-1",
                    "node_ids": ["node-1"],
                    "heading_path": ["Architecture"],
                    "retrievable_text": "Architecture\nA complete bounded chunk.",
                    "source_locations": [{"page_or_slide": 1}],
                }
            ],
        },
        "retrievable_preview": "Architecture\nA complete bounded chunk.",
        "warnings": [] if state == "ready" else ["ocr_required"],
        "visual_candidate_count": 0 if state == "ready" else 1,
    }


def _source(tmp_path):
    source = tmp_path / "sample.pdf"
    source.write_bytes(b"pdf")
    return source, hashlib.sha256(b"pdf").hexdigest()


@pytest.mark.asyncio
async def test_ready_document_compiles_persists_and_indexes_complete_revision(tmp_path):
    source, checksum = _source(tmp_path)
    compilation = _compilation()
    compilation["schema_artifact"]["checksum"] = checksum
    tool = FakeToolExecutor(compilation)
    vector = FakeVectorService()
    index = FakeIndexStore()
    facade = DocumentIngestionHostFacade(
        tool_executor=tool,
        vector_service=vector,
        index_store=index,
    )

    result = await facade.compile_and_index(
        workspace_id="workspace-1",
        user_id="user-1",
        source_artifact_id="file-1",
        file_path=str(source),
        file_name="sample.pdf",
        file_type="application/pdf",
        file_size=3,
        checksum=checksum,
    )

    assert tool.calls[0][0] == "document_ingestion.compile_document"
    assert tool.calls[0][1]["allow_ocr"] is False
    assert vector.calls == [("Architecture\nA complete bounded chunk.", False)]
    assert len(index.replace_calls) == 1
    metadata = index.replace_calls[0]["records"][0]["metadata"]
    assert metadata["workspace_id"] == "workspace-1"
    assert metadata["active"] is True
    assert metadata["embedding_source_dimension"] == 2
    assert result.summary["index"]["state"] == "indexed"
    assert result.summary["node_count"] == 1
    assert "schema_artifact" not in result.summary
    assert source.with_suffix(".document-ingestion.json").is_file()
    assert result.file_info_override["text_content"].startswith("Architecture")


@pytest.mark.asyncio
async def test_existing_active_revision_skips_all_embedding_work(tmp_path):
    source, checksum = _source(tmp_path)
    compilation = _compilation()
    compilation["schema_artifact"]["checksum"] = checksum
    reused = DocumentIndexWriteResult(
        state="reused",
        indexed_chunks=1,
        revision_id="sha256-aaaaaaaaaaaaaaaa",
        embedding_model="bge-m3",
    )
    vector = FakeVectorService()
    index = FakeIndexStore(reused=reused)
    facade = DocumentIngestionHostFacade(
        tool_executor=FakeToolExecutor(compilation),
        vector_service=vector,
        index_store=index,
    )

    result = await facade.compile_and_index(
        workspace_id="workspace-1",
        user_id="user-1",
        source_artifact_id="file-1",
        file_path=str(source),
        file_name="sample.pdf",
        file_type=None,
        file_size=None,
        checksum=checksum,
    )

    assert result.summary["index"]["state"] == "reused"
    assert vector.calls == []
    assert index.replace_calls == []


@pytest.mark.asyncio
async def test_degraded_compilation_writes_artifact_without_indexing(tmp_path):
    source, checksum = _source(tmp_path)
    compilation = _compilation(state="degraded")
    compilation["schema_artifact"]["checksum"] = checksum
    index = FakeIndexStore()
    facade = DocumentIngestionHostFacade(
        tool_executor=FakeToolExecutor(compilation),
        vector_service=FakeVectorService(),
        index_store=index,
    )

    result = await facade.compile_and_index(
        workspace_id="workspace-1",
        user_id="user-1",
        source_artifact_id="file-1",
        file_path=str(source),
        file_name="sample.pdf",
        file_type=None,
        file_size=None,
        checksum=checksum,
    )

    assert result.summary["state"] == "degraded"
    assert result.summary["index"]["state"] == "not_ready"
    assert index.find_calls == []
    assert index.replace_calls == []


@pytest.mark.asyncio
async def test_embedding_failure_never_replaces_the_active_revision(tmp_path):
    source, checksum = _source(tmp_path)
    compilation = _compilation()
    compilation["schema_artifact"]["checksum"] = checksum
    index = FakeIndexStore()
    facade = DocumentIngestionHostFacade(
        tool_executor=FakeToolExecutor(compilation),
        vector_service=FakeVectorService(error=RuntimeError("embedding offline")),
        index_store=index,
    )

    result = await facade.compile_and_index(
        workspace_id="workspace-1",
        user_id="user-1",
        source_artifact_id="file-1",
        file_path=str(source),
        file_name="sample.pdf",
        file_type=None,
        file_size=None,
        checksum=checksum,
    )

    assert result.summary["index"]["state"] == "failed"
    assert index.replace_calls == []


@pytest.mark.asyncio
async def test_index_database_outage_does_not_abort_file_analysis(tmp_path):
    source, checksum = _source(tmp_path)
    compilation = _compilation()
    compilation["schema_artifact"]["checksum"] = checksum
    index = FakeIndexStore(find_error=RuntimeError("database offline"))
    facade = DocumentIngestionHostFacade(
        tool_executor=FakeToolExecutor(compilation),
        vector_service=FakeVectorService(),
        index_store=index,
    )

    result = await facade.compile_and_index(
        workspace_id="workspace-1",
        user_id="user-1",
        source_artifact_id="file-1",
        file_path=str(source),
        file_name="sample.pdf",
        file_type=None,
        file_size=None,
        checksum=checksum,
    )

    assert result.summary["state"] == "ready"
    assert result.summary["index"]["state"] == "failed"
    assert result.file_info_override["text_content"].startswith("Architecture")


@pytest.mark.asyncio
async def test_missing_compiler_falls_back_without_claiming_a_document_preview(tmp_path):
    source, checksum = _source(tmp_path)
    facade = DocumentIngestionHostFacade(
        tool_executor=FakeToolExecutor(error=RuntimeError("pack unavailable")),
        vector_service=FakeVectorService(),
        index_store=FakeIndexStore(),
    )

    result = await facade.compile_and_index(
        workspace_id="workspace-1",
        user_id="user-1",
        source_artifact_id="file-1",
        file_path=str(source),
        file_name="sample.pdf",
        file_type=None,
        file_size=None,
        checksum=checksum,
    )

    assert result.summary["state"] == "failed"
    assert result.summary["warnings"] == ["document_ingestion_compiler_unavailable"]
    assert result.file_info_override is None


@pytest.mark.asyncio
async def test_non_document_file_is_outside_the_facade_boundary(tmp_path):
    source = tmp_path / "note.txt"
    source.write_text("hello")
    facade = DocumentIngestionHostFacade(
        tool_executor=FakeToolExecutor(),
        vector_service=FakeVectorService(),
        index_store=FakeIndexStore(),
    )

    result = await facade.compile_and_index(
        workspace_id="workspace-1",
        user_id="user-1",
        source_artifact_id="file-1",
        file_path=str(source),
        file_name="note.txt",
        file_type="text/plain",
        file_size=5,
        checksum=hashlib.sha256(b"hello").hexdigest(),
    )

    assert result is None
