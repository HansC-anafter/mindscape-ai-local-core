"""Aggregate, citation, and coverage operations behind the retrieval facade."""

from __future__ import annotations

import asyncio
from typing import Any

from .contracts import (
    KnowledgeAggregateRequest,
    KnowledgeCitationFetchRequest,
    KnowledgeCoverageRequest,
)
from .filter_compiler import compile_facet_filters


class AuthorizationAwareKnowledgeOperationsMixin:
    async def aggregate(
        self,
        request: KnowledgeAggregateRequest,
    ) -> dict[str, Any]:
        self._authorization_service.admit_read(
            access_context=request.access_context,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
        )
        rows = await asyncio.to_thread(
            self._operation_store.fetch_aggregate_rows,
            context=request.access_context,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            source_apps=request.source_apps,
            owner_capabilities=request.owner_capabilities,
            source_kinds=request.source_kinds,
            record_kinds=request.record_kinds,
            group_by=request.group_by,
            measure=request.measure,
            facet_filters=compile_facet_filters(
                request.facet_filters,
                record_alias="record",
            ),
        )
        final = await self._final_authorize_rows(
            context=request.access_context,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            rows=rows,
        )
        groups: dict[tuple[str, str], int] = {}
        for row in rows:
            if not self._row_is_final_authorized(row, final):
                continue
            key = (str(row["facet_type"]), str(row["group_value"]))
            groups[key] = groups.get(key, 0) + int(row["measured_value"])
        aggregates = [
            {
                "facet_type": key[0],
                "group_value": key[1],
                "measure": request.measure,
                "value": value,
            }
            for key, value in sorted(
                groups.items(),
                key=lambda item: (-item[1], item[0]),
            )[: request.limit]
        ]
        return {
            "operation": "aggregate",
            "aggregates": aggregates,
            "candidate_group_count": len(rows),
            "authorized_group_count": len(aggregates),
            "authorization_receipt_digest": self._operation_receipt(
                request.access_context.principal_set_hash,
                request.scope_type,
                request.scope_id,
                rows,
                final,
            ),
            "transaction_count": 2 if rows else 1,
        }

    async def fetch_by_citation(
        self,
        request: KnowledgeCitationFetchRequest,
    ) -> dict[str, Any]:
        self._authorization_service.admit_read(
            access_context=request.access_context,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
        )
        expected = {
            citation.citation_id: citation.content_hash
            for citation in request.citations
        }
        rows = await asyncio.to_thread(
            self._operation_store.fetch_citation_rows,
            context=request.access_context,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            citation_ids=tuple(expected),
        )
        exact_rows = [
            row
            for row in rows
            if expected.get(str(row["citation_id"]))
            == str(row["content_hash"])
        ]
        final = await self._final_authorize_rows(
            context=request.access_context,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            rows=exact_rows,
        )
        fetched: list[dict[str, Any]] = []
        fetched_ids: set[str] = set()
        for row in exact_rows:
            if not self._row_is_final_authorized(row, final):
                continue
            citation_id = str(row["citation_id"])
            fetched_ids.add(citation_id)
            fetched.append(
                {
                    "kind": (
                        "text_excerpt"
                        if str(row.get("content") or "")
                        else "owner_pointer"
                    ),
                    "trust": "untrusted_evidence",
                    "content": str(row.get("content") or "")[:32768],
                    "metadata": dict(row.get("metadata") or {}),
                    "citation": {
                        "citation_id": citation_id,
                        "content_hash": str(row["content_hash"]),
                        "knowledge_resource_id": str(
                            row["knowledge_resource_id"]
                        ),
                        "security_label_id": str(
                            row["security_label_id"]
                        ),
                        "projection_revision_id": str(
                            row["projection_revision_id"]
                        ),
                        "source_ref": str(row.get("source_ref") or ""),
                    },
                }
            )
        return {
            "operation": "fetch_by_citation",
            "evidence": fetched,
            "unavailable": [
                {
                    "citation_id": citation.citation_id,
                    "reason": "unavailable_or_stale",
                }
                for citation in request.citations
                if citation.citation_id not in fetched_ids
            ],
            "authorization_receipt_digest": self._operation_receipt(
                request.access_context.principal_set_hash,
                request.scope_type,
                request.scope_id,
                exact_rows,
                final,
            ),
            "transaction_count": 2 if rows else 1,
        }

    async def explain_coverage(
        self,
        request: KnowledgeCoverageRequest,
    ) -> dict[str, Any]:
        self._authorization_service.admit_read(
            access_context=request.access_context,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
        )
        rows = await asyncio.to_thread(
            self._operation_store.fetch_coverage_rows,
            context=request.access_context,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            source_apps=request.source_apps,
            owner_capabilities=request.owner_capabilities,
            source_kinds=request.source_kinds,
        )
        final = await self._final_authorize_rows(
            context=request.access_context,
            scope_type=request.scope_type,
            scope_id=request.scope_id,
            rows=rows,
        )
        authorized = [
            row
            for row in rows
            if self._row_is_final_authorized(row, final)
        ]
        resources: dict[tuple[str, str, str], set[str]] = {}
        channels: dict[tuple[str, str, str], set[str]] = {}
        for row in authorized:
            resource_key = (
                str(row["source_app"]),
                str(row["source_kind"]),
                str(row["projection_status"]),
            )
            resources.setdefault(resource_key, set()).add(
                str(row["knowledge_resource_id"])
            )
            if row.get("channel_id"):
                channel_key = (
                    str(row["modality"]),
                    str(row["channel_state"]),
                    str(row.get("channel_reason") or ""),
                )
                channels.setdefault(channel_key, set()).add(
                    str(row["knowledge_resource_id"])
                )
        return {
            "operation": "explain_coverage",
            "resources": [
                {
                    "source_app": key[0],
                    "source_kind": key[1],
                    "projection_status": key[2],
                    "authorized_resource_count": len(value),
                }
                for key, value in sorted(resources.items())
            ][: request.limit],
            "channels": [
                {
                    "modality": key[0],
                    "state": key[1],
                    "reason": key[2] or None,
                    "authorized_resource_count": len(value),
                }
                for key, value in sorted(channels.items())
            ][: request.limit],
            "authorization_receipt_digest": self._operation_receipt(
                request.access_context.principal_set_hash,
                request.scope_type,
                request.scope_id,
                rows,
                final,
            ),
            "transaction_count": 2 if rows else 1,
        }


__all__ = ["AuthorizationAwareKnowledgeOperationsMixin"]
