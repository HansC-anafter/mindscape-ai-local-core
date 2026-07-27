from datetime import datetime, timezone

import pytest

from backend.app.models.workspace import Task, TaskStatus
from backend.app.runner import task_executor_admission
from backend.app.runner.task_executor_admission import (
    LEGACY_QUEUE_SNAPSHOT_CUTOVER,
    RUNNER_ADMISSION_BLOCKED_REASON,
    park_task_for_runner_admission,
    prepare_runner_child_admission,
)
from backend.app.runner.task_executor_process import build_child_payload
from backend.app.services.workspace_capability_admission.execution_snapshot import (
    build_execution_snapshot,
)
from backend.app.services.task_admission_service import ADMISSION_DEFERRED_REASON
from backend.app.services.knowledge_projection.retrievable.internal_admission import (
    build_internal_projection_admission,
)
from backend.app.services.knowledge_projection.retrievable.source_admission import (
    INTERNAL_PROJECTION_TOOL,
)


NOW = datetime(2026, 7, 25, tzinfo=timezone.utc)


def _task(*, task_type="playbook_execution", context=None, created_at=NOW):
    return Task(
        id="task-one",
        workspace_id="workspace-one",
        message_id="message-one",
        execution_id="execution-one",
        pack_id="pack.action",
        task_type=task_type,
        status=TaskStatus.RUNNING,
        execution_context=context or {"inputs": {}},
        created_at=created_at,
    )


def _snapshot():
    return build_execution_snapshot(
        {
            "source_runtime_id": "runtime-one",
            "workspace_id": "workspace-one",
            "active_group_id": None,
            "topology_snapshot_id": None,
            "topology_snapshot_hash": None,
            "wpcs_hash": "3" * 64,
            "catalog_hash": "2" * 64,
            "admission_mode": "legacy_unmanaged",
            "pcs_id": None,
            "pcs_version": None,
            "product_surface_id": "pack.action.surface",
            "selector_kind": "playbook",
            "selector_key": "pack.action",
            "operation_type": "generate",
            "entry": "local",
            "execution_backend": "local",
            "deployment_mode": "unmanaged_local",
            "deployment_state_revision": 0,
            "deployment_envelope_revision": None,
            "dce_hash": None,
            "availability": "not_configured",
            "diagnostics": [],
            "external_decision_id": None,
            "external_decision_issuer": None,
            "external_decision_expires_at": None,
            "provider_token_id": None,
            "trace_id": "execution-one",
            "root_execution_id": "execution-one",
            "admitted_at": NOW,
        }
    )


@pytest.mark.asyncio
async def test_legacy_playbook_gets_hashed_pre_cutover_snapshot(monkeypatch):
    async def forbidden_prepare(**kwargs):
        raise AssertionError("pre-cutover task must not be re-admitted")

    monkeypatch.setattr(
        task_executor_admission,
        "prepare_playbook_admission",
        forbidden_prepare,
    )
    result = await prepare_runner_child_admission(
        _task(),
        {"execution_id": "execution-one"},
        {"inputs": {}},
        profile_id="profile-one",
    )

    assert result.changed is True
    snapshot = result.execution_context["execution_admission_snapshot"]
    assert snapshot["availability"] == "available"
    assert snapshot["admission_mode"] == "legacy_unmanaged"
    assert "pre_snapshot_queue_compatibility" in snapshot["diagnostics"]
    assert snapshot["snapshot_hash"] == (
        result.inputs["execution_admission_snapshot"]["snapshot_hash"]
    )
    assert result.execution_context["inputs"] == result.inputs


@pytest.mark.asyncio
async def test_post_cutover_missing_snapshot_uses_current_root_admission(monkeypatch):
    snapshot = _snapshot()
    calls = []

    async def fake_prepare(**kwargs):
        calls.append(kwargs)
        normalized = dict(kwargs["inputs"])
        normalized["execution_admission_snapshot"] = snapshot.model_dump(mode="json")
        return normalized, snapshot

    monkeypatch.setattr(
        task_executor_admission,
        "prepare_playbook_admission",
        fake_prepare,
    )
    task = _task(created_at=LEGACY_QUEUE_SNAPSHOT_CUTOVER)
    result = await prepare_runner_child_admission(
        task,
        {"execution_id": "execution-one"},
        {"inputs": {}},
        profile_id="profile-one",
    )

    assert len(calls) == 1
    assert result.execution_context["execution_admission_snapshot"][
        "snapshot_hash"
    ] == snapshot.snapshot_hash


@pytest.mark.asyncio
async def test_existing_snapshot_is_verified_without_root_readmission(monkeypatch):
    snapshot_payload = _snapshot().model_dump(mode="json")

    async def forbidden_prepare(**kwargs):
        raise AssertionError("root admission must not run")

    monkeypatch.setattr(
        task_executor_admission,
        "prepare_playbook_admission",
        forbidden_prepare,
    )
    inputs = {
        "execution_id": "execution-one",
        "execution_admission_snapshot": snapshot_payload,
    }
    context = {
        "inputs": inputs,
        "execution_admission_snapshot": snapshot_payload,
    }
    result = await prepare_runner_child_admission(
        _task(context=context),
        inputs,
        context,
        profile_id="profile-one",
    )

    assert result.changed is False
    assert result.inputs == inputs
    assert result.execution_context == context


@pytest.mark.asyncio
async def test_admission_block_preserves_retry_and_acks_processing_item():
    task = _task(
        context={
            "inputs": {},
            "retry_count": 2,
            "status": "running",
        }
    )
    captured = {}

    class Store:
        def get_task(self, task_id):
            return task

        def update_task(self, task_id, **kwargs):
            captured.update(kwargs)

    class Queue:
        def __init__(self):
            self.acked = []

        async def ack_task(self, task_id):
            self.acked.append(task_id)

    queue = Queue()
    await park_task_for_runner_admission(
        Store(),
        task,
        "runner-one",
        ValueError("invalid"),
        queue,
    )

    assert captured["status"] == TaskStatus.PENDING
    assert captured["blocked_reason"] == ADMISSION_DEFERRED_REASON
    assert captured["blocked_payload"]["reason"] == RUNNER_ADMISSION_BLOCKED_REASON
    assert captured["next_eligible_at"] > NOW
    assert captured["frontier_state"] == "cold"
    assert captured["execution_context"]["retry_count"] == 2
    assert captured["execution_context"]["status"] == "blocked_admission"
    assert captured["error"] is None
    assert queue.acked == ["task-one"]


def test_child_payload_consumes_the_same_context_snapshot():
    snapshot_payload = _snapshot().model_dump(mode="json")
    payload = build_child_payload(
        task=_task(),
        runner_id="runner-one",
        inputs={"execution_id": "execution-one"},
        ctx={"execution_admission_snapshot": snapshot_payload},
        resolved_profile_id="profile-one",
        result_file="/tmp/result.json",
    )

    assert payload["execution_admission_snapshot"] == snapshot_payload
    assert payload["inputs"]["execution_admission_snapshot"] == snapshot_payload


def _internal_projection_fixture():
    task_id = "ktask_" + "1" * 64
    intake_id = "ksi_" + "2" * 32
    descriptor_hash = "3" * 64
    source_payload = {
        "contract_version": "knowledge.project-source.v1",
        "internal_task_id": task_id,
        "intake_id": intake_id,
        "actor_user_id": "profile-one",
        "tenant_id": "local",
        "workspace_id": "workspace-one",
        "group_id": None,
        "trigger_mode": "source_revision",
        "descriptor": {
            "capability_code": "test_pack",
            "capability_version": "1.0.0",
            "descriptor_id": "test_projection",
            "descriptor_hash": descriptor_hash,
            "manifest_hash": "4" * 64,
        },
        "source": {
            "source_kind": "object",
            "source_instance_id": "object-one",
            "source_ref": "aol://workspace-one/object-one",
            "source_revision": "revision-one",
            "content_hash": "5" * 64,
            "object_kind": "test.object",
            "artifact_selector": None,
        },
        "checkpoint": {"cursor_id": "object-one"},
    }
    receipt = build_internal_projection_admission(
        task_id=task_id,
        tenant_id="local",
        actor_user_id="profile-one",
        workspace_id="workspace-one",
        group_id=None,
        capability_code="test_pack",
        descriptor_id="test_projection",
        descriptor_hash=descriptor_hash,
        sources=[
            {
                "intake_id": intake_id,
                "source_instance_id": "object-one",
                "source_revision": "revision-one",
                "content_hash": "5" * 64,
            }
        ],
        trigger_mode="source_revision",
    )
    context = {
        "tool_name": INTERNAL_PROJECTION_TOOL,
        "inputs": source_payload,
        "knowledge_projection_admission": receipt.model_dump(mode="json"),
    }
    task = Task(
        id=task_id,
        workspace_id="workspace-one",
        message_id=f"knowledge-intake:{intake_id}",
        execution_id=task_id,
        pack_id=INTERNAL_PROJECTION_TOOL,
        task_type="tool_execution",
        status=TaskStatus.RUNNING,
        params=source_payload,
        execution_context=context,
        created_at=NOW,
    )
    return task, source_payload, context, receipt


@pytest.mark.asyncio
async def test_internal_projection_task_uses_committed_source_receipt(
    monkeypatch,
):
    from backend.app.services.knowledge_projection.source_ledger import (
        KnowledgeSourceLedgerFacade,
    )

    task, inputs, context, receipt = _internal_projection_fixture()
    monkeypatch.setattr(
        KnowledgeSourceLedgerFacade,
        "verify_internal_projection_admission",
        lambda self, candidate: candidate.receipt_hash == receipt.receipt_hash,
    )
    result = await prepare_runner_child_admission(
        task,
        inputs,
        context,
        profile_id="profile-one",
    )

    assert "execution_admission_snapshot" not in result.execution_context
    assert result.execution_context["knowledge_projection_admission"][
        "receipt_hash"
    ] == receipt.receipt_hash
    child = build_child_payload(
        task=task,
        runner_id="runner-one",
        inputs=result.inputs,
        ctx=result.execution_context,
        resolved_profile_id="profile-one",
        result_file="/tmp/result.json",
    )
    assert child["knowledge_projection_admission"]["receipt_hash"] == (
        receipt.receipt_hash
    )


@pytest.mark.asyncio
async def test_internal_projection_task_rejects_forged_identity(monkeypatch):
    from backend.app.services.knowledge_projection.source_ledger import (
        KnowledgeSourceLedgerFacade,
    )

    task, inputs, context, _receipt = _internal_projection_fixture()
    monkeypatch.setattr(
        KnowledgeSourceLedgerFacade,
        "verify_internal_projection_admission",
        lambda self, candidate: True,
    )
    forged = dict(inputs)
    forged["actor_user_id"] = "attacker"

    with pytest.raises(
        ValueError,
        match="knowledge_projection_internal_admission_identity_mismatch",
    ):
        await prepare_runner_child_admission(
            task,
            forged,
            context,
            profile_id="profile-one",
        )
