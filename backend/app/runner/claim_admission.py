"""Runner claim admission decisions and observability payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.app.runner.worker_db_budget import WorkerDbBudgetDecision
from backend.app.services.runner_topology import (
    resolve_target_runner_profile,
    runner_profile_can_claim_task,
)


@dataclass(frozen=True)
class RunnerClaimAdmissionDecision:
    allow: bool
    reason: str
    action: str = "allow"
    delay_seconds: int = 0
    observability: dict[str, Any] = field(default_factory=dict)
    workspace_quota_payload: dict[str, Any] | None = None


def _clean_string(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _task_context(task: Any) -> dict[str, Any]:
    context = getattr(task, "execution_context", None)
    return context if isinstance(context, dict) else {}


def _task_identity(task: Any) -> dict[str, Any]:
    context = _task_context(task)
    inputs = context.get("inputs")
    if not isinstance(inputs, dict):
        inputs = {}
    return {
        "task_id": _clean_string(getattr(task, "id", None) or context.get("task_id")),
        "workspace_id": _clean_string(
            getattr(task, "workspace_id", None)
            or context.get("workspace_id")
            or inputs.get("workspace_id")
        ),
        "pack_id": _clean_string(
            getattr(task, "pack_id", None)
            or context.get("pack_id")
            or context.get("playbook_code")
        ),
        "task_type": _clean_string(
            getattr(task, "task_type", None)
            or context.get("task_type")
            or context.get("playbook_code")
        ),
        "queue_shard": _clean_string(
            getattr(task, "queue_shard", None) or context.get("queue_shard")
        ),
        "playbook_code": _clean_string(context.get("playbook_code")),
    }


def _resource_observability(resource_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(resource_snapshot, dict):
        return {}
    admission = resource_snapshot.get("admission")
    memory = resource_snapshot.get("memory")
    cpu = resource_snapshot.get("cpu")
    payload: dict[str, Any] = {}
    if isinstance(admission, dict):
        payload["resource_admission_state"] = admission.get("state")
        payload["resource_admission_reasons"] = admission.get("reasons")
    if isinstance(memory, dict):
        payload["memory_working_set_ratio"] = memory.get("working_set_ratio")
    if isinstance(cpu, dict):
        payload["cpu_usage_ratio"] = cpu.get("usage_ratio")
        payload["cpu_throttled_ratio"] = cpu.get("throttled_ratio")
    return payload


def _quota_payload(workspace_quota_decision: Any) -> dict[str, Any] | None:
    if workspace_quota_decision is None:
        return None
    to_dict = getattr(workspace_quota_decision, "to_dict", None)
    if callable(to_dict):
        try:
            result = to_dict()
            return result if isinstance(result, dict) else None
        except Exception:
            return None
    if isinstance(workspace_quota_decision, dict):
        return workspace_quota_decision
    return None


def _base_observability(
    task: Any,
    runner_profile: Any,
    db_budget: WorkerDbBudgetDecision,
    resource_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = _task_identity(task)
    payload.update(
        {
            "runner_profile": _clean_string(getattr(runner_profile, "profile_code", None)),
            "db_budget_reason": db_budget.reason,
            "db_budget_wait_seconds": db_budget.wait_seconds,
        }
    )
    payload.update(_resource_observability(resource_snapshot))
    return payload


def decide_runner_claim_admission(
    task: Any,
    runner_profile: Any,
    db_budget: WorkerDbBudgetDecision,
    resource_snapshot: dict[str, Any] | None,
    *,
    workspace_quota_decision: Any = None,
) -> RunnerClaimAdmissionDecision:
    """Return the single runner claim admission decision for a rehydrated task."""

    observability = _base_observability(
        task,
        runner_profile,
        db_budget,
        resource_snapshot,
    )

    if not db_budget.allow_claim_scan:
        return RunnerClaimAdmissionDecision(
            allow=False,
            reason=db_budget.reason or "db_budget_claim_scan_paused",
            action="delay",
            delay_seconds=max(1, int(db_budget.wait_seconds or 1)),
            observability=observability,
        )

    if not runner_profile_can_claim_task(runner_profile, task):
        observability["target_runner_profile"] = resolve_target_runner_profile(task)
        return RunnerClaimAdmissionDecision(
            allow=False,
            reason="runner_profile_mismatch",
            action="delay",
            delay_seconds=5,
            observability=observability,
        )

    quota_payload = _quota_payload(workspace_quota_decision)
    quota_allow = getattr(workspace_quota_decision, "allow", None)
    if quota_payload is not None:
        observability["workspace_quota_admission"] = quota_payload
    if quota_allow is False:
        reason = _clean_string(getattr(workspace_quota_decision, "reason", None))
        return RunnerClaimAdmissionDecision(
            allow=False,
            reason=reason or "workspace_quota_blocked",
            action="park",
            delay_seconds=10,
            observability=observability,
            workspace_quota_payload=quota_payload,
        )

    return RunnerClaimAdmissionDecision(
        allow=True,
        reason="allowed",
        action="allow",
        delay_seconds=0,
        observability=observability,
    )
