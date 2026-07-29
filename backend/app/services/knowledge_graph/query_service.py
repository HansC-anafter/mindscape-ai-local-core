"""Bounded graph retrieval over authorization-prefiltered candidates."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from backend.app.services.knowledge_authorization import (
    KnowledgeAuthorizationService,
)
from backend.app.services.knowledge_retrieval.contracts import (
    AuthorizedKnowledgeHit,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResult,
)
from backend.app.services.knowledge_retrieval.store import (
    AuthorizationAwareKnowledgeRetrievalStore,
)

from .query_store import AuthorizationAwareKnowledgeGraphQueryStore


class AuthorizationAwareKnowledgeGraphQueryService:
    """Execute one explicit graph mode; never extract, summarize, or call an LLM."""

    def __init__(
        self,
        *,
        store: AuthorizationAwareKnowledgeGraphQueryStore,
        final_authorization_store: AuthorizationAwareKnowledgeRetrievalStore,
        authorization_service: KnowledgeAuthorizationService | None = None,
    ) -> None:
        self._store = store
        self._final_store = final_authorization_store
        self._authorization_service = (
            authorization_service or KnowledgeAuthorizationService()
        )

    async def search(
        self,
        request: KnowledgeRetrievalRequest,
    ) -> KnowledgeRetrievalResult:
        self._authorization_service.admit_read(
            access_context=request.access_context,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
        )
        if request.retrieval_mode == "global_graph":
            rows, query_seed_bindings = await asyncio.to_thread(
                self._store.fetch_global_candidates,
                query=request.query,
                context=request.access_context,
                scope_type=request.scope_type,
                scope_id=request.scope_id,
                source_apps=request.source_apps,
                source_ids=request.source_ids,
                owner_capabilities=request.owner_capabilities,
                modality_filter=request.modality_filter,
                candidate_limit=min(40, request.top_k * 2),
                query_evidence_refs=request.query_evidence_refs,
            )
            metrics = {
                "seed_count": 0,
                "visited_nodes": 0,
                "visited_edges": 0,
            }
        else:
            if request.retrieval_mode == "local_graph":
                max_hops, max_nodes, max_edges = 2, 200, 400
            elif request.retrieval_mode == "multi_hop":
                max_hops, max_nodes, max_edges = 3, 400, 800
            else:
                raise ValueError("knowledge_graph_retrieval_mode_forbidden")
            rows, metrics, query_seed_bindings = await asyncio.to_thread(
                self._store.fetch_neighborhood_candidates,
                query=request.query,
                context=request.access_context,
                scope_type=request.scope_type,
                scope_id=request.scope_id,
                source_apps=request.source_apps,
                source_ids=request.source_ids,
                owner_capabilities=request.owner_capabilities,
                modality_filter=request.modality_filter,
                max_hops=max_hops,
                max_nodes=max_nodes,
                max_edges=max_edges,
                result_limit=request.top_k,
                query_evidence_refs=request.query_evidence_refs,
            )
        selected = rows[: request.top_k]
        selected_bindings = tuple(
            (
                str(row["knowledge_resource_id"]),
                int(row["authz_revision"]),
            )
            for row in selected
        )
        final = await asyncio.to_thread(
            self._final_store.final_authorize,
            context=request.access_context,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            expected_bindings=selected_bindings + query_seed_bindings,
        )
        query_seed_is_final = all(
            final.get(resource_id) == revision
            for resource_id, revision in query_seed_bindings
        )
        authorized_rows = [
            row
            for row in selected
            if query_seed_is_final
            and final.get(str(row["knowledge_resource_id"]))
            == int(row["authz_revision"])
        ]
        hits = tuple(
            self._global_hit(row)
            if request.retrieval_mode == "global_graph"
            else self._neighborhood_hit(row)
            for row in authorized_rows
        )
        receipt = hashlib.sha256(
            json.dumps(
                {
                    "principal_set_hash": (
                        request.access_context.principal_set_hash
                    ),
                    "scope": [request.scope_type, request.scope_id],
                    "mode": request.retrieval_mode,
                    "bindings": [
                        [hit.knowledge_resource_id, hit.authz_revision]
                        for hit in hits
                    ],
                    "metrics": metrics,
                    "query_seed_bindings": list(
                        query_seed_bindings
                    ),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        degraded = ()
        if not rows:
            degraded = ("authorized_graph_candidates_empty",)
        if not query_seed_is_final:
            degraded = (
                *degraded,
                "query_evidence_revoked_before_final_authorization",
            )
        return KnowledgeRetrievalResult(
            hits=hits,
            requested_mode=request.retrieval_mode,
            executed_mode=request.retrieval_mode,
            candidate_count=len(rows),
            final_authorized_count=len(hits),
            transaction_count=(
                2 if rows or query_seed_bindings else 1
            ),
            degraded_reasons=degraded,
            authorization_receipt_digest=receipt,
            graph_metrics=metrics,
            fusion_revision=(
                "community_report_rank.v1"
                if request.retrieval_mode == "global_graph"
                else "graph_neighborhood_confidence_depth.v1"
            ),
            channel_coverage={
                "graph_candidates": len(rows),
                "query_evidence_seed_count": len(
                    query_seed_bindings
                ),
                "requested_modality": request.modality_filter,
                "applied_source_ids": list(request.source_ids),
            },
        )

    @staticmethod
    def _neighborhood_hit(row: dict[str, Any]) -> AuthorizedKnowledgeHit:
        citation = dict(row.get("citation") or {})
        if row.get("external_doc_id"):
            citation_id = f"external_doc:{row['external_doc_id']}"
        elif row.get("projection_record_id"):
            citation_id = (
                f"projection_record:{row['projection_record_id']}"
            )
        else:
            citation_id = f"graph_mention:{row['mention_id']}"
        citation.update(
            {
                "citation_id": citation_id,
                "knowledge_resource_id": str(
                    row["knowledge_resource_id"]
                ),
                "security_label_id": str(row["security_label_id"]),
                "projection_revision_id": str(
                    row["projection_revision_id"]
                ),
                "source_ref": str(row.get("source_ref") or ""),
                "content_hash": (
                    hashlib.sha256(
                        str(row.get("document_content") or "").encode("utf-8")
                    ).hexdigest()
                    if row.get("external_doc_id")
                    else (
                        str(row["record_content_hash"])
                        if row.get("projection_record_id")
                        else hashlib.sha256(
                            str(row.get("surface_text") or "").encode("utf-8")
                        ).hexdigest()
                    )
                ),
            }
        )
        metadata = dict(row.get("document_metadata") or {})
        metadata.update(
            {
                "unit_key": row.get("unit_key"),
                "unit_kind": row.get("unit_kind"),
                "owner_asset_ref": row.get("owner_asset_ref"),
                "media_type": row.get("media_type"),
                "anchor": row.get("anchor") or {},
                "record_values": row.get("record_values") or {},
                "graph_depth": int(row.get("graph_depth") or 0),
                "graph_relation_ids": list(
                    row.get("graph_relation_ids") or []
                ),
            }
        )
        score = float(row.get("confidence") or 0.0) / (
            1.0 + float(row.get("graph_depth") or 0)
        )
        return AuthorizedKnowledgeHit(
            knowledge_resource_id=str(row["knowledge_resource_id"]),
            security_label_id=str(row["security_label_id"]),
            authz_revision=int(row["authz_revision"]),
            projection_revision_id=str(row["projection_revision_id"]),
            source_app=str(row["source_app"]),
            source_id=str(row["source_id"]),
            content=str(
                row.get("document_content")
                or row.get("record_text")
                or row.get("surface_text")
                or ""
            ),
            metadata=metadata,
            score=max(0.0, score),
            channels=("graph_neighborhood",),
            citation=citation,
        )

    @staticmethod
    def _global_hit(row: dict[str, Any]) -> AuthorizedKnowledgeHit:
        report_id = str(row["community_report_id"])
        citation = {
            "citation_id": f"community_report:{report_id}",
            "knowledge_resource_id": str(row["knowledge_resource_id"]),
            "security_label_id": str(row["security_label_id"]),
            "projection_revision_id": str(
                row["projection_revision_id"]
            ),
            "source_ref": str(row.get("source_ref") or ""),
            "supporting_citations": list(
                row.get("supporting_citations") or []
            ),
            "content_hash": hashlib.sha256(
                str(row.get("summary") or "").encode("utf-8")
            ).hexdigest(),
        }
        return AuthorizedKnowledgeHit(
            knowledge_resource_id=str(row["knowledge_resource_id"]),
            security_label_id=str(row["security_label_id"]),
            authz_revision=int(row["authz_revision"]),
            projection_revision_id=str(row["projection_revision_id"]),
            source_app=str(row["source_app"]),
            source_id=str(row["source_id"]),
            content=str(row.get("summary") or ""),
            metadata={
                "community_id": str(row["community_id"]),
                "community_level": int(row["level"]),
                "findings": list(row.get("findings") or []),
            },
            score=max(
                0.0,
                float(row.get("keyword_score") or 0.0)
                + float(row.get("rank") or 0.0),
            ),
            channels=("graph_community_report",),
            citation=citation,
        )


__all__ = ["AuthorizationAwareKnowledgeGraphQueryService"]
