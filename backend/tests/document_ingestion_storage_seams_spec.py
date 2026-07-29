import hashlib
import json
from types import SimpleNamespace

import pytest

from backend.app.services.document_chunk_index_store import (
    DocumentChunkIndexStore,
    fit_external_docs_embedding,
)
from backend.app.services.file_analysis_service_core.document_ingestion_artifact_store import (
    DocumentIngestionArtifactStore,
)
from backend.app.services.file_analysis_service_core.document_ingestion_facade import (
    build_event_analysis_projection,
)


class FakeCursor:
    def __init__(self, row=None, executemany_error=None):
        self.row = row
        self.executemany_error = executemany_error
        self.calls = []
        self.batch = None

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def executemany(self, query, batch):
        self.calls.append((query, None))
        self.batch = batch
        if self.executemany_error:
            raise self.executemany_error

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_obj = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self, **_kwargs):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


class FakeAuthorizedStore:
    def __init__(self, *, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def find_active_document_revision(self, **kwargs):
        self.calls.append(("find", kwargs))
        return self.result

    def replace_trusted_document_revision(self, **kwargs):
        self.calls.append(("replace", kwargs))
        if self.error:
            raise self.error
        return self.result


def _authorized_result(*, state="indexed", chunks=1):
    return SimpleNamespace(
        state=state,
        indexed_chunks=chunks,
        revision_id="rev-1",
        embedding_model="bge-m3",
        knowledge_resource_id="kr-1",
        security_label_id="label-1",
        projection_revision_id="projection-1",
        authz_revision=1,
    )


def _record():
    return {
        "source_id": "doc-1:rev-1:chunk-1",
        "title": "sample.pdf",
        "content": "A bounded chunk",
        "embedding": [0.1, 0.2],
        "metadata": {
            "workspace_id": "workspace-1",
            "document_id": "doc-1",
            "revision_id": "rev-1",
            "active": True,
            "embedding_model": "bge-m3",
        },
    }


def test_artifact_store_writes_atomically_reuses_and_repairs(tmp_path):
    source = tmp_path / "sample.pdf"
    source.write_bytes(b"pdf")
    store = DocumentIngestionArtifactStore()
    compilation = {"state": "ready", "schema_artifact": {"nodes": []}}

    first = store.write(
        file_path=str(source),
        compilation=compilation,
        file_name="sample.pdf",
        workspace_id="workspace-1",
    )
    second = store.write(
        file_path=str(source),
        compilation=compilation,
        file_name="sample.pdf",
        workspace_id="workspace-1",
    )

    artifact = tmp_path / "sample.document-ingestion.json"
    assert first == second
    assert first.storage_key == str(artifact)
    assert hashlib.sha256(artifact.read_bytes()).hexdigest() == first.checksum
    assert not list(tmp_path.glob("*.tmp"))

    artifact.write_text("corrupt", encoding="utf-8")
    repaired = store.write(
        file_path=str(source),
        compilation=compilation,
        file_name="sample.pdf",
        workspace_id="workspace-1",
    )
    assert repaired == first
    assert json.loads(artifact.read_text())["compilation"]["state"] == "ready"


def test_find_active_revision_prefilters_workspace_identity_and_pipeline():
    authorized = FakeAuthorizedStore(
        result=_authorized_result(state="reused", chunks=3)
    )
    store = DocumentChunkIndexStore(
        lambda: None,
        authorized_store=authorized,
    )

    result = store.find_active_revision(
        user_id="user-1",
        workspace_id="workspace-1",
        document_id="doc-1",
        checksum="a" * 64,
        pipeline_version="pipeline-1",
    )

    assert result.state == "reused"
    assert result.indexed_chunks == 3
    assert authorized.calls == [("find", {
        "user_id": "user-1",
        "workspace_id": "workspace-1",
        "document_id": "doc-1",
        "checksum": "a" * 64,
        "pipeline_version": "pipeline-1",
    })]


def test_replace_active_revision_is_one_delete_insert_transaction():
    authorized = FakeAuthorizedStore(result=_authorized_result())
    store = DocumentChunkIndexStore(
        lambda: None,
        authorized_store=authorized,
    )

    result = store.replace_active_revision(
        user_id="user-1",
        workspace_id="workspace-1",
        document_id="doc-1",
        revision_id="rev-1",
        records=[_record()],
    )

    assert authorized.calls[0][0] == "replace"
    assert authorized.calls[0][1]["records"] == [_record()]
    assert result.state == "indexed"
    assert result.knowledge_resource_id == "kr-1"
    assert result.projection_revision_id == "projection-1"


def test_replace_active_revision_propagates_canonical_writer_failure():
    authorized = FakeAuthorizedStore(error=RuntimeError("insert failed"))
    store = DocumentChunkIndexStore(
        lambda: None,
        authorized_store=authorized,
    )

    with pytest.raises(RuntimeError, match="insert failed"):
        store.replace_active_revision(
            user_id="user-1",
            workspace_id="workspace-1",
            document_id="doc-1",
            revision_id="rev-1",
            records=[_record()],
        )

    assert authorized.calls[0][0] == "replace"


def test_external_docs_embedding_adapter_pads_but_never_truncates():
    fitted = fit_external_docs_embedding([0.3, 0.4])

    assert len(fitted) == 1536
    assert fitted[:2] == [0.3, 0.4]
    assert set(fitted[2:]) == {0.0}
    with pytest.raises(ValueError, match="dimension_exceeds"):
        fit_external_docs_embedding([0.1] * 1537)


def test_event_projection_keeps_only_bounded_document_summary():
    original = {
        "file_info": {"text_content": "x" * 5000},
        "document_ingestion": {
            "retrievable_preview": "y" * 5000,
            "schema_artifact": {"nodes": [1]},
            "chunk_manifest": {"chunks": [1]},
        },
    }

    projection = build_event_analysis_projection(original)

    assert len(projection["file_info"]["text_content"]) == 4000
    assert len(projection["document_ingestion"]["retrievable_preview"]) == 4000
    assert "schema_artifact" not in projection["document_ingestion"]
    assert "chunk_manifest" not in projection["document_ingestion"]
    assert len(original["file_info"]["text_content"]) == 5000
