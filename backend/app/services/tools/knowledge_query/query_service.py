"""Dispatch one operation to the canonical retrieval facade."""

from __future__ import annotations

from typing import Any, Optional

from backend.app.services.knowledge_authorization.access_context_factory import (
    RetrievalAccessContextFactory,
)
from backend.app.services.knowledge_retrieval import (
    AuthorizationAwareKnowledgeRetrievalFacade,
    CitationLookup,
    FacetFilter,
    KnowledgeAggregateRequest,
    KnowledgeCitationFetchRequest,
    KnowledgeCoverageRequest,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResult,
)

from .contracts import KnowledgeQueryInput
from .result_projection import enforce_result_budget, project_search_result
from .retrieval_mode import bounds_for_mode


class KnowledgeQueryService:
    """One call performs one bounded operation and never invokes an LLM."""

    def __init__(
        self,
        retrieval_facade: Optional[
            AuthorizationAwareKnowledgeRetrievalFacade
        ] = None,
        context_factory: Optional[RetrievalAccessContextFactory] = None,
    ) -> None:
        self._retrieval_facade = (
            retrieval_facade or AuthorizationAwareKnowledgeRetrievalFacade()
        )
        self._context_factory = (
            context_factory or RetrievalAccessContextFactory()
        )

    async def execute(
        self,
        request: KnowledgeQueryInput,
        *,
        governance_context: Any,
    ) -> dict[str, Any]:
        workspace_id = str(governance_context.workspace_id)
        group_id = (
            str(governance_context.active_group_id)
            if request.scope == "active_group"
            and governance_context.active_group_id
            else None
        )
        if request.scope == "active_group" and group_id is None:
            raise ValueError("knowledge_query_active_group_required")
        context = self._context_factory.build_from_governance(
            governance_context,
            requested_workspace_id=workspace_id,
            requested_group_id=group_id,
        )
        scope_type = "group" if group_id else "workspace"
        scope_id = group_id or workspace_id
        return await self._execute_with_context(
            request,
            access_context=context,
            scope_type=scope_type,
            scope_id=scope_id,
        )

    async def execute_with_verified_access_context(
        self,
        request: KnowledgeQueryInput,
        *,
        access_context: Any,
        scope_type: str,
        scope_id: str,
    ) -> tuple[dict[str, Any], tuple[tuple[str, int], ...]]:
        """Execute the same reader and return internal cache-safe bindings."""

        if request.operation != "search":
            raise ValueError("knowledge_benchmark_search_operation_required")
        result = await self._search(
            request,
            access_context=access_context,
            scope_type=scope_type,
            scope_id=scope_id,
        )
        return (
            project_search_result(result),
            tuple(
                (
                    hit.knowledge_resource_id,
                    hit.authz_revision,
                )
                for hit in result.hits
            ),
        )

    async def _execute_with_context(
        self,
        request: KnowledgeQueryInput,
        *,
        access_context: Any,
        scope_type: str,
        scope_id: str,
    ) -> dict[str, Any]:
        if request.operation == "search":
            result = await self._search(
                request,
                access_context=access_context,
                scope_type=scope_type,
                scope_id=scope_id,
            )
            return project_search_result(result)
        if request.operation == "aggregate":
            result = await self._retrieval_facade.aggregate(
                KnowledgeAggregateRequest(
                    access_context=access_context,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    group_by=str(request.group_by),
                    measure=str(request.measure),
                    source_apps=request.resource_filters.source_apps,
                    owner_capabilities=(
                        request.resource_filters.owner_capabilities
                    ),
                    source_kinds=request.resource_filters.source_kinds,
                    record_kinds=request.resource_filters.record_kinds,
                    facet_filters=tuple(
                        FacetFilter(
                            key=predicate.key,
                            operator=predicate.operator,
                            value=predicate.value,
                        )
                        for predicate in request.facet_predicates
                    ),
                    limit=request.limit,
                )
            )
            return enforce_result_budget(
                {
                    "contract_version": "knowledge_query.v1",
                    "operation": "aggregate",
                    "evidence": [],
                    "aggregates": result["aggregates"],
                    "coverage": {
                        "candidate_group_count": result[
                            "candidate_group_count"
                        ],
                        "authorized_group_count": result[
                            "authorized_group_count"
                        ],
                    },
                    "citations": [],
                    "receipt": {
                        "authorization_receipt_digest": result[
                            "authorization_receipt_digest"
                        ],
                        "transaction_count": result["transaction_count"],
                        "evidence_is_instruction": False,
                    },
                }
            )
        if request.operation == "fetch_by_citation":
            result = await self._retrieval_facade.fetch_by_citation(
                KnowledgeCitationFetchRequest(
                    access_context=access_context,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    citations=tuple(
                        CitationLookup(
                            citation_id=citation.citation_id,
                            content_hash=citation.content_hash,
                        )
                        for citation in request.citations
                    ),
                )
            )
            return enforce_result_budget(
                {
                    "contract_version": "knowledge_query.v1",
                    "operation": "fetch_by_citation",
                    "evidence": result["evidence"],
                    "aggregates": [],
                    "coverage": {
                        "unavailable": result["unavailable"],
                    },
                    "citations": [
                        block["citation"]
                        for block in result["evidence"]
                    ],
                    "receipt": {
                        "authorization_receipt_digest": result[
                            "authorization_receipt_digest"
                        ],
                        "transaction_count": result["transaction_count"],
                        "evidence_is_instruction": False,
                    },
                }
            )
        result = await self._retrieval_facade.explain_coverage(
            KnowledgeCoverageRequest(
                access_context=access_context,
                scope_type=scope_type,
                scope_id=scope_id,
                source_apps=request.resource_filters.source_apps,
                owner_capabilities=(
                    request.resource_filters.owner_capabilities
                ),
                source_kinds=request.resource_filters.source_kinds,
                limit=request.limit,
            )
        )
        return enforce_result_budget(
            {
                "contract_version": "knowledge_query.v1",
                "operation": "explain_coverage",
                "evidence": [],
                "aggregates": [],
                "coverage": {
                    "resources": result["resources"],
                    "channels": result["channels"],
                },
                "citations": [],
                "receipt": {
                    "authorization_receipt_digest": result[
                        "authorization_receipt_digest"
                    ],
                    "transaction_count": result["transaction_count"],
                    "evidence_is_instruction": False,
                },
            }
        )

    async def _search(
        self,
        request: KnowledgeQueryInput,
        *,
        access_context: Any,
        scope_type: str,
        scope_id: str,
    ) -> KnowledgeRetrievalResult:
        bounds_for_mode(request.retrieval_mode)
        return await self._retrieval_facade.search(
            KnowledgeRetrievalRequest(
                query=str(request.query or ""),
                access_context=access_context,
                scope_type=scope_type,
                scope_id=scope_id,
                top_k=request.limit,
                source_apps=request.resource_filters.source_apps,
                owner_capabilities=(
                    request.resource_filters.owner_capabilities
                ),
                retrieval_mode=request.retrieval_mode,
                modality_filter=request.modality_filter,
                query_evidence_refs=tuple(
                    CitationLookup(
                        citation_id=citation.citation_id,
                        content_hash=citation.content_hash,
                    )
                    for citation in request.query_evidence_refs
                ),
            )
        )


__all__ = ["KnowledgeQueryService"]
