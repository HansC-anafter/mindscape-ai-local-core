"""A cache row is a hit only after exact final authorization."""

from __future__ import annotations

import pytest

from backend.app.services.knowledge_authorization import (
    KnowledgePermission,
    PrincipalRef,
    RetrievalAccessContext,
    ScopeMembership,
)
from backend.app.services.knowledge_benchmark.contracts import (
    BenchmarkExecutionCommand,
)
from backend.app.services.knowledge_benchmark.facade import (
    KnowledgeBenchmarkFacade,
)


def _context() -> RetrievalAccessContext:
    return RetrievalAccessContext.create(
        subject_user_id="owner",
        tenant_id="local",
        principals=(PrincipalRef("user", "owner"),),
        memberships=(
            ScopeMembership("group", "wg_health", "owner", "revision-1"),
        ),
        permissions=(
            KnowledgePermission("knowledge.read", "group", "wg_health"),
            KnowledgePermission("knowledge.project", "group", "wg_health"),
        ),
    )


def _seed():
    return {
        "cache_key": "c" * 64,
        "projection_digest": "p" * 64,
        "retrieval_revision": "knowledge-retrieval.cjk-graph-seed.v3",
        "request_digest": "r" * 64,
        "question": {
            "question_row_id": "kbq_1",
            "question_id": "hwg.sleep.q01",
            "domain_id": "sleep",
            "tier": "quick",
            "benchmark_class": "data_local",
            "question_text": "睡眠是否重要？",
            "owner_scope_id": "wg_health",
            "canonical_request": {
                "operation": "search",
                "query": "睡眠",
                "retrieval_mode": "hybrid",
                "scope": "active_group",
            },
        },
        "cached": {
            "response_payload": {
                "evidence": [{"content": "cached"}],
                "receipt": {
                    "authorization_receipt_digest": "receipt"
                },
            },
            "resource_bindings": [
                {
                    "knowledge_resource_id": "resource-1",
                    "authz_revision": 7,
                }
            ],
        },
    }


class _Store:
    def __init__(self):
        self.hit = 0
        self.stale = 0
        self.miss = 0

    def load_execution_seed(self, **_kwargs):
        return _seed()

    def record_cache_hit(self, **_kwargs):
        self.hit += 1

    def record_stale_authorization(self, **_kwargs):
        self.stale += 1

    def store_miss(self, **_kwargs):
        self.miss += 1


class _FinalStore:
    def __init__(self, authorized: bool):
        self.authorized = authorized

    def final_authorize(self, **_kwargs):
        return {"resource-1": 7} if self.authorized else {}


class _Query:
    def __init__(self):
        self.calls = 0

    async def execute_with_verified_access_context(self, *_args, **_kwargs):
        self.calls += 1
        return (
            {
                "evidence": [{"content": "fresh"}],
                "receipt": {
                    "authorization_receipt_digest": "fresh-receipt"
                },
            },
            (("resource-2", 8),),
        )


def _command() -> BenchmarkExecutionCommand:
    return BenchmarkExecutionCommand(
        workspace_id="workspace-dispatch",
        group_id="wg_health",
        catalog_id="health.frontier.v1",
        catalog_revision="2026-07-27",
        question_id="hwg.sleep.q01",
    )


@pytest.mark.asyncio
async def test_cache_hit_requires_exact_final_binding() -> None:
    store = _Store()
    query = _Query()
    facade = KnowledgeBenchmarkFacade(
        store=store,
        query_service=query,
        final_authorization_store=_FinalStore(True),
    )

    result = await facade.execute(_command(), access_context=_context())

    assert result["cache_status"] == "hit"
    assert result["retrieval_revision"] == (
        "knowledge-retrieval.cjk-graph-seed.v3"
    )
    assert result["result"]["evidence"][0]["content"] == "cached"
    assert store.hit == 1
    assert query.calls == 0


@pytest.mark.asyncio
async def test_revoked_cache_binding_executes_canonical_reader() -> None:
    store = _Store()
    query = _Query()
    facade = KnowledgeBenchmarkFacade(
        store=store,
        query_service=query,
        final_authorization_store=_FinalStore(False),
    )

    result = await facade.execute(_command(), access_context=_context())

    assert result["cache_status"] == "stale_authorization"
    assert result["result"]["evidence"][0]["content"] == "fresh"
    assert store.stale == 1
    assert store.miss == 1
    assert query.calls == 1
