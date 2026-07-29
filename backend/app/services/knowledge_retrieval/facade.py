"""One authorization-aware reader for all knowledge callers."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any, Optional

from backend.app.services.knowledge_projection.retrievable.text_compatibility import (
    fit_external_docs_embedding,
)
from backend.app.services.knowledge_authorization import (
    KnowledgeAuthorizationService,
)
from backend.app.services.vector_search import VectorSearchService

from .contracts import KnowledgeRetrievalRequest, KnowledgeRetrievalResult
from .facade_helpers import (
    AuthorizationAwareKnowledgeRetrievalHelpersMixin,
)
from .facade_operations import AuthorizationAwareKnowledgeOperationsMixin
from .operations_store import AuthorizationAwareKnowledgeOperationStore
from .store import AuthorizationAwareKnowledgeRetrievalStore


RRF_K = 60


class AuthorizationAwareKnowledgeRetrievalFacade(
    AuthorizationAwareKnowledgeOperationsMixin,
    AuthorizationAwareKnowledgeRetrievalHelpersMixin,
):
    """Prefilter, rank, and final-check without per-hit database queries."""

    def __init__(
        self,
        *,
        vector_service: Optional[VectorSearchService] = None,
        store: Optional[AuthorizationAwareKnowledgeRetrievalStore] = None,
        authorization_service: Optional[
            KnowledgeAuthorizationService
        ] = None,
        operation_store: Optional[
            AuthorizationAwareKnowledgeOperationStore
        ] = None,
    ) -> None:
        self._vector_service = vector_service or VectorSearchService()
        self._store = store or AuthorizationAwareKnowledgeRetrievalStore(
            self._vector_service._get_connection
        )
        self._authorization_service = (
            authorization_service or KnowledgeAuthorizationService()
        )
        self._operation_store = (
            operation_store
            or AuthorizationAwareKnowledgeOperationStore(
                self._vector_service._get_connection
            )
        )

    async def search(
        self,
        request: KnowledgeRetrievalRequest,
    ) -> KnowledgeRetrievalResult:
        if request.retrieval_mode != "hybrid":
            from backend.app.services.knowledge_graph.query_service import (
                AuthorizationAwareKnowledgeGraphQueryService,
            )
            from backend.app.services.knowledge_graph.query_store import (
                AuthorizationAwareKnowledgeGraphQueryStore,
            )

            return await AuthorizationAwareKnowledgeGraphQueryService(
                store=AuthorizationAwareKnowledgeGraphQueryStore(
                    self._vector_service._get_connection
                ),
                final_authorization_store=self._store,
                authorization_service=self._authorization_service,
            ).search(request)
        self._authorization_service.admit_read(
            access_context=request.access_context,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
        )
        if request.query_evidence_refs:
            embedding, model_name = None, None
        else:
            try:
                embedding, model_name = (
                    await self._vector_service._generate_embedding_with_model(
                        request.query,
                        is_query=True,
                    )
                )
            except Exception:
                embedding, model_name = None, None
        fitted = fit_external_docs_embedding(embedding) if embedding else None
        candidate_limit = min(60, request.top_k * 3)
        vector_rows, keyword_rows, seed_bindings = await asyncio.to_thread(
            self._store.fetch_hybrid_candidates,
            query=request.query,
            query_embedding=fitted,
            model_name=model_name,
            context=request.access_context,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            source_apps=request.source_apps,
            owner_capabilities=request.owner_capabilities,
            modality_filter=request.modality_filter,
            candidate_limit=candidate_limit,
            query_evidence_refs=request.query_evidence_refs,
        )
        ranked: dict[str, dict[str, Any]] = {}
        for channel, rows in (
            ("text_vector", vector_rows),
            ("keyword", keyword_rows),
        ):
            for rank, row in enumerate(rows, start=1):
                identity = str(row["id"])
                entry = ranked.setdefault(
                    identity,
                    {"row": row, "score": 0.0, "channels": []},
                )
                entry["score"] += 1.0 / (RRF_K + rank)
                if channel not in entry["channels"]:
                    entry["channels"].append(channel)

        selected = sorted(
            ranked.values(),
            key=lambda item: (-float(item["score"]), str(item["row"]["id"])),
        )[: request.top_k]
        selected_bindings = tuple(
            (
                str(item["row"]["knowledge_resource_id"]),
                int(item["row"]["authz_revision"]),
            )
            for item in selected
        )
        final = await asyncio.to_thread(
            self._store.final_authorize,
            context=request.access_context,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            expected_bindings=selected_bindings + seed_bindings,
        )
        seed_is_final = all(
            final.get(resource_id) == revision
            for resource_id, revision in seed_bindings
        )
        hits = tuple(
            self._build_hit(
                item["row"],
                score=float(item["score"]),
                channels=tuple(item["channels"]),
            )
            for item in selected
            if seed_is_final
            and final.get(str(item["row"]["knowledge_resource_id"]))
            == int(item["row"]["authz_revision"])
        )
        receipt = hashlib.sha256(
            json.dumps(
                {
                    "principal_set_hash": request.access_context.principal_set_hash,
                    "scope_type": request.scope_type,
                    "scope_id": request.scope_id,
                    "bindings": [
                        [hit.knowledge_resource_id, hit.authz_revision]
                        for hit in hits
                    ],
                    "query_seed_bindings": list(seed_bindings),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        degraded: list[str] = []
        if not vector_rows:
            degraded.append("text_vector_unavailable_or_empty")
        if not keyword_rows:
            degraded.append("keyword_empty")
        if request.query_evidence_refs:
            degraded.append(
                "query_evidence_vector_channel_not_admitted"
            )
        if not seed_is_final:
            degraded.append(
                "query_evidence_revoked_before_final_authorization"
            )
        return KnowledgeRetrievalResult(
            hits=hits,
            requested_mode=request.retrieval_mode,
            executed_mode="hybrid",
            candidate_count=len(ranked),
            final_authorized_count=len(hits),
            transaction_count=2 if ranked or seed_bindings else 1,
            degraded_reasons=tuple(degraded),
            authorization_receipt_digest=receipt,
            fusion_revision="rrf.k60.lexical-prefix.v2",
            channel_coverage={
                "text_vector_candidates": len(vector_rows),
                "keyword_candidates": len(keyword_rows),
                "query_evidence_seed_count": len(seed_bindings),
                "requested_modality": request.modality_filter,
            },
        )

__all__ = ["AuthorizationAwareKnowledgeRetrievalFacade", "RRF_K"]
