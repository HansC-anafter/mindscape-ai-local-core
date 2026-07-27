"""Projection action facade keeps revision checks and the existing task lane."""

from __future__ import annotations

import pytest

from backend.app.services.knowledge_authorization import (
    KnowledgePermission,
    PrincipalRef,
    RetrievalAccessContext,
)
from backend.app.services.knowledge_authorization.governance import (
    KnowledgeAccessService,
    KnowledgeProjectionActionCommand,
)
from backend.app.services.knowledge_authorization.store import (
    KnowledgeAuthorizationConflictError,
)
from backend.app.services.knowledge_projection.retrievable.source_admission import (
    RetrievableSourceAdmissionCommand,
    RetrievableSourceAdmissionReceipt,
)


def _context() -> RetrievalAccessContext:
    return RetrievalAccessContext.create(
        subject_user_id="owner-1",
        tenant_id="local",
        principals=(PrincipalRef("user", "owner-1"),),
        permissions=(
            KnowledgePermission(
                "knowledge.manage_acl",
                "workspace",
                "workspace-1",
            ),
            KnowledgePermission(
                "knowledge.project",
                "workspace",
                "workspace-1",
            ),
        ),
    )


class _AccessRepository:
    def __init__(self, *, active: bool = True) -> None:
        self.active = active

    def get_detail(self, **_kwargs):
        return {
            "resource": {
                "knowledge_resource_id": "resource-1",
                "authz_revision": 3,
                "source_revision": "revision-1",
                "source_id": "object-1",
                "owner_capability_code": "synthetic_pack",
                "source_kind": "object",
                "source_ref": "object:object-1",
                "active": self.active,
            }
        }


class _SourceRepository:
    def __init__(self) -> None:
        self.trigger_mode = None

    def resolve(self, **kwargs):
        self.trigger_mode = kwargs["trigger_mode"]
        return RetrievableSourceAdmissionCommand(
            capability_code="synthetic_pack",
            capability_version="1.0.0",
            descriptor_id="synthetic_objects",
            descriptor_hash="a" * 64,
            manifest_hash="b" * 64,
            source_kind="object",
            source_instance_id="object-1",
            source_ref="object:object-1",
            source_revision="revision-1",
            content_hash="c" * 64,
            evidence_type="aol_object_revision",
            evidence_id="evidence-1",
            workspace_id="workspace-1",
            object_kind="synthetic_object",
            trigger_mode=kwargs["trigger_mode"],
            auto_triggered=False,
        )


class _ProjectionFacade:
    def __init__(self) -> None:
        self.command = None

    def admit_retrievable_source(self, command, **_kwargs):
        self.command = command
        return RetrievableSourceAdmissionReceipt(
            state="admitted",
            intake_id="intake-1",
            task_id="task-1",
            intake_created=True,
            task_created=True,
            queue_shard="knowledge_indexing",
        )


def _service(*, active: bool = True):
    source_repository = _SourceRepository()
    projection_facade = _ProjectionFacade()
    service = KnowledgeAccessService(
        repository=_AccessRepository(active=active),
        projection_action_source_repository=source_repository,
        projection_facade=projection_facade,
        connection_factory=lambda: None,
    )
    return service, source_repository, projection_facade


@pytest.mark.parametrize(
    ("action", "active", "trigger_mode"),
    (
        ("reindex", True, "explicit_reindex"),
        ("retry", True, "explicit_reindex"),
        ("revoke", True, "revoke"),
        ("restore", False, "explicit_reindex"),
    ),
)
def test_action_maps_to_existing_admission_lane(
    action: str,
    active: bool,
    trigger_mode: str,
) -> None:
    service, source_repository, projection_facade = _service(
        active=active
    )
    receipt = service.run_projection_action(
        context=_context(),
        workspace_id="workspace-1",
        resource_id="resource-1",
        command=KnowledgeProjectionActionCommand(
            action=action,
            expected_authz_revision=3,
            expected_source_revision="revision-1",
        ),
    )

    assert source_repository.trigger_mode == trigger_mode
    assert projection_facade.command.trigger_mode == trigger_mode
    assert receipt["admission"]["task_id"] == "task-1"
    assert receipt["request_budget"]["follow_up_get_required"] is False


def test_action_rejects_stale_revision_before_admission() -> None:
    service, source_repository, projection_facade = _service()

    with pytest.raises(KnowledgeAuthorizationConflictError):
        service.run_projection_action(
            context=_context(),
            workspace_id="workspace-1",
            resource_id="resource-1",
            command=KnowledgeProjectionActionCommand(
                action="reindex",
                expected_authz_revision=2,
                expected_source_revision="revision-1",
            ),
        )

    assert source_repository.trigger_mode is None
    assert projection_facade.command is None
