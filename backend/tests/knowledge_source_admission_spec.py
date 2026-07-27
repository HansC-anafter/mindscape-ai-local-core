from contextlib import contextmanager
import hashlib
from pathlib import Path

import pytest

from backend.app.services.knowledge_authorization import (
    KnowledgePermission,
    PrincipalRef,
    RetrievalAccessContext,
)
from backend.app.services.knowledge_projection.contracts import (
    KnowledgeSourceIntakeReceipt,
)
from backend.app.services.knowledge_projection.retrievable.adapter_registry import (
    KnowledgeProjectionAdapterRegistry,
)
from backend.app.services.knowledge_projection.retrievable.source_admission import (
    INTERNAL_PROJECTION_TOOL,
    RetrievableSourceAdmissionCommand,
    RetrievableSourceAdmissionService,
)
from backend.app.services.knowledge_projection.retrievable.task_payload import (
    KnowledgeProjectionTaskPayload,
    MAX_KNOWLEDGE_PROJECTION_TASK_BYTES,
)
from backend.app.services.runner_topology import (
    KNOWLEDGE_INDEXING_QUEUE_PARTITION,
)


def _registry():
    registry = KnowledgeProjectionAdapterRegistry()
    manifest = {
        "code": "test_pack",
        "version": "1.2.3",
        "object_exports": [{"kind": "test.asset"}],
        "knowledge_projections": [
            {
                "id": "asset_projection",
                "source_kind": "object",
                "object_kinds": ["test.asset"],
                "contract_version": "1.0.0",
                "compiler_backend": (
                    "capabilities.test_pack.projections.compiler:compile_asset"
                ),
                "projection_profiles": [
                    "semantic_text",
                    "typed_records",
                    "evidence_graph",
                ],
                "evidence_unit_kinds": ["text_span", "image_region"],
                "derived_text_kinds": ["caption"],
                "trigger_modes": [
                    "source_revision",
                    "explicit_reindex",
                    "revoke",
                ],
                "limits": {
                    "max_chunks": 100,
                    "max_records_per_page": 1000,
                },
            }
        ],
    }
    descriptor = registry.register_manifest(
        "test_pack",
        manifest,
        Path("/tmp/test-pack"),
    )[0]
    return registry, descriptor


def _context():
    return RetrievalAccessContext.create(
        subject_user_id="user-1",
        tenant_id="tenant-1",
        principals=(PrincipalRef("user", "user-1"),),
        permissions=(
            KnowledgePermission(
                "knowledge.project",
                "workspace",
                "workspace-1",
            ),
        ),
    )


def _command(descriptor, **overrides):
    payload = {
        "capability_code": descriptor.capability_code,
        "capability_version": descriptor.capability_version,
        "descriptor_id": descriptor.descriptor_id,
        "descriptor_hash": descriptor.descriptor_hash,
        "manifest_hash": descriptor.manifest_hash,
        "source_kind": "object",
        "source_instance_id": "asset-1",
        "source_ref": "aol://workspace-1/asset/asset-1",
        "source_revision": "revision-7",
        "content_hash": "a" * 64,
        "evidence_type": "aol_object_revision",
        "evidence_id": "evidence-7",
        "workspace_id": "workspace-1",
        "object_kind": "test.asset",
        "trigger_mode": "source_revision",
        "checkpoint": {"revision": 7, "cursor_id": "asset-1"},
    }
    payload.update(overrides)
    return RetrievableSourceAdmissionCommand.model_validate(payload)


class _Ledger:
    def __init__(self):
        self.connections = []
        self.created = True

    def prepare_intake(self, _intake):
        return "ksi_" + hashlib.sha256(
            _intake.source_instance_id.encode("utf-8")
        ).hexdigest()[:32]

    def record_intake_with_conn(self, conn, intake, *, intake_id):
        self.connections.append(conn)
        return KnowledgeSourceIntakeReceipt(
            intake_id=intake_id,
            source_instance_id=intake.source_instance_id,
            source_revision=intake.source_revision,
            content_hash=intake.content_hash,
            created=self.created,
        )


class _AdmissionStore:
    def __init__(self):
        self.connections = []
        self.receipts = []

    def record_with_conn(self, conn, receipt):
        self.connections.append(conn)
        self.receipts.append(receipt)


class _Tasks:
    def __init__(self):
        self.connection = object()
        self.connections = []
        self.events = []
        self.created = True
        self.last_task = None
        self.retry_result = None

    def prepare_task_for_create(self, task):
        self.events.append("prepared")
        self.last_task = task
        return task

    @contextmanager
    def transaction(self):
        self.events.append("transaction_started")
        try:
            yield self.connection
        except Exception:
            self.events.append("transaction_rolled_back")
            raise
        else:
            self.events.append("transaction_committed")

    def create_task_with_conn(
        self,
        conn,
        task,
        *,
        already_prepared,
        idempotent,
    ):
        assert already_prepared is True
        assert idempotent is True
        self.connections.append(conn)
        self.events.append("task_written")
        return task, self.created

    def finalize_task_create_after_commit(self, task, *, created):
        self.events.append(("finalized", created))
        return task

    def retry_terminal_task_after_commit(self, task_id):
        self.events.append(("retry_terminal", task_id))
        return self.retry_result


def test_source_admission_uses_one_transaction_and_pointer_only_task():
    registry, descriptor = _registry()
    ledger = _Ledger()
    admissions = _AdmissionStore()
    tasks = _Tasks()
    service = RetrievableSourceAdmissionService(
        registry=registry,
        source_ledger=ledger,
        tasks_store=tasks,
        internal_admission_store=admissions,
    )

    receipt = service.admit(_command(descriptor), access_context=_context())

    assert receipt.state == "admitted"
    assert receipt.queue_shard == KNOWLEDGE_INDEXING_QUEUE_PARTITION
    assert ledger.connections == [tasks.connection]
    assert tasks.connections == [tasks.connection]
    assert admissions.connections == [tasks.connection]
    assert admissions.receipts[0].task_id == receipt.task_id
    assert tasks.events == [
        "prepared",
        "transaction_started",
        "task_written",
        "transaction_committed",
        ("finalized", True),
    ]


def test_source_admission_rolls_back_before_enqueue_on_failpoint():
    registry, descriptor = _registry()
    ledger = _Ledger()
    admissions = _AdmissionStore()
    tasks = _Tasks()

    def failpoint(step):
        if step == "intake_written":
            raise RuntimeError("expected_failpoint")

    service = RetrievableSourceAdmissionService(
        registry=registry,
        source_ledger=ledger,
        tasks_store=tasks,
        internal_admission_store=admissions,
        failpoint=failpoint,
    )

    with pytest.raises(RuntimeError, match="expected_failpoint"):
        service.admit(_command(descriptor), access_context=_context())

    assert ledger.connections == [tasks.connection]
    assert tasks.connections == []
    assert admissions.connections == []
    assert tasks.events == [
        "prepared",
        "transaction_started",
        "transaction_rolled_back",
    ]


def test_source_admission_reuses_intake_and_task_idempotently():
    registry, descriptor = _registry()
    ledger = _Ledger()
    admissions = _AdmissionStore()
    tasks = _Tasks()
    service = RetrievableSourceAdmissionService(
        registry=registry,
        source_ledger=ledger,
        tasks_store=tasks,
        internal_admission_store=admissions,
    )
    first = service.admit(_command(descriptor), access_context=_context())
    ledger.created = False
    tasks.created = False

    second = service.admit(_command(descriptor), access_context=_context())

    assert second.state == "reused"
    assert second.intake_id == first.intake_id
    assert second.task_id == first.task_id
    assert second.intake_created is False
    assert second.task_created is False
    assert admissions.connections == [
        tasks.connection,
        tasks.connection,
    ]
    assert tasks.events[-1] == ("finalized", False)


def test_source_admission_batches_one_descriptor_page_into_one_task():
    registry, descriptor = _registry()
    ledger = _Ledger()
    admissions = _AdmissionStore()
    tasks = _Tasks()
    service = RetrievableSourceAdmissionService(
        registry=registry,
        source_ledger=ledger,
        tasks_store=tasks,
        internal_admission_store=admissions,
    )
    commands = (
        _command(descriptor, source_instance_id="asset-2"),
        _command(descriptor, source_instance_id="asset-1"),
    )

    receipt = service.admit_page(commands, access_context=_context())

    assert receipt.task_created is True
    assert len(receipt.intake_ids) == 2
    assert tasks.events.count("task_written") == 1
    assert len(ledger.connections) == 2
    assert set(ledger.connections) == {tasks.connection}
    assert len(admissions.receipts[0].sources) == 2
    payload = KnowledgeProjectionTaskPayload.model_validate(
        tasks.last_task.params
    )
    assert [item.source_instance_id for item in payload.source_page] == [
        "asset-1",
        "asset-2",
    ]


def test_explicit_reindex_retries_only_an_existing_terminal_task():
    registry, descriptor = _registry()
    ledger = _Ledger()
    ledger.created = False
    admissions = _AdmissionStore()
    tasks = _Tasks()
    tasks.created = False
    service = RetrievableSourceAdmissionService(
        registry=registry,
        source_ledger=ledger,
        tasks_store=tasks,
        internal_admission_store=admissions,
    )
    command = _command(
        descriptor,
        trigger_mode="explicit_reindex",
        auto_triggered=False,
    )
    tasks.retry_result = None
    reused = service.admit(command, access_context=_context())
    tasks.retry_result = tasks.last_task
    retried = service.admit(command, access_context=_context())

    assert reused.state == "reused"
    assert retried.state == "retried"
    assert len(admissions.receipts) == 2


def test_source_revision_and_revoke_share_intake_but_not_task_receipt():
    registry, descriptor = _registry()
    ledger = _Ledger()
    admissions = _AdmissionStore()
    tasks = _Tasks()
    service = RetrievableSourceAdmissionService(
        registry=registry,
        source_ledger=ledger,
        tasks_store=tasks,
        internal_admission_store=admissions,
    )

    projected = service.admit(
        _command(descriptor),
        access_context=_context(),
    )
    ledger.created = False
    revoked = service.admit(
        _command(
            descriptor,
            trigger_mode="revoke",
            auto_triggered=False,
        ),
        access_context=_context(),
    )

    assert projected.intake_id == revoked.intake_id
    assert projected.task_id != revoked.task_id
    assert [receipt.trigger_mode for receipt in admissions.receipts] == [
        "source_revision",
        "revoke",
    ]


def test_projection_task_payload_rejects_secrets_and_source_bodies():
    _, descriptor = _registry()
    command = _command(descriptor)
    base = {
        "internal_task_id": "ktask-1",
        "intake_id": "ksi-1",
        "actor_user_id": "user-1",
        "tenant_id": "tenant-1",
        "workspace_id": "workspace-1",
        "trigger_mode": command.trigger_mode,
        "descriptor": {
            "capability_code": descriptor.capability_code,
            "capability_version": descriptor.capability_version,
            "descriptor_id": descriptor.descriptor_id,
            "descriptor_hash": descriptor.descriptor_hash,
            "manifest_hash": descriptor.manifest_hash,
        },
        "source": {
            "source_kind": command.source_kind,
            "source_instance_id": command.source_instance_id,
            "source_ref": command.source_ref,
            "source_revision": command.source_revision,
            "content_hash": command.content_hash,
            "object_kind": command.object_kind,
        },
    }
    valid = KnowledgeProjectionTaskPayload.model_validate(
        {**base, "checkpoint": {"page": 4, "cursor_id": "row-91"}}
    )
    encoded = valid.model_dump_json().encode("utf-8")
    assert len(encoded) <= MAX_KNOWLEDGE_PROJECTION_TASK_BYTES

    with pytest.raises(
        ValueError,
        match="secret_or_body_forbidden",
    ):
        KnowledgeProjectionTaskPayload.model_validate(
            {**base, "checkpoint": {"api_token": "do-not-persist"}}
        )
    with pytest.raises(
        ValueError,
        match="secret_or_body_forbidden",
    ):
        KnowledgeProjectionTaskPayload.model_validate(
            {**base, "checkpoint": {"raw_content": "not-a-pointer"}}
        )


def test_source_admission_requires_server_permission():
    registry, descriptor = _registry()
    denied = RetrievalAccessContext.create(
        subject_user_id="user-1",
        tenant_id="tenant-1",
        principals=(PrincipalRef("user", "user-1"),),
    )
    service = RetrievableSourceAdmissionService(
        registry=registry,
        source_ledger=_Ledger(),
        tasks_store=_Tasks(),
    )

    with pytest.raises(
        PermissionError,
        match="knowledge_source_admission_permission_required",
    ):
        service.admit(_command(descriptor), access_context=denied)


def test_internal_projection_tool_is_not_in_public_registry():
    from backend.app.services.tools.registry import (
        _mindscape_tools,
        get_all_mindscape_tools,
        get_mindscape_tool,
        register_internal_knowledge_projection_tool,
    )

    previous = _mindscape_tools.get(INTERNAL_PROJECTION_TOOL)
    try:
        register_internal_knowledge_projection_tool()
        assert get_mindscape_tool(INTERNAL_PROJECTION_TOOL) is not None
        assert INTERNAL_PROJECTION_TOOL not in get_all_mindscape_tools()
        assert (
            INTERNAL_PROJECTION_TOOL
            in get_all_mindscape_tools(include_internal=True)
        )
    finally:
        if previous is None:
            _mindscape_tools.pop(INTERNAL_PROJECTION_TOOL, None)
        else:
            _mindscape_tools[INTERNAL_PROJECTION_TOOL] = previous


@pytest.mark.asyncio
async def test_internal_projection_tool_rejects_direct_execution():
    from backend.app.services.tools.knowledge_project_source import (
        KnowledgeProjectSourceTool,
    )

    _, descriptor = _registry()
    command = _command(descriptor)
    payload = {
        "internal_task_id": "ktask-1",
        "intake_id": "ksi-1",
        "actor_user_id": "user-1",
        "tenant_id": "tenant-1",
        "workspace_id": "workspace-1",
        "trigger_mode": command.trigger_mode,
        "descriptor": {
            "capability_code": descriptor.capability_code,
            "capability_version": descriptor.capability_version,
            "descriptor_id": descriptor.descriptor_id,
            "descriptor_hash": descriptor.descriptor_hash,
            "manifest_hash": descriptor.manifest_hash,
        },
        "source": {
            "source_kind": command.source_kind,
            "source_instance_id": command.source_instance_id,
            "source_ref": command.source_ref,
            "source_revision": command.source_revision,
            "content_hash": command.content_hash,
            "object_kind": command.object_kind,
        },
    }

    with pytest.raises(
        PermissionError,
        match="runner_internal_tool_authority_required",
    ):
        await KnowledgeProjectSourceTool().execute(**payload)
