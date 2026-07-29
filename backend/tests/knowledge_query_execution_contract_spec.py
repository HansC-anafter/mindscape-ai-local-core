"""Knowledge query exposes one honest, source-bounded execution receipt."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.services.knowledge_retrieval.contracts import (
    AuthorizedKnowledgeHit,
    KnowledgeRetrievalResult,
)
from backend.app.services.knowledge_retrieval.store import (
    _AUTHORIZED_CTE,
    _candidate_common_parameters,
)
from backend.app.services.knowledge_graph.query_store_common import (
    AUTHORIZED_PROJECTIONS_CTE,
    common_parameters,
)
from backend.app.services.knowledge_authorization import (
    PrincipalRef,
    RetrievalAccessContext,
)
from backend.app.services.tools.knowledge_query.contracts import (
    KnowledgeQueryInput,
)
from backend.app.services.tools.knowledge_query.query_service import (
    KnowledgeQueryService,
)


class _RetrievalFacade:
    def __init__(self) -> None:
        self.request = None

    async def search(self, request):
        self.request = request
        citation = {
            "citation_id": "external_doc:doc-1",
            "knowledge_resource_id": "kr_1",
            "security_label_id": "ksl_1",
            "projection_revision_id": "kpr_1",
            "source_ref": "document:health-frontier:sleep",
            "content_hash": "a" * 64,
        }
        return KnowledgeRetrievalResult(
            hits=(
                AuthorizedKnowledgeHit(
                    knowledge_resource_id="kr_1",
                    security_label_id="ksl_1",
                    authz_revision=7,
                    projection_revision_id="kpr_1",
                    source_app="health_frontier_wiki",
                    source_id="health-frontier:sleep",
                    content="bounded evidence",
                    metadata={"domain_id": "sleep"},
                    score=1.0,
                    channels=("graph_neighborhood",),
                    citation=citation,
                ),
            ),
            requested_mode="local_graph",
            executed_mode="local_graph",
            candidate_count=1,
            final_authorized_count=1,
            transaction_count=2,
            degraded_reasons=(),
            authorization_receipt_digest="b" * 64,
            fusion_revision="graph_neighborhood_confidence_depth.v1",
            channel_coverage={
                "applied_source_ids": ["health-frontier:sleep"],
            },
        )


def _access_context() -> RetrievalAccessContext:
    return RetrievalAccessContext.create(
        subject_user_id="owner",
        tenant_id="local",
        principals=(PrincipalRef("user", "owner"),),
    )


def test_authorization_cte_parameters_cover_source_identity_filters() -> None:
    context = _access_context()
    hybrid_parameters = _candidate_common_parameters(
        context=context,
        scope_type="workspace",
        scope_id="workspace-1",
        source_apps=("health_frontier_wiki",),
        source_ids=("health-frontier:sleep",),
        owner_capabilities=("external_docs",),
        modality_filter="text",
    )
    graph_parameters = common_parameters(
        context=context,
        scope_type="workspace",
        scope_id="workspace-1",
        source_apps=("health_frontier_wiki",),
        source_ids=("health-frontier:sleep",),
        owner_capabilities=("external_docs",),
        modality_filter="text",
    )

    assert _AUTHORIZED_CTE.count("%s") == len(hybrid_parameters)
    assert AUTHORIZED_PROJECTIONS_CTE.count("%s") == len(
        graph_parameters
    )
    assert "document.source_id = ANY" in _AUTHORIZED_CTE
    assert "resource.source_id = ANY" in AUTHORIZED_PROJECTIONS_CTE


def test_source_identity_filter_is_not_silently_ignored_by_aggregate() -> None:
    with pytest.raises(
        ValidationError,
        match="knowledge_query_source_ids_only_for_search",
    ):
        KnowledgeQueryInput.model_validate(
            {
                "operation": "aggregate",
                "group_by": "health.domain",
                "measure": "count",
                "resource_filters": {
                    "source_ids": ["health-frontier:sleep"],
                },
            }
        )


@pytest.mark.asyncio
async def test_verified_query_applies_source_ids_and_reports_actual_path() -> None:
    retrieval = _RetrievalFacade()
    service = KnowledgeQueryService(retrieval_facade=retrieval)
    request = KnowledgeQueryInput.model_validate(
        {
            "operation": "search",
            "query": "睡眠規律",
            "retrieval_mode": "local_graph",
            "scope": "active_group",
            "resource_filters": {
                "source_apps": ["health_frontier_wiki"],
                "source_ids": [
                    "health-frontier:sleep",
                    "health-frontier:sleep",
                ],
            },
        }
    )
    assert request.resource_filters.source_ids == (
        "health-frontier:sleep",
    )

    payload, bindings = (
        await service.execute_with_verified_access_context(
            request,
            access_context=object(),
            scope_type="group",
            scope_id="wg_health",
        )
    )

    assert retrieval.request.source_ids == ("health-frontier:sleep",)
    assert bindings == (("kr_1", 7),)
    assert payload["receipt"]["execution_path"] == {
        "selection_source": "caller_explicit",
        "requested_mode": "local_graph",
        "executed_mode": "local_graph",
        "fusion_revision": (
            "graph_neighborhood_confidence_depth.v1"
        ),
    }
    assert payload["coverage"]["channel_coverage"][
        "applied_source_ids"
    ] == ["health-frontier:sleep"]
