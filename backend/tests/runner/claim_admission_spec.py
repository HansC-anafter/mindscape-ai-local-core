from dataclasses import dataclass

from backend.app.runner.claim_admission import decide_runner_claim_admission
from backend.app.runner.worker_db_budget import WorkerDbBudgetDecision
from backend.app.services.runner_topology.profile_registry import RunnerProfile


@dataclass
class _Task:
    id: str = "task-1"
    workspace_id: str = "workspace-1"
    pack_id: str = "ig_analyze_following"
    task_type: str = "playbook_execution"
    queue_shard: str = "default_local"
    execution_context: dict | None = None


@dataclass
class _QuotaDecision:
    allow: bool
    reason: str = "workspace_allocation_quota_exhausted"

    def to_dict(self):
        return {
            "allow": self.allow,
            "reason": self.reason,
            "active_count": 2,
            "max_parallel_task_claims": 2,
        }


def _profile(*, code="default_local", partitions=("default_local",)):
    return RunnerProfile(
        profile_code=code,
        display_name=code,
        dispatch_mode="docker_local",
        accepted_resource_classes=("compute",),
        accepted_queue_partitions=partitions,
        max_inflight=2,
    )


def _budget(**overrides):
    values = {
        "allow_claim_scan": True,
        "claim_scan_limit_multiplier": 1.0,
        "allow_release_maintenance": True,
        "allow_postgres_heartbeat": True,
        "wait_seconds": 0,
        "reason": "open",
    }
    values.update(overrides)
    return WorkerDbBudgetDecision(**values)


def test_claim_admission_allows_default_open_path():
    decision = decide_runner_claim_admission(
        _Task(),
        _profile(),
        _budget(),
        {"admission": {"state": "open"}, "memory": {"working_set_ratio": 0.25}},
    )

    assert decision.allow is True
    assert decision.reason == "allowed"
    assert decision.observability["workspace_id"] == "workspace-1"
    assert decision.observability["pack_id"] == "ig_analyze_following"
    assert decision.observability["queue_shard"] == "default_local"
    assert decision.observability["resource_admission_state"] == "open"


def test_claim_admission_delays_when_db_budget_pauses_claim_scan():
    decision = decide_runner_claim_admission(
        _Task(),
        _profile(),
        _budget(
            allow_claim_scan=False,
            claim_scan_limit_multiplier=0.0,
            wait_seconds=3,
            reason="pgbouncer_client_waiting",
        ),
        None,
    )

    assert decision.allow is False
    assert decision.action == "delay"
    assert decision.reason == "pgbouncer_client_waiting"
    assert decision.delay_seconds == 3
    assert decision.observability["db_budget_reason"] == "pgbouncer_client_waiting"


def test_claim_admission_delays_runner_profile_mismatch():
    task = _Task(queue_shard="browser_local")

    decision = decide_runner_claim_admission(
        task,
        _profile(code="default_local", partitions=("default_local",)),
        _budget(),
        None,
    )

    assert decision.allow is False
    assert decision.action == "delay"
    assert decision.reason == "runner_profile_mismatch"
    assert decision.delay_seconds == 5
    assert decision.observability["target_runner_profile"] == "browser_local"


def test_claim_admission_parks_workspace_quota_deny_with_payload():
    quota = _QuotaDecision(allow=False)

    decision = decide_runner_claim_admission(
        _Task(),
        _profile(),
        _budget(reason="pgbouncer_client_active_budget"),
        None,
        workspace_quota_decision=quota,
    )

    assert decision.allow is False
    assert decision.action == "park"
    assert decision.reason == "workspace_allocation_quota_exhausted"
    assert decision.delay_seconds == 10
    assert decision.workspace_quota_payload == quota.to_dict()
    assert decision.observability["workspace_quota_admission"] == quota.to_dict()
    assert decision.observability["db_budget_reason"] == "pgbouncer_client_active_budget"
