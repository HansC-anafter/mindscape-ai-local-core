"""Owner-declared records and graph compile through the document seam."""

from backend.app.services.knowledge_projection.retrievable.document_adapter import (
    compile_document_projection,
)


def test_owner_declared_document_projection_is_complete_and_referential() -> None:
    records = [
        {
            "source_id": "health:rev-1:0",
            "title": "Health",
            "content": "Sleep regularity is associated with cognitive health.",
            "embedding": [1.0, 0.0],
            "metadata": {
                "workspace_id": "workspace-health",
                "document_id": "health",
                "revision_id": "rev-1",
                "checksum": "a" * 64,
                "chunk_id": "chunk-0",
                "active": True,
                "embedding_model": "test",
            },
        }
    ]

    payload, documents = compile_document_projection(
        workspace_id="workspace-health",
        document_id="health",
        revision_id="rev-1",
        records=records,
        projection_records=(
            {
                "record_kind": "health_claim",
                "record_key": "claim.sleep-cognition",
                "search_text": "sleep regularity cognition",
                "citation": {"url": "https://example.test/source"},
                "values": {"evidence_grade": "systematic_review"},
                "facets": (
                    {
                        "key": "domain",
                        "value_type": "enum",
                        "value": "sleep",
                    },
                ),
            },
        ),
        owner_declared_graph={
            "entities": (
                {
                    "canonical_key": "mesh:sleep",
                    "entity_type": "concept",
                },
                {
                    "canonical_key": "mesh:cognition",
                    "entity_type": "concept",
                },
            ),
            "mentions": (
                {
                    "entity_key": "mesh:sleep",
                    "record_key": "claim.sleep-cognition",
                    "surface_text": "Sleep regularity",
                },
                {
                    "entity_key": "mesh:cognition",
                    "record_key": "claim.sleep-cognition",
                    "surface_text": "cognitive health",
                },
            ),
            "relations": (
                {
                    "relation_key": "sleep-associated-cognition",
                    "source_entity_key": "mesh:sleep",
                    "target_entity_key": "mesh:cognition",
                    "relation_kind": "associated_with",
                },
            ),
            "communities": (
                {
                    "community_key": "sleep-cognition",
                    "entity_keys": ("mesh:sleep", "mesh:cognition"),
                    "relation_keys": ("sleep-associated-cognition",),
                },
            ),
            "reports": (
                {
                    "community_key": "sleep-cognition",
                    "summary": "Sleep and cognition are linked by cited evidence.",
                },
            ),
        },
    )

    assert len(documents) == 1
    assert payload.projector_revision == "document-index.owner-declared.v1"
    assert len(payload.records) == 1
    assert payload.graph_complete is True
    assert payload.graph_required is True
    assert payload.relation_count == 1
    assert payload.graph is not None
    assert payload.graph.relations[0].supporting_evidence_unit_keys == (
        "chunk-0",
    )


def test_plain_document_keeps_legacy_projection_shape() -> None:
    payload, _ = compile_document_projection(
        workspace_id="workspace-health",
        document_id="plain",
        revision_id="rev-1",
        records=(
            {
                "source_id": "plain:rev-1:0",
                "title": "Plain",
                "content": "Plain content",
                "embedding": [1.0, 0.0],
                "metadata": {
                    "workspace_id": "workspace-health",
                    "document_id": "plain",
                    "revision_id": "rev-1",
                    "checksum": "b" * 64,
                    "chunk_id": "chunk-0",
                    "active": True,
                    "embedding_model": "test",
                },
            },
        ),
    )

    assert payload.projector_revision == "document-index.v2"
    assert payload.records == ()
    assert payload.graph is None
