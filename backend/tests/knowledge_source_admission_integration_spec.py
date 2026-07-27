"""Disposable-core acceptance for atomic intake plus task admission."""

from pathlib import Path
import os

import psycopg2
import pytest

from backend.app.services.knowledge_authorization import (
    KnowledgePermission,
    PrincipalRef,
    RetrievalAccessContext,
)
from backend.app.services.knowledge_projection.retrievable.adapter_registry import (
    KnowledgeProjectionAdapterRegistry,
)
from backend.app.services.knowledge_projection.retrievable.internal_admission import (
    InternalProjectionAdmissionReceipt,
)
from backend.app.services.knowledge_projection.retrievable.internal_admission_store import (
    InternalProjectionAdmissionStore,
)
from backend.app.services.knowledge_projection.retrievable.source_admission import (
    RetrievableSourceAdmissionCommand,
    RetrievableSourceAdmissionService,
)
from backend.app.services.stores.tasks_store import TasksStore


TEST_CORE_URL = os.getenv("TEST_CORE_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_CORE_URL,
    reason="TEST_CORE_DATABASE_URL is required",
)


def _registry():
    registry = KnowledgeProjectionAdapterRegistry()
    descriptor = registry.register_manifest(
        "atomic_pack",
        {
            "code": "atomic_pack",
            "version": "1.0.0",
            "object_exports": [{"kind": "atomic.asset"}],
            "knowledge_projections": [
                {
                    "id": "atomic_projection",
                    "source_kind": "object",
                    "object_kinds": ["atomic.asset"],
                    "contract_version": "1.0.0",
                    "compiler_backend": (
                        "capabilities.atomic_pack.projections.compiler:"
                        "compile_asset"
                    ),
                    "projection_profiles": ["semantic_text"],
                    "evidence_unit_kinds": ["text_span"],
                    "trigger_modes": [
                        "source_revision",
                        "explicit_reindex",
                        "revoke",
                    ],
                    "limits": {
                        "max_chunks": 100,
                        "max_records_per_page": 100,
                    },
                }
            ],
        },
        Path("/tmp/atomic-pack"),
    )[0]
    return registry, descriptor


def _command(descriptor, source_id, **overrides):
    command = RetrievableSourceAdmissionCommand(
        capability_code="atomic_pack",
        capability_version="1.0.0",
        descriptor_id=descriptor.descriptor_id,
        descriptor_hash=descriptor.descriptor_hash,
        manifest_hash=descriptor.manifest_hash,
        source_kind="object",
        source_instance_id=source_id,
        source_ref=f"aol://workspace-atomic/{source_id}",
        source_revision="revision-one",
        content_hash=("a" if source_id.endswith("one") else "b") * 64,
        evidence_type="aol_object_revision",
        evidence_id=f"evidence:{source_id}",
        workspace_id="workspace-atomic",
        object_kind="atomic.asset",
        trigger_mode="source_revision",
        checkpoint={"cursor_id": source_id},
    )
    return RetrievableSourceAdmissionCommand.model_validate(
        {
            **command.model_dump(mode="json"),
            **overrides,
        }
    )


def _context():
    return RetrievalAccessContext.create(
        subject_user_id="atomic-owner",
        tenant_id="local",
        principals=(PrincipalRef("user", "atomic-owner"),),
        permissions=(
            KnowledgePermission(
                "knowledge.project",
                "workspace",
                "workspace-atomic",
            ),
        ),
    )


def _counts(source_id):
    connection = psycopg2.connect(TEST_CORE_URL)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    (
                        SELECT COUNT(*)
                        FROM knowledge_source_intakes
                        WHERE source_instance_id = %s
                    ),
                    (
                        SELECT COUNT(*)
                        FROM tasks
                        WHERE params->'source'->>'source_instance_id' = %s
                    ),
                    (
                        SELECT COUNT(*)
                        FROM knowledge_projection_task_admissions AS admission
                        JOIN knowledge_source_intakes AS intake
                          ON intake.id = admission.intake_id
                        WHERE intake.source_instance_id = %s
                    )
                """,
                (source_id, source_id, source_id),
            )
            return cursor.fetchone()
    finally:
        connection.close()


def _service(*, failpoint=None):
    registry, descriptor = _registry()
    tasks = TasksStore()
    tasks._enqueue_runner_task_after_commit = lambda _task: None
    return (
        RetrievableSourceAdmissionService(
            registry=registry,
            tasks_store=tasks,
            failpoint=failpoint,
        ),
        descriptor,
    )


def test_intake_and_task_commit_once_with_real_postgres_transaction():
    service, descriptor = _service()
    command = _command(descriptor, "atomic-source-one")

    first = service.admit(command, access_context=_context())
    second = service.admit(command, access_context=_context())

    assert first.task_id == second.task_id
    assert first.state == "admitted"
    assert second.state == "reused"
    assert _counts(command.source_instance_id) == (1, 1, 1)


def test_failpoint_after_intake_rolls_back_both_real_rows():
    def failpoint(step):
        if step == "intake_written":
            raise RuntimeError("atomic_rollback_expected")

    service, descriptor = _service(failpoint=failpoint)
    command = _command(descriptor, "atomic-source-two")

    with pytest.raises(RuntimeError, match="atomic_rollback_expected"):
        service.admit(command, access_context=_context())

    assert _counts(command.source_instance_id) == (0, 0, 0)


def test_same_intake_supports_distinct_projection_and_revoke_receipts():
    service, descriptor = _service()
    projected = service.admit(
        _command(descriptor, "atomic-source-three"),
        access_context=_context(),
    )
    revoked = service.admit(
        _command(
            descriptor,
            "atomic-source-three",
            trigger_mode="revoke",
            auto_triggered=False,
        ),
        access_context=_context(),
    )

    assert projected.intake_id == revoked.intake_id
    assert projected.task_id != revoked.task_id
    assert _counts("atomic-source-three") == (1, 2, 2)

    tasks = TasksStore()
    for task_id in (projected.task_id, revoked.task_id):
        task = tasks.get_task(task_id)
        receipt = InternalProjectionAdmissionReceipt.model_validate(
            task.execution_context["knowledge_projection_admission"]
        )
        assert InternalProjectionAdmissionStore().verify(receipt) is True
