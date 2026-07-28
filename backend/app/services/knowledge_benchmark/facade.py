"""Single explicit benchmark facade over the canonical knowledge reader."""

from __future__ import annotations

import asyncio
from time import perf_counter
from typing import Any

from backend.app.services.knowledge_authorization import (
    RetrievalAccessContext,
)
from backend.app.services.knowledge_retrieval.store import (
    AuthorizationAwareKnowledgeRetrievalStore,
)
from backend.app.services.tools.knowledge_query.contracts import (
    KnowledgeQueryInput,
)
from backend.app.services.tools.knowledge_query.query_service import (
    KnowledgeQueryService,
)
from backend.app.services.vector_search import VectorSearchService

from .contracts import (
    BenchmarkCatalogCommand,
    BenchmarkExecutionCommand,
)
from .store import KnowledgeBenchmarkStore
from .store_common import sha256_json


class KnowledgeBenchmarkFacade:
    """Catalog, execute, cache, and receipt without a second retrieval path."""

    def __init__(
        self,
        *,
        store: KnowledgeBenchmarkStore | None = None,
        query_service: KnowledgeQueryService | None = None,
        final_authorization_store: (
            AuthorizationAwareKnowledgeRetrievalStore | None
        ) = None,
    ) -> None:
        vector_service = (
            VectorSearchService()
            if store is None or final_authorization_store is None
            else None
        )
        self._store = store or KnowledgeBenchmarkStore(vector_service)
        self._query_service = query_service or KnowledgeQueryService()
        if final_authorization_store is None:
            assert vector_service is not None
        self._final_store = (
            final_authorization_store
            or AuthorizationAwareKnowledgeRetrievalStore(
                vector_service._get_connection
            )
        )

    async def register_catalog(
        self,
        command: BenchmarkCatalogCommand,
        *,
        access_context: RetrievalAccessContext,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._store.register_catalog,
            context=access_context,
            command=command,
        )

    async def execute(
        self,
        command: BenchmarkExecutionCommand,
        *,
        access_context: RetrievalAccessContext,
    ) -> dict[str, Any]:
        started = perf_counter()
        topology_revision = self._topology_revision(
            access_context,
            command.group_id,
        )
        authorization_generation = sha256_json(
            access_context.as_dict()
        )
        seed = await asyncio.to_thread(
            self._store.load_execution_seed,
            context=access_context,
            group_id=command.group_id,
            catalog_id=command.catalog_id,
            catalog_revision=command.catalog_revision,
            question_id=command.question_id,
            topology_revision=topology_revision,
            authorization_generation=authorization_generation,
        )
        cached = seed.get("cached")
        if cached is not None:
            bindings = tuple(
                (
                    str(item["knowledge_resource_id"]),
                    int(item["authz_revision"]),
                )
                for item in tuple(cached.get("resource_bindings") or ())
            )
            final = await asyncio.to_thread(
                self._final_store.final_authorize,
                context=access_context,
                scope_type="group",
                scope_id=command.group_id,
                expected_bindings=bindings,
            )
            if all(
                final.get(resource_id) == revision
                for resource_id, revision in bindings
            ):
                latency_ms = self._elapsed_ms(started)
                await asyncio.to_thread(
                    self._store.record_cache_hit,
                    context=access_context,
                    seed=seed,
                    latency_ms=latency_ms,
                )
                return self._response(
                    seed=seed,
                    cache_status="hit",
                    payload=dict(cached["response_payload"]),
                )
            await asyncio.to_thread(
                self._store.record_stale_authorization,
                context=access_context,
                seed=seed,
                latency_ms=self._elapsed_ms(started),
            )

        query = KnowledgeQueryInput.model_validate(
            seed["question"]["canonical_request"]
        )
        payload, bindings = (
            await self._query_service.execute_with_verified_access_context(
                query,
                access_context=access_context,
                scope_type="group",
                scope_id=command.group_id,
            )
        )
        latency_ms = self._elapsed_ms(started)
        await asyncio.to_thread(
            self._store.store_miss,
            context=access_context,
            seed=seed,
            topology_revision=topology_revision,
            authorization_generation=authorization_generation,
            response_payload=payload,
            bindings=bindings,
            latency_ms=latency_ms,
        )
        return self._response(
            seed=seed,
            cache_status=(
                "stale_authorization" if cached is not None else "miss"
            ),
            payload=payload,
        )

    async def stats(
        self,
        *,
        access_context: RetrievalAccessContext,
        group_id: str,
        catalog_id: str,
        catalog_revision: str,
        limit: int,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._store.stats,
            context=access_context,
            group_id=group_id,
            catalog_id=catalog_id,
            catalog_revision=catalog_revision,
            limit=limit,
        )

    @staticmethod
    def _topology_revision(
        context: RetrievalAccessContext,
        group_id: str,
    ) -> str:
        revision = next(
            (
                membership.revision
                for membership in context.memberships
                if membership.scope_type == "group"
                and membership.scope_id == group_id
            ),
            "",
        )
        if not revision:
            raise PermissionError(
                "knowledge_benchmark_group_membership_required"
            )
        return revision

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, int((perf_counter() - started) * 1000))

    @staticmethod
    def _response(
        *,
        seed: dict[str, Any],
        cache_status: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        question = seed["question"]
        return {
            "contract_version": "knowledge_benchmark.v1",
            "cache_status": cache_status,
            "cache_key": seed["cache_key"],
            "projection_digest": seed["projection_digest"],
            "retrieval_revision": seed["retrieval_revision"],
            "question": {
                "question_id": question["question_id"],
                "domain_id": question["domain_id"],
                "tier": question["tier"],
                "benchmark_class": question["benchmark_class"],
                "question_text": question["question_text"],
            },
            "result": payload,
        }


__all__ = ["KnowledgeBenchmarkFacade"]
