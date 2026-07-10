import pytest

from backend.app.runner.resource_failure_policy import (
    decide_resource_failure,
    is_resource_block_reason,
)


@pytest.mark.parametrize(
    ("source", "action", "reason", "auto_requeue"),
    [
        ("browser_resource_lease", "resource_wait", "resource_wait", True),
        ("runner_cgroup_oom_correlated", "resource_block", "resource_exhausted", False),
        ("unclassified_sigkill", "resource_block", "unclassified_sigkill", False),
        ("resource_ownership_lost", "resource_block", "resource_ownership_lost", False),
        ("browser_launch_timeout", "normal_retry", None, True),
    ],
)
def test_resource_failure_decision_table(source, action, reason, auto_requeue):
    decision = decide_resource_failure(source)
    assert decision.action == action
    assert decision.blocked_reason == reason
    assert decision.auto_requeue is auto_requeue
    assert decision.consumes_workflow_retry is (action == "normal_retry")


def test_only_terminal_resource_block_reasons_are_restart_protected():
    assert is_resource_block_reason("resource_exhausted") is True
    assert is_resource_block_reason("resource_wait") is False
    assert is_resource_block_reason(None) is False


def test_sigkill_without_a_persisted_resource_contract_uses_bounded_retry():
    decision = decide_resource_failure(
        "unclassified_sigkill",
        resource_contract_available=False,
    )
    assert decision.action == "normal_retry"
    assert decision.consumes_workflow_retry is True
