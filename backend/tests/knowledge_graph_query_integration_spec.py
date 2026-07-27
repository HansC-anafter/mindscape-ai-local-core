"""Disposable-PostgreSQL acceptance for authorized graph/query operations."""

from __future__ import annotations

import hashlib
import os
from dataclasses import replace

import psycopg2
import pytest

from backend.app.services.authorized_knowledge_index_store import (
    AuthorizedKnowledgeIndexStore,
)
from backend.app.services.knowledge_authorization import (
    KnowledgeGrant,
    KnowledgePermission,
    KnowledgeResourceIdentity,
    PrincipalRef,
    RetrievalAccessContext,
    visibility_partition_hash_for_grants,
)
from backend.app.services.knowledge_graph.contracts import (
    GraphCommunityReportWrite,
    GraphEntityWrite,
    GraphMentionWrite,
    GraphProjectionWrite,
    GraphRelationWrite,
)
from backend.app.services.knowledge_graph.community import (
    build_visibility_partitioned_communities,
)
from backend.app.services.knowledge_projection.retrievable.write_contracts import (
    ProjectionChannelWrite,
    ProjectionEvidenceWrite,
    ProjectionFacetWrite,
    ProjectionRecordWrite,
    RetrievableProjectionWrite,
)
from backend.app.services.knowledge_retrieval import (
    AuthorizationAwareKnowledgeRetrievalFacade,
    CitationLookup,
    FacetFilter,
    KnowledgeAggregateRequest,
    KnowledgeCitationFetchRequest,
    KnowledgeCoverageRequest,
    KnowledgeRetrievalRequest,
)


TEST_VECTOR_URL = os.getenv("TEST_VECTOR_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_VECTOR_URL,
    reason="TEST_VECTOR_DATABASE_URL is required",
)


def _connection():
    return psycopg2.connect(TEST_VECTOR_URL)


class _VectorService:
    def _get_connection(self):
        return _connection()

    async def _generate_embedding_with_model(self, *_args, **_kwargs):
        raise AssertionError("graph_operation_must_not_generate_query_embedding")


def _context(user_id: str, *, writer: bool = False):
    permissions = ()
    if writer:
        permissions = (
            KnowledgePermission(
                "knowledge.project",
                "workspace",
                "workspace-graph-spec",
            ),
        )
    return RetrievalAccessContext.create(
        subject_user_id=user_id,
        tenant_id="local",
        principals=(PrincipalRef("user", user_id),),
        permissions=permissions,
    )


def _graph_payload(
    *,
    user_id: str,
    source_id: str,
    marker: str,
    confidence: float,
) -> RetrievableProjectionWrite:
    grants = (
        KnowledgeGrant(
            PrincipalRef("user", user_id),
            relation="owner",
        ),
    )
    visibility_hash = visibility_partition_hash_for_grants(grants)
    content = f"{marker} alpha collaborates with beta"
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    entities = (
        GraphEntityWrite("alpha", "concept", "exact.v1"),
        GraphEntityWrite("beta", "concept", "exact.v1"),
    )
    relations = (
        GraphRelationWrite(
            relation_key="alpha-beta",
            source_entity_key="alpha",
            target_entity_key="beta",
            relation_kind="collaborates_with",
            origin="extracted",
            confidence=confidence,
            supporting_evidence_unit_keys=("unit-1",),
            supporting_citations=(
                {
                    "source_ref": f"object:{source_id}",
                    "anchor": "unit-1",
                },
            ),
            extractor_revision="extractor.v1",
        ),
    )
    communities = build_visibility_partitioned_communities(
        entities=entities,
        relations=relations,
        visibility_partition_hash=visibility_hash,
    )
    graph = GraphProjectionWrite(
        algorithm_revision="connected_components.v1",
        resolver_revision="exact.v1",
        visibility_partition_hash=visibility_hash,
        entities=entities,
        mentions=(
            GraphMentionWrite(
                entity_key="alpha",
                evidence_unit_key="unit-1",
                record_key="record-1",
                surface_text="alpha",
                mention_type="entity",
                confidence=confidence,
                citation={
                    "source_ref": f"object:{source_id}",
                    "anchor": "unit-1",
                },
                extractor_revision="extractor.v1",
                model_revision="fixture.v1",
                prompt_revision="fixture.v1",
            ),
            GraphMentionWrite(
                entity_key="beta",
                evidence_unit_key="unit-1",
                record_key="record-1",
                surface_text="beta",
                mention_type="entity",
                confidence=confidence,
                citation={
                    "source_ref": f"object:{source_id}",
                    "anchor": "unit-1",
                },
                extractor_revision="extractor.v1",
                model_revision="fixture.v1",
                prompt_revision="fixture.v1",
            ),
        ),
        relations=relations,
        communities=communities,
        reports=(
            GraphCommunityReportWrite(
                community_key=communities[0].community_key,
                summary=f"{marker} alpha and beta form a design theme",
                findings=(
                    {
                        "claim": "alpha collaborates with beta",
                        "source_ref": f"object:{source_id}",
                    },
                ),
                rank=confidence,
                supporting_citations=(
                    {
                        "source_ref": f"object:{source_id}",
                        "anchor": "unit-1",
                    },
                ),
                model_revision="fixture.v1",
                prompt_revision="fixture.v1",
            ),
        ),
    )
    return RetrievableProjectionWrite(
        source_instance_id=source_id,
        source_revision="revision-1",
        content_hash=content_hash,
        descriptor_id="graph_fixture",
        descriptor_revision="graph-fixture.v1",
        projector_revision="graph-fixture.v1",
        facet_schema_revision="graph-fixture.v1",
        embedding_profile_revision="graph-derivative.v1",
        projection_hash=hashlib.sha256(
            f"{source_id}:{content_hash}".encode("utf-8")
        ).hexdigest(),
        evidence_units=(
            ProjectionEvidenceWrite(
                unit_key="unit-1",
                unit_kind="text_span",
                owner_asset_ref=f"object:{source_id}",
                content_hash=content_hash,
                media_type="text/plain",
                anchor={"kind": "text_span", "start": 0, "end": len(content)},
            ),
        ),
        channels=(
            ProjectionChannelWrite(
                unit_key="unit-1",
                channel_id="text.graph-derivative",
                modality="text",
                profile_revision="graph-derivative.v1",
                model_revision=None,
                dimension=None,
                calibration_revision=None,
                index_revision=None,
                required=False,
                state="not_admitted",
                row_count=0,
                byte_count=0,
                reason="fixture_has_no_vector_channel",
            ),
        ),
        records=(
            ProjectionRecordWrite(
                record_kind="theme",
                record_key="record-1",
                search_text=content,
                citation={
                    "source_ref": f"object:{source_id}",
                    "anchor": "unit-1",
                },
                values={"theme": "design"},
                content_hash=content_hash,
                facets=(
                    ProjectionFacetWrite(
                        key="theme",
                        value_type="string",
                        value="design",
                    ),
                ),
            ),
        ),
        relation_count=1,
        graph_complete=True,
        graph_required=True,
        graph=graph,
    )


def _write_graph_resource(
    *,
    user_id: str,
    source_id: str,
    marker: str,
    confidence: float,
):
    return AuthorizedKnowledgeIndexStore(_connection).replace_projection(
        access_context=_context(user_id, writer=True),
        identity=KnowledgeResourceIdentity(
            tenant_id="local",
            owner_capability_code="synthetic_graph_fixture",
            source_kind="object",
            source_app="synthetic_graph_fixture",
            source_id=source_id,
            source_ref=f"object:{source_id}",
            source_revision="revision-1",
            owner_scope_type="workspace",
            owner_scope_id="workspace-graph-spec",
            classification="workspace",
        ),
        payload=_graph_payload(
            user_id=user_id,
            source_id=source_id,
            marker=marker,
            confidence=confidence,
        ),
        documents=(),
    )


@pytest.mark.asyncio
async def test_graph_modes_prefilter_decoy_and_keep_raw_citations() -> None:
    authorized = _write_graph_resource(
        user_id="graph-reader",
        source_id="authorized-graph",
        marker="AUTHORIZED_GRAPH",
        confidence=0.8,
    )
    _write_graph_resource(
        user_id="graph-other",
        source_id="unauthorized-graph",
        marker="UNAUTHORIZED_GRAPH_DECOY",
        confidence=1.0,
    )
    facade = AuthorizationAwareKnowledgeRetrievalFacade(
        vector_service=_VectorService(),
    )
    context = _context("graph-reader")
    for mode in ("local_graph", "multi_hop", "global_graph"):
        result = await facade.search(
            KnowledgeRetrievalRequest(
                query="alpha",
                access_context=context,
                scope_type="workspace",
                scope_id="workspace-graph-spec",
                top_k=10,
                retrieval_mode=mode,
            )
        )
        assert result.transaction_count == 2
        assert {
            hit.knowledge_resource_id for hit in result.hits
        } == {authorized.knowledge_resource_id}
        serialized = " ".join(hit.content for hit in result.hits)
        assert "AUTHORIZED_GRAPH" in serialized
        assert "UNAUTHORIZED_GRAPH_DECOY" not in serialized
        assert all(hit.citation.get("content_hash") for hit in result.hits)
        if mode != "global_graph":
            assert result.graph_metrics["visited_edges"] == 1


@pytest.mark.asyncio
async def test_graph_modes_accept_authorized_query_evidence_ref_in_two_transactions() -> None:
    _write_graph_resource(
        user_id="graph-seed-reader",
        source_id="authorized-graph-seed",
        marker="AUTHORIZED_GRAPH_SEED",
        confidence=0.85,
    )
    facade = AuthorizationAwareKnowledgeRetrievalFacade(
        vector_service=_VectorService(),
    )
    context = _context("graph-seed-reader")
    initial = await facade.search(
        KnowledgeRetrievalRequest(
            query="alpha",
            access_context=context,
            scope_type="workspace",
            scope_id="workspace-graph-spec",
            top_k=1,
            retrieval_mode="local_graph",
        )
    )
    citation = initial.hits[0].citation
    query_ref = CitationLookup(
        citation_id=str(citation["citation_id"]),
        content_hash=str(citation["content_hash"]),
    )

    for mode in ("local_graph", "multi_hop", "global_graph"):
        seeded = await facade.search(
            KnowledgeRetrievalRequest(
                query="",
                query_evidence_refs=(query_ref,),
                access_context=context,
                scope_type="workspace",
                scope_id="workspace-graph-spec",
                top_k=10,
                retrieval_mode=mode,
            )
        )
        assert seeded.transaction_count == 2
        assert any(
            "AUTHORIZED_GRAPH_SEED" in hit.content
            for hit in seeded.hits
        )

    with pytest.raises(
        ValueError,
        match="knowledge_query_evidence_ref_unavailable_or_stale",
    ):
        await facade.search(
            KnowledgeRetrievalRequest(
                query="",
                query_evidence_refs=(
                    CitationLookup(
                        citation_id=query_ref.citation_id,
                        content_hash="0" * 64,
                    ),
                ),
                access_context=context,
                scope_type="workspace",
                scope_id="workspace-graph-spec",
                retrieval_mode="local_graph",
            )
        )


@pytest.mark.asyncio
async def test_graph_modality_filter_requires_active_matching_evidence_channel() -> None:
    payload = _graph_payload(
        user_id="graph-image-reader",
        source_id="authorized-image-graph",
        marker="AUTHORIZED_IMAGE_GRAPH",
        confidence=0.9,
    )
    image_payload = replace(
        payload,
        evidence_units=(
            replace(
                payload.evidence_units[0],
                unit_kind="image_region",
                media_type="image/png",
                anchor={
                    "kind": "image_region",
                    "x": 0.0,
                    "y": 0.0,
                    "width": 1.0,
                    "height": 1.0,
                },
            ),
        ),
        channels=(
            replace(
                payload.channels[0],
                channel_id="image.synthetic",
                modality="image",
                model_revision="synthetic-image.v1",
                dimension=4,
                index_revision="synthetic-image-index.v1",
                state="active",
                row_count=1,
                byte_count=16,
                reason=None,
                physical_store_ref="synthetic://image-index",
            ),
        ),
    )
    written = AuthorizedKnowledgeIndexStore(_connection).replace_projection(
        access_context=_context("graph-image-reader", writer=True),
        identity=KnowledgeResourceIdentity(
            tenant_id="local",
            owner_capability_code="synthetic_graph_fixture",
            source_kind="object",
            source_app="synthetic_graph_fixture",
            source_id="authorized-image-graph",
            source_ref="object:authorized-image-graph",
            source_revision="revision-1",
            owner_scope_type="workspace",
            owner_scope_id="workspace-graph-spec",
            classification="workspace",
        ),
        payload=image_payload,
        documents=(),
    )
    facade = AuthorizationAwareKnowledgeRetrievalFacade(
        vector_service=_VectorService(),
    )
    context = _context("graph-image-reader")

    for mode in ("local_graph", "multi_hop", "global_graph"):
        image_result = await facade.search(
            KnowledgeRetrievalRequest(
                query="alpha",
                access_context=context,
                scope_type="workspace",
                scope_id="workspace-graph-spec",
                top_k=10,
                retrieval_mode=mode,
                modality_filter="image",
            )
        )
        text_result = await facade.search(
            KnowledgeRetrievalRequest(
                query="alpha",
                access_context=context,
                scope_type="workspace",
                scope_id="workspace-graph-spec",
                top_k=10,
                retrieval_mode=mode,
                modality_filter="text",
            )
        )

        assert {
            hit.knowledge_resource_id for hit in image_result.hits
        } == {written.knowledge_resource_id}
        assert text_result.hits == ()


@pytest.mark.asyncio
async def test_aggregate_fetch_and_coverage_share_final_authorization() -> None:
    facade = AuthorizationAwareKnowledgeRetrievalFacade(
        vector_service=_VectorService(),
    )
    context = _context("graph-reader")
    aggregate = await facade.aggregate(
        KnowledgeAggregateRequest(
            access_context=context,
            scope_type="workspace",
            scope_id="workspace-graph-spec",
            group_by="theme",
            measure="distinct_count",
            facet_filters=(
                FacetFilter("theme", "eq", "design"),
            ),
            limit=10,
        )
    )
    assert aggregate["aggregates"] == [
        {
            "facet_type": "string",
            "group_value": "design",
            "measure": "distinct_count",
            "value": 1,
        }
    ]
    result = await facade.search(
        KnowledgeRetrievalRequest(
            query="alpha",
            access_context=context,
            scope_type="workspace",
            scope_id="workspace-graph-spec",
            top_k=1,
            retrieval_mode="local_graph",
        )
    )
    citation = result.hits[0].citation
    fetched = await facade.fetch_by_citation(
        KnowledgeCitationFetchRequest(
            access_context=context,
            scope_type="workspace",
            scope_id="workspace-graph-spec",
            citations=(
                CitationLookup(
                    citation_id=str(citation["citation_id"]),
                    content_hash=str(citation["content_hash"]),
                ),
            ),
        )
    )
    assert len(fetched["evidence"]) == 1
    assert fetched["unavailable"] == []
    stale = await facade.fetch_by_citation(
        KnowledgeCitationFetchRequest(
            access_context=context,
            scope_type="workspace",
            scope_id="workspace-graph-spec",
            citations=(
                CitationLookup(
                    citation_id=str(citation["citation_id"]),
                    content_hash="0" * 64,
                ),
            ),
        )
    )
    assert stale["evidence"] == []
    assert stale["unavailable"][0]["reason"] == "unavailable_or_stale"

    coverage = await facade.explain_coverage(
        KnowledgeCoverageRequest(
            access_context=context,
            scope_type="workspace",
            scope_id="workspace-graph-spec",
        )
    )
    assert sum(
        row["authorized_resource_count"]
        for row in coverage["resources"]
    ) == 1
    assert {
        row["state"] for row in coverage["channels"]
    } == {"not_admitted"}
