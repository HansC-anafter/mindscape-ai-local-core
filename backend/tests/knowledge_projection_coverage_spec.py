from datetime import datetime, timezone

import pytest

from backend.app.services.knowledge_authorization import (
    KnowledgePermission,
    PrincipalRef,
    RetrievalAccessContext,
)
from backend.app.services.knowledge_projection.retrievable.coverage import (
    ProjectionCoverageService,
)


NOW = datetime(2026, 7, 27, tzinfo=timezone.utc)


def _context(*, permitted=True):
    return RetrievalAccessContext.create(
        subject_user_id="owner-one",
        tenant_id="local",
        principals=(PrincipalRef("user", "owner-one"),),
        permissions=(
            (
                KnowledgePermission(
                    "knowledge.read",
                    "workspace",
                    "workspace-one",
                ),
            )
            if permitted
            else ()
        ),
    )


class _Core:
    def list_page(self, **_kwargs):
        return (
            {
                "intake_id": "intake-active",
                "source_instance_id": "source-active",
                "source_revision": "revision-one",
                "content_hash": "1" * 64,
                "metadata": {
                    "source_ref": "object:active",
                    "capability_code": "test_pack",
                    "descriptor_id": "asset_projection",
                    "trigger_mode": "source_revision",
                },
                "created_at": NOW,
                "task_id": "task-active",
                "task_status": "succeeded",
            },
            {
                "intake_id": "intake-gap",
                "source_instance_id": "source-gap",
                "source_revision": "revision-two",
                "content_hash": "2" * 64,
                "metadata": {
                    "source_ref": "object:gap",
                    "capability_code": "test_pack",
                    "descriptor_id": "asset_projection",
                    "trigger_mode": "source_revision",
                },
                "created_at": NOW,
                "task_id": "task-gap",
                "task_status": "succeeded",
            },
            {
                "intake_id": "intake-revoked",
                "source_instance_id": "source-revoked",
                "source_revision": "revision-three",
                "content_hash": "3" * 64,
                "metadata": {
                    "source_ref": "object:revoked",
                    "capability_code": "test_pack",
                    "descriptor_id": "asset_projection",
                    "trigger_mode": "revoke",
                },
                "created_at": NOW,
                "task_id": "task-revoked",
                "task_status": "succeeded",
                "task_trigger_mode": "revoke",
            },
        )


class _Cursor:
    def execute(self, _query, _params):
        return None

    def fetchall(self):
        return [
            ("object:active", "revision-one", True, "active", True),
            ("object:revoked", "revision-three", False, "revoked", False),
        ]


class _Connection:
    def cursor(self):
        return _Cursor()

    def close(self):
        return None


def test_coverage_reports_active_revoked_and_crash_gap_without_retry_loop():
    service = ProjectionCoverageService(
        core_repository=_Core(),
        vector_connection_factory=_Connection,
    )

    page = service.list_page(
        access_context=_context(),
        scope_type="workspace",
        scope_id="workspace-one",
        limit=100,
    )

    assert [item.state for item in page.items] == [
        "active",
        "missing",
        "revoked",
    ]
    assert page.items[1].reason == "missing_active_projection"
    assert page.next_before_created_at is None


def test_coverage_requires_verified_scope_permission():
    service = ProjectionCoverageService(
        core_repository=_Core(),
        vector_connection_factory=_Connection,
    )

    with pytest.raises(
        PermissionError,
        match="knowledge_projection_coverage_permission_required",
    ):
        service.list_page(
            access_context=_context(permitted=False),
            scope_type="workspace",
            scope_id="workspace-one",
        )
