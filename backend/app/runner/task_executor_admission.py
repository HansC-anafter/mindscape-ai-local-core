"""Parent-side admission convergence for runner child execution."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any, Dict, Optional

from backend.app.models.workspace import Task, TaskStatus
from backend.app.services.playbook_run_executor_admission import (
    prepare_playbook_admission,
)
from backend.app.services.stores.redis.runner_queue_store import RedisRunnerQueueStore
from backend.app.services.stores.tasks_store import TasksStore
from backend.app.services.task_admission_service import ADMISSION_DEFERRED_REASON
from backend.app.services.tool_execution_admission import prepare_tool_admission
from backend.app.services.workspace_capability_admission.child_snapshot_verifier import (
    verify_child_snapshot,
)
from backend.app.services.workspace_capability_admission.contracts import (
    ExecutionAdmissionSnapshot,
)
from backend.app.services.workspace_capability_admission.execution_snapshot import (
    build_execution_snapshot,
)

from backend.app.runner.utils import _utc_now

logger = logging.getLogger(__name__)

RUNNER_ADMISSION_BLOCKED_REASON = "workspace_product_admission_required"
RUNNER_ADMISSION_RETRY_SECONDS = 300
LEGACY_QUEUE_SNAPSHOT_CUTOVER = datetime(
    2026,
    7,
    25,
    7,
    30,
    tzinfo=timezone.utc,
)


@dataclass(frozen=True)
class RunnerChildAdmission:
    """The one normalized parent-to-child admission payload."""

    inputs: Dict[str, Any]
    execution_context: Dict[str, Any]
    changed: bool


def _validated_snapshot(
    payload: Any,
    *,
    workspace_id: str,
    root_execution_id: str,
) -> ExecutionAdmissionSnapshot:
    if not isinstance(payload, dict):
        raise ValueError("runner_parent_admission_snapshot_invalid")
    parsed = ExecutionAdmissionSnapshot.model_validate(payload)
    return verify_child_snapshot(
        parsed,
        expected_workspace_id=workspace_id,
        expected_root_execution_id=root_execution_id,
    )


def _existing_snapshot(
    *,
    inputs: Dict[str, Any],
    execution_context: Dict[str, Any],
    workspace_id: str,
    root_execution_id: str,
) -> ExecutionAdmissionSnapshot | None:
    input_snapshot = inputs.get("execution_admission_snapshot")
    context_snapshot = execution_context.get("execution_admission_snapshot")
    if input_snapshot is None and context_snapshot is None:
        return None

    selected = context_snapshot if context_snapshot is not None else input_snapshot
    parsed = _validated_snapshot(
        selected,
        workspace_id=workspace_id,
        root_execution_id=root_execution_id,
    )
    if input_snapshot is not None and context_snapshot is not None:
        input_parsed = _validated_snapshot(
            input_snapshot,
            workspace_id=workspace_id,
            root_execution_id=root_execution_id,
        )
        if input_parsed.snapshot_hash != parsed.snapshot_hash:
            raise ValueError("runner_parent_admission_snapshot_conflict")
    return parsed


def _task_created_at(task: Task) -> datetime:
    created_at = task.created_at
    if created_at.tzinfo is None:
        return created_at.replace(tzinfo=timezone.utc)
    return created_at.astimezone(timezone.utc)


def _legacy_queue_snapshot(
    task: Task,
    inputs: Dict[str, Any],
    *,
    workspace_id: str,
    root_execution_id: str,
) -> ExecutionAdmissionSnapshot:
    """Pin tasks queued before snapshot enforcement to their prior admission."""
    selector_kind = (
        "tool"
        if (task.task_type or "playbook_execution") == "tool_execution"
        else "playbook"
    )
    selector_key = str(
        inputs.get("tool_name") if selector_kind == "tool" else task.pack_id
    ).strip() or str(task.pack_id or task.id)
    product_surface_id = str(
        inputs.get("product_surface_id") or "legacy.runner.queued_execution"
    ).strip()
    legacy_wpcs_hash = sha256(
        f"legacy-queue-wpcs:{workspace_id}".encode("utf-8")
    ).hexdigest()
    legacy_catalog_hash = sha256(
        b"legacy-queue-pre-snapshot-catalog"
    ).hexdigest()
    created_at = _task_created_at(task)
    return build_execution_snapshot(
        {
            "source_runtime_id": "local-core-legacy-runner-cutover",
            "workspace_id": workspace_id,
            "active_group_id": None,
            "topology_revision": None,
            "topology_snapshot_id": None,
            "topology_snapshot_hash": None,
            "wpcs_hash": legacy_wpcs_hash,
            "catalog_hash": legacy_catalog_hash,
            "admission_mode": "legacy_unmanaged",
            "pcs_id": None,
            "pcs_version": None,
            "product_surface_id": product_surface_id[:256],
            "selector_kind": selector_kind,
            "selector_key": selector_key[:512],
            "operation_type": (
                "modify" if selector_kind == "tool" else "generate"
            ),
            "entry": "local",
            "execution_backend": "local",
            "deployment_mode": "unmanaged_local",
            "deployment_state_revision": 0,
            "deployment_envelope_revision": None,
            "dce_hash": None,
            "availability": "available",
            "diagnostics": [
                "pre_snapshot_queue_compatibility",
                f"cutover:{LEGACY_QUEUE_SNAPSHOT_CUTOVER.isoformat()}",
            ],
            "external_decision_id": None,
            "external_decision_issuer": None,
            "external_decision_expires_at": None,
            "provider_token_id": None,
            "trace_id": str(inputs.get("trace_id") or root_execution_id)[:128],
            "root_execution_id": root_execution_id,
            "admitted_at": created_at,
        }
    )


async def prepare_runner_child_admission(
    task: Task,
    inputs: Dict[str, Any],
    execution_context: Dict[str, Any],
    *,
    profile_id: str,
) -> RunnerChildAdmission:
    """Converge legacy/current tasks before a child process can start."""
    normalized_inputs = dict(inputs)
    normalized_context = dict(execution_context)
    workspace_id = str(task.workspace_id or "").strip()
    if task.task_type == "product_outcome_evaluation" and not workspace_id:
        raise ValueError("outcome_task_workspace_required")
    if not workspace_id:
        return RunnerChildAdmission(
            inputs=normalized_inputs,
            execution_context=normalized_context,
            changed=False,
        )

    root_execution_id = str(task.execution_id or task.id)
    internal_admission = _verified_internal_projection_admission(
        task=task,
        inputs=normalized_inputs,
        execution_context=normalized_context,
    )
    if task.task_type == "product_outcome_evaluation":
        from backend.app.services.workflow.durable_state.outcome_runtime_trust import (
            OutcomeRuntimeTrust,
        )
        from backend.app.services.workflow.durable_state.outcome_task_admission import (
            verify_outcome_task_admission,
        )

        receipt = verify_outcome_task_admission(
            normalized_context.get("product_outcome_evaluation_admission"),
            expected_task_id=task.id,
            expected_workspace_id=workspace_id,
            expected_params=dict(task.params),
            verification_keys=(
                OutcomeRuntimeTrust.from_mounted_files().descriptor_verification_keys
            ),
        )
        candidate_inputs = dict(normalized_inputs)
        injected_execution_id = candidate_inputs.pop(
            "execution_id",
            None,
        )
        if injected_execution_id is not None and str(injected_execution_id) != str(
            task.execution_id or task.id
        ):
            raise ValueError("outcome_task_execution_id_mismatch")
        if candidate_inputs != task.params:
            raise ValueError("outcome_task_input_identity_mismatch")
        normalized_context["inputs"] = dict(task.params)
        normalized_context["product_outcome_evaluation_admission"] = receipt
        for key in (
            "execution_backend_hint",
            "runtime_binding",
            "selected_runtime_id",
            "execution_admission_snapshot",
        ):
            normalized_context.pop(key, None)
        return RunnerChildAdmission(
            inputs=dict(task.params),
            execution_context=normalized_context,
            changed=normalized_context != execution_context,
        )
    if internal_admission is not None:
        internal_receipt, projection_payload = internal_admission
        normalized_inputs = projection_payload.bounded_dict()
        normalized_context["inputs"] = normalized_inputs
        for key in (
            "execution_backend_hint",
            "runtime_binding",
            "selected_runtime_id",
        ):
            normalized_context.pop(key, None)
        normalized_context["knowledge_projection_admission"] = (
            internal_receipt.model_dump(mode="json")
        )
        return RunnerChildAdmission(
            inputs=normalized_inputs,
            execution_context=normalized_context,
            changed=normalized_context != execution_context,
        )
    snapshot = _existing_snapshot(
        inputs=normalized_inputs,
        execution_context=normalized_context,
        workspace_id=workspace_id,
        root_execution_id=root_execution_id,
    )

    if snapshot is None and _task_created_at(task) < LEGACY_QUEUE_SNAPSHOT_CUTOVER:
        snapshot = _legacy_queue_snapshot(
            task,
            normalized_inputs,
            workspace_id=workspace_id,
            root_execution_id=root_execution_id,
        )

    if snapshot is None:
        if (task.task_type or "playbook_execution") == "tool_execution":
            tool_name = str(
                normalized_context.get("tool_name") or task.pack_id or ""
            ).strip()
            admission_arguments = dict(normalized_inputs)
            injected_workspace_id = "workspace_id" not in admission_arguments
            injected_actor_id = "actor_user_id" not in admission_arguments
            admission_arguments.setdefault("workspace_id", workspace_id)
            admission_arguments.setdefault("actor_user_id", profile_id)
            admission_arguments.setdefault("root_execution_id", root_execution_id)
            governed_inputs, snapshot = await prepare_tool_admission(
                tool_name=tool_name,
                arguments=admission_arguments,
            )
            if injected_workspace_id:
                governed_inputs.pop("workspace_id", None)
            if injected_actor_id:
                governed_inputs.pop("actor_user_id", None)
            normalized_inputs = governed_inputs
        else:
            normalized_inputs, snapshot = await prepare_playbook_admission(
                playbook_code=task.pack_id,
                profile_id=profile_id,
                workspace_id=workspace_id,
                project_id=(
                    str(normalized_inputs.get("project_id"))
                    if normalized_inputs.get("project_id")
                    else None
                ),
                inputs={
                    **normalized_inputs,
                    "execution_id": root_execution_id,
                },
            )

    if snapshot is None:
        raise ValueError("runner_parent_admission_snapshot_required")

    snapshot_payload = snapshot.model_dump(mode="json")
    normalized_inputs["execution_admission_snapshot"] = snapshot_payload
    normalized_context["execution_admission_snapshot"] = snapshot_payload
    normalized_context["inputs"] = normalized_inputs
    changed = (
        normalized_inputs != inputs
        or normalized_context != execution_context
    )
    return RunnerChildAdmission(
        inputs=normalized_inputs,
        execution_context=normalized_context,
        changed=changed,
    )


def _verified_internal_projection_admission(
    *,
    task: Task,
    inputs: Dict[str, Any],
    execution_context: Dict[str, Any],
):
    """Fail closed unless this hidden-tool task has a committed intake receipt."""

    from backend.app.services.knowledge_projection.retrievable.source_admission import (
        INTERNAL_PROJECTION_TOOL,
    )

    tool_name = str(
        execution_context.get("tool_name") or task.pack_id or ""
    ).strip()
    raw_receipt = execution_context.get("knowledge_projection_admission")
    if tool_name != INTERNAL_PROJECTION_TOOL:
        if raw_receipt is not None:
            raise ValueError(
                "knowledge_projection_internal_admission_tool_mismatch"
            )
        return None
    if not isinstance(raw_receipt, dict):
        raise ValueError(
            "knowledge_projection_internal_admission_required"
        )
    from backend.app.services.knowledge_projection.retrievable.internal_admission import (
        InternalProjectionAdmissionReceipt,
    )
    from backend.app.services.knowledge_projection.retrievable.task_payload import (
        KnowledgeProjectionTaskPayload,
    )
    from backend.app.services.knowledge_projection.retrievable.internal_admission_store import (
        InternalProjectionAdmissionStore,
    )

    receipt = InternalProjectionAdmissionReceipt.model_validate(raw_receipt)
    candidate_payload = dict(inputs)
    for key in (
        "runtime_binding",
        "runtime_id",
        "site_key",
        "target_device_id",
    ):
        candidate_payload.pop(key, None)
    injected_execution_id = candidate_payload.pop("execution_id", None)
    if (
        injected_execution_id is not None
        and str(injected_execution_id) != str(task.execution_id or task.id)
    ):
        raise ValueError(
            "knowledge_projection_internal_admission_identity_mismatch"
        )
    candidate_projection_payload = (
        KnowledgeProjectionTaskPayload.model_validate(candidate_payload)
    )
    projection_payload = KnowledgeProjectionTaskPayload.model_validate(task.params)
    if candidate_projection_payload != projection_payload:
        raise ValueError(
            "knowledge_projection_internal_admission_identity_mismatch"
        )
    payload_sources = projection_payload.source_page
    receipt_sources = receipt.sources
    if (
        receipt.task_id != task.id
        or receipt.task_id != projection_payload.internal_task_id
        or receipt_sources[0].intake_id != projection_payload.intake_id
        or receipt.workspace_id != str(task.workspace_id or "").strip()
        or receipt.workspace_id != projection_payload.workspace_id
        or receipt.group_id != projection_payload.group_id
        or receipt.tenant_id != projection_payload.tenant_id
        or receipt.actor_user_id != projection_payload.actor_user_id
        or receipt.capability_code
        != projection_payload.descriptor.capability_code
        or receipt.descriptor_id
        != projection_payload.descriptor.descriptor_id
        or receipt.descriptor_hash
        != projection_payload.descriptor.descriptor_hash
        or len(receipt_sources) != len(payload_sources)
        or any(
            binding.source_instance_id != source.source_instance_id
            or binding.source_revision != source.source_revision
            or binding.content_hash != source.content_hash
            for binding, source in zip(receipt_sources, payload_sources)
        )
        or receipt.trigger_mode != projection_payload.trigger_mode
    ):
        raise ValueError(
            "knowledge_projection_internal_admission_identity_mismatch"
        )
    if not InternalProjectionAdmissionStore().verify(
        receipt
    ):
        raise ValueError(
            "knowledge_projection_internal_admission_not_committed"
        )
    return receipt, projection_payload


async def park_task_for_runner_admission(
    tasks_store: TasksStore,
    task: Task,
    runner_id: str,
    error: BaseException,
    redis_queue: Optional[RedisRunnerQueueStore] = None,
) -> None:
    """Preserve a task without consuming an execution retry or Deadlettering."""
    latest = tasks_store.get_task(task.id) or task
    ctx = (
        dict(latest.execution_context)
        if isinstance(latest.execution_context, dict)
        else {}
    )
    error_code = str(
        getattr(error, "code", None) or type(error).__name__
    ).strip()
    blocked_at = _utc_now()
    retry_at = blocked_at + timedelta(seconds=RUNNER_ADMISSION_RETRY_SECONDS)
    blocked_payload = {
        "policy": RUNNER_ADMISSION_BLOCKED_REASON,
        "reason": RUNNER_ADMISSION_BLOCKED_REASON,
        "error_code": error_code[:128],
        "blocked_at": blocked_at.isoformat(),
        "defer_until": retry_at.isoformat(),
        "runner_id": runner_id,
    }
    ctx["runner_skip_reason"] = RUNNER_ADMISSION_BLOCKED_REASON
    ctx["status"] = "blocked_admission"
    ctx["workspace_product_admission"] = blocked_payload
    ctx.pop("runner_id", None)
    ctx.pop("heartbeat_at", None)
    tasks_store.update_task(
        latest.id,
        execution_context=ctx,
        status=TaskStatus.PENDING,
        next_eligible_at=retry_at,
        blocked_reason=ADMISSION_DEFERRED_REASON,
        blocked_payload=blocked_payload,
        frontier_state="cold",
        frontier_enqueued_at=None,
        completed_at=None,
        error=None,
        runner_id=None,
        heartbeat_at=None,
    )
    logger.warning(
        "Runner preserved task in admission block task_id=%s playbook=%s "
        "error_code=%s",
        latest.id,
        latest.pack_id,
        error_code,
    )
    if redis_queue:
        await redis_queue.ack_task(latest.id)
