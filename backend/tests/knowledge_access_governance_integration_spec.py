"""Disposable-PostgreSQL acceptance for the Knowledge access facade."""

from __future__ import annotations

import os

import psycopg2
import pytest

from backend.app.services.authorized_knowledge_index_store import (
    AuthorizedKnowledgeIndexStore,
)
from backend.app.services.knowledge_authorization import (
    AgentExecutionMask,
    KnowledgePermission,
    PrincipalRef,
    RetrievalAccessContext,
)
from backend.app.services.knowledge_authorization.governance import (
    KnowledgeAgentMaskInput,
    KnowledgeAccessForbiddenError,
    KnowledgeAccessGrantInput,
    KnowledgeAccessReplacementCommand,
    KnowledgeAccessService,
)
from backend.app.services.knowledge_authorization.governance.agent_mask_store import (
    KnowledgeAgentMaskStore,
)
from backend.app.services.knowledge_retrieval import (
    AuthorizationAwareKnowledgeRetrievalFacade,
    KnowledgeRetrievalRequest,
)
from backend.app.services.knowledge_authorization.store import (
    KnowledgeAuthorizationConflictError,
)
from backend.app.services.knowledge_retrieval.store import (
    AuthorizationAwareKnowledgeRetrievalStore,
)


TEST_VECTOR_URL = os.getenv("TEST_VECTOR_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_VECTOR_URL,
    reason="TEST_VECTOR_DATABASE_URL is required",
)


def _connection():
    return psycopg2.connect(TEST_VECTOR_URL)


def _context(
    user_id: str,
    *,
    manage: bool,
    agent_role: str | None = None,
) -> RetrievalAccessContext:
    permissions = [
        KnowledgePermission(
            "knowledge.read",
            "workspace",
            "workspace-knowledge-access-spec",
        )
    ]
    if manage:
        permissions.extend(
            (
                KnowledgePermission(
                    "knowledge.read_all_scope",
                    "workspace",
                    "workspace-knowledge-access-spec",
                ),
                KnowledgePermission(
                    "knowledge.manage_acl",
                    "workspace",
                    "workspace-knowledge-access-spec",
                ),
                KnowledgePermission(
                    "knowledge.project",
                    "workspace",
                    "workspace-knowledge-access-spec",
                ),
            )
        )
    return RetrievalAccessContext.create(
        subject_user_id=user_id,
        tenant_id="local",
        principals=(PrincipalRef("user", user_id),),
        permissions=permissions,
        agent_mask=(
            AgentExecutionMask(
                role=agent_role,
                policy_revision="topology-policy-revision-1",
                topology_snapshot_id="topology-snapshot-1",
            )
            if agent_role
            else None
        ),
    )


def _record():
    return {
        "source_id": "knowledge-access-document:revision-1:chunk-1",
        "title": "knowledge-access.txt",
        "content": "KNOWLEDGE_ACCESS_GOVERNANCE_MARKER",
        "embedding": [1.0, 0.0],
        "metadata": {
            "workspace_id": "workspace-knowledge-access-spec",
            "document_id": "knowledge-access-document",
            "revision_id": "revision-1",
            "checksum": "a" * 64,
            "chunk_id": "chunk-1",
            "node_ids": [],
            "source_locations": [],
            "active": True,
            "embedding_model": "bge-m3",
            "pipeline_version": "knowledge-access-spec.v1",
        },
    }


class _VectorService:
    def _get_connection(self):
        return _connection()

    async def _generate_embedding_with_model(self, *_args, **_kwargs):
        return [1.0, 0.0], "bge-m3"


class _AgentMaskRevokingFinalStore:
    def __init__(
        self,
        *,
        resource_id: str,
        authz_revision: int,
        context: RetrievalAccessContext,
    ) -> None:
        self._delegate = AuthorizationAwareKnowledgeRetrievalStore(
            _connection
        )
        self._resource_id = resource_id
        self._authz_revision = authz_revision
        self._context = context
        self._changed = False

    def fetch_hybrid_candidates(self, **kwargs):
        return self._delegate.fetch_hybrid_candidates(**kwargs)

    def final_authorize(self, **kwargs):
        if not self._changed:
            connection = _connection()
            try:
                cursor = connection.cursor()
                KnowledgeAgentMaskStore.replace(
                    cursor,
                    resource_id=self._resource_id,
                    authz_revision=self._authz_revision,
                    masks=(("dispatch", "deny"),),
                    context=self._context,
                )
                connection.commit()
            finally:
                connection.close()
            self._changed = True
        return self._delegate.final_authorize(**kwargs)


@pytest.mark.asyncio
async def test_summary_detail_and_cas_replace_share_one_facade() -> None:
    written = AuthorizedKnowledgeIndexStore(
        _connection
    ).replace_trusted_document_revision(
        user_id="knowledge-access-owner",
        workspace_id="workspace-knowledge-access-spec",
        document_id="knowledge-access-document",
        revision_id="revision-1",
        records=[_record()],
    )
    context = _context("knowledge-access-owner", manage=True)
    service = KnowledgeAccessService(connection_factory=_connection)

    summary = service.list_summary(
        context=context,
        workspace_id="workspace-knowledge-access-spec",
    )
    detail = service.get_detail(
        context=context,
        workspace_id="workspace-knowledge-access-spec",
        resource_id=written.knowledge_resource_id,
    )

    assert summary["request_budget"]["polling"] is False
    assert written.knowledge_resource_id in {
        item["knowledge_resource_id"] for item in summary["items"]
    }
    assert [item["modality"] for item in detail["modality_truth"]] == [
        "text",
        "image",
        "video",
        "audio",
    ]
    assert detail["modality_truth"][0]["state"] == "active"
    assert all(
        item["state"] == "not_admitted"
        for item in detail["modality_truth"][1:]
    )

    command = KnowledgeAccessReplacementCommand(
        expected_authz_revision=written.authz_revision,
        acknowledge_complete_replacement=True,
        grants=(
            KnowledgeAccessGrantInput(
                principal_type="user",
                principal_id="knowledge-access-owner",
                relation="owner",
            ),
            KnowledgeAccessGrantInput(
                principal_type="workspace_role",
                principal_id="workspace-knowledge-access-spec:member",
                relation="reader",
            ),
        ),
        agent_masks=(
            KnowledgeAgentMaskInput(
                agent_role="dispatch",
                effect="allow",
            ),
            KnowledgeAgentMaskInput(
                agent_role="cell",
                effect="deny",
            ),
        ),
    )
    replaced = service.replace_grants(
        context=context,
        workspace_id="workspace-knowledge-access-spec",
        resource_id=written.knowledge_resource_id,
        command=command,
    )

    assert replaced["resource"]["authz_revision"] == (
        written.authz_revision + 1
    )
    assert replaced["mutation"]["follow_up_get_required"] is False
    assert replaced["mutation"]["graph_reindex_required"] is False
    assert replaced["agent_mask"]["mask_count"] == 2
    retrieval = AuthorizationAwareKnowledgeRetrievalFacade(
        vector_service=_VectorService()
    )
    dispatch_result = await retrieval.search(
        KnowledgeRetrievalRequest(
            query="KNOWLEDGE_ACCESS_GOVERNANCE_MARKER",
            access_context=_context(
                "knowledge-access-owner",
                manage=True,
                agent_role="dispatch",
            ),
            scope_type="workspace",
            scope_id="workspace-knowledge-access-spec",
        )
    )
    cell_result = await retrieval.search(
        KnowledgeRetrievalRequest(
            query="KNOWLEDGE_ACCESS_GOVERNANCE_MARKER",
            access_context=_context(
                "knowledge-access-owner",
                manage=True,
                agent_role="cell",
            ),
            scope_type="workspace",
            scope_id="workspace-knowledge-access-spec",
        )
    )
    assert {
        hit.knowledge_resource_id for hit in dispatch_result.hits
    } == {written.knowledge_resource_id}
    assert cell_result.hits == ()
    with pytest.raises(KnowledgeAuthorizationConflictError):
        service.replace_grants(
            context=context,
            workspace_id="workspace-knowledge-access-spec",
            resource_id=written.knowledge_resource_id,
            command=command,
        )


def test_read_only_member_cannot_open_acl_governance() -> None:
    service = KnowledgeAccessService(connection_factory=_connection)

    with pytest.raises(KnowledgeAccessForbiddenError):
        service.list_summary(
            context=_context("knowledge-access-member", manage=False),
            workspace_id="workspace-knowledge-access-spec",
        )


@pytest.mark.asyncio
async def test_agent_mask_changed_after_ranking_is_dropped_by_final_check() -> None:
    written = AuthorizedKnowledgeIndexStore(
        _connection
    ).replace_trusted_document_revision(
        user_id="knowledge-agent-race-owner",
        workspace_id="workspace-knowledge-access-spec",
        document_id="knowledge-agent-race-document",
        revision_id="revision-1",
        records=[
            {
                **_record(),
                "source_id": (
                    "knowledge-agent-race-document:"
                    "revision-1:chunk-1"
                ),
                "content": "KNOWLEDGE_AGENT_RACE_MARKER",
                "metadata": {
                    **_record()["metadata"],
                    "document_id": "knowledge-agent-race-document",
                },
            }
        ],
    )
    owner = _context(
        "knowledge-agent-race-owner",
        manage=True,
        agent_role="dispatch",
    )
    connection = _connection()
    try:
        cursor = connection.cursor()
        KnowledgeAgentMaskStore.replace(
            cursor,
            resource_id=written.knowledge_resource_id,
            authz_revision=written.authz_revision,
            masks=(("dispatch", "allow"),),
            context=owner,
        )
        connection.commit()
    finally:
        connection.close()
    retrieval = AuthorizationAwareKnowledgeRetrievalFacade(
        vector_service=_VectorService(),
        store=_AgentMaskRevokingFinalStore(
            resource_id=written.knowledge_resource_id,
            authz_revision=written.authz_revision,
            context=owner,
        ),
    )

    result = await retrieval.search(
        KnowledgeRetrievalRequest(
            query="KNOWLEDGE_AGENT_RACE_MARKER",
            access_context=owner,
            scope_type="workspace",
            scope_id="workspace-knowledge-access-spec",
        )
    )

    assert written.knowledge_resource_id not in {
        hit.knowledge_resource_id for hit in result.hits
    }
