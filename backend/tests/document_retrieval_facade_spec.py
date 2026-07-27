import pytest

from backend.app.services.conversation.context_builder.memory_retriever import (
    _format_document_hit,
)
from backend.app.services.document_retrieval_facade import DocumentRetrievalFacade
from backend.app.services.knowledge_retrieval.contracts import (
    AuthorizedKnowledgeHit,
    KnowledgeRetrievalResult,
)


def _row(identifier="row-1"):
    return {
        "id": identifier,
        "source_id": "doc-1:rev-1:chunk-1",
        "content": "A cited architecture statement.",
        "metadata": {
            "workspace_id": "workspace-1",
            "document_id": "doc-1",
            "revision_id": "rev-1",
            "chunk_id": "chunk-1",
            "node_ids": ["node-1"],
            "source_locations": [
                {
                    "page_or_slide": 2,
                    "bounds": {"x": 1, "y": 2, "width": 3, "height": 4},
                }
            ],
            "schema_version": "document_schema.v1",
            "index_version": "document-index.v1",
            "file_name": "architecture.pdf",
            "heading_path": ["System", "Data plane"],
        },
    }


class FakeRetrievalFacade:
    def __init__(self, channels=("text_vector", "keyword")):
        self.channels = channels
        self.requests = []

    async def search(self, request):
        self.requests.append(request)
        row = _row()
        return KnowledgeRetrievalResult(
            hits=(
                AuthorizedKnowledgeHit(
                    knowledge_resource_id="resource-1",
                    security_label_id="label-1",
                    authz_revision=1,
                    projection_revision_id="projection-1",
                    source_app="document_ingestion",
                    source_id=row["source_id"],
                    content=row["content"],
                    metadata=row["metadata"],
                    score=0.5,
                    channels=self.channels,
                    citation={},
                ),
            ),
            requested_mode="hybrid",
            executed_mode="hybrid",
            candidate_count=1,
            final_authorized_count=1,
            transaction_count=2,
            degraded_reasons=(),
            authorization_receipt_digest="a" * 64,
        )


@pytest.mark.asyncio
async def test_document_compatibility_entry_delegates_to_canonical_reader():
    retrieval = FakeRetrievalFacade()
    facade = DocumentRetrievalFacade(
        retrieval_facade=retrieval,
    )

    hits = await facade.search(
        query="architecture",
        user_id="user-1",
        workspace_id="workspace-1",
        top_k=5,
    )

    request = retrieval.requests[0]
    assert request.scope_type == "workspace"
    assert request.scope_id == "workspace-1"
    assert request.source_apps == ("document_ingestion",)
    assert request.owner_capabilities == ("document_ingestion",)
    assert hits[0]["channels"] == ["text_vector", "keyword"]
    assert hits[0]["citation"]["chunk_id"] == "chunk-1"
    assert hits[0]["source_label"] == "architecture.pdf"


@pytest.mark.asyncio
async def test_keyword_retrieval_survives_embedding_outage():
    retrieval = FakeRetrievalFacade(channels=("keyword",))
    facade = DocumentRetrievalFacade(
        retrieval_facade=retrieval,
    )

    hits = await facade.search(
        query="architecture",
        user_id="user-1",
        workspace_id="workspace-1",
        top_k=3,
    )

    assert hits[0]["channels"] == ["keyword"]


def test_memory_context_formatter_preserves_exact_citation_location():
    hit = {
        "source_label": "architecture.pdf",
        "heading_path": ["System", "Data plane"],
        "retrievable_text": "A cited architecture statement.",
        "citation": {
            "document_id": "doc-1",
            "chunk_id": "chunk-1",
            "source_locations": _row()["metadata"]["source_locations"],
        },
    }

    formatted = _format_document_hit(hit)

    assert "architecture.pdf" in formatted
    assert "System > Data plane" in formatted
    assert "page/slide 2" in formatted
    assert "bbox(1,2,3,4)" in formatted
    assert "chunk chunk-1" in formatted
