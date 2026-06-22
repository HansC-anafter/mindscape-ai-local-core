from types import SimpleNamespace

from backend.app.services.host_resources.workspace_quota_admission import (
    WORKSPACE_ALLOCATION_REQUIRED_REASON,
    WORKSPACE_QUOTA_EXHAUSTED_REASON,
    decide_workspace_quota_admission_for_task,
)


def _task(**overrides):
    payload = {
        "id": "task-1",
        "workspace_id": "ws-1",
        "queue_shard": "default_local_browser",
        "pack_id": "ig_pin_post_detail",
        "task_type": "ig_pin_post_detail",
        "execution_context": {"playbook_code": "ig_pin_post_detail"},
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


class _AllocationStore:
    def __init__(self, allocations):
        self.allocations = allocations

    def list_allocations(self, **kwargs):
        self.kwargs = kwargs
        return self.allocations


class _UsageStore:
    def __init__(self, active_count):
        self.active_count = active_count

    def count_active_tasks(self, **kwargs):
        self.kwargs = kwargs
        return self.active_count


def _allocation(**overrides):
    payload = {
        "allocation_id": "alloc-1",
        "workspace_id": "ws-1",
        "queue_shard": "default_local_browser",
        "task_family": "browser_batch",
        "state": "enabled",
        "max_parallel_task_claims": 3,
        "metadata": {"task_selectors": ["ig_batch_pin_references", "ig_pin_post_detail"]},
    }
    payload.update(overrides)
    return payload


def test_workspace_quota_allows_task_when_allocation_has_available_parallel_slot():
    decision = decide_workspace_quota_admission_for_task(
        _task(),
        allocation_store=_AllocationStore([_allocation()]),
        usage_store=_UsageStore(active_count=2),
    )

    assert decision.allow is True
    assert decision.reason == "workspace_allocation_available"
    assert decision.active_count == 2
    assert decision.max_parallel_task_claims == 3


def test_workspace_quota_defers_task_when_parallel_quota_is_exhausted():
    decision = decide_workspace_quota_admission_for_task(
        _task(),
        allocation_store=_AllocationStore([_allocation()]),
        usage_store=_UsageStore(active_count=3),
    )

    assert decision.allow is False
    assert decision.reason == WORKSPACE_QUOTA_EXHAUSTED_REASON
    assert decision.active_count == 3


def test_workspace_quota_requires_matching_allocation_for_workspace_queue_family():
    decision = decide_workspace_quota_admission_for_task(
        _task(),
        allocation_store=_AllocationStore([]),
        usage_store=_UsageStore(active_count=0),
    )

    assert decision.allow is False
    assert decision.reason == WORKSPACE_ALLOCATION_REQUIRED_REASON


def test_workspace_quota_does_not_block_tasks_without_route_identity():
    decision = decide_workspace_quota_admission_for_task(
        _task(workspace_id=None, queue_shard=None),
        allocation_store=_AllocationStore([]),
        usage_store=_UsageStore(active_count=0),
    )

    assert decision.allow is True
    assert decision.reason == "workspace_quota_identity_not_available"
