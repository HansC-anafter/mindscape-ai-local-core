from types import SimpleNamespace

import pytest

from backend.app.services.runtime.simple_runtime import SimpleRuntime
from backend.app.services.workflow.execution_profile_retry import (
    resolve_handoff_retry_policy,
)


def _playbook_run(retry_policy):
    playbook_json = SimpleNamespace(
        playbook_code="managed_release",
        execution_profile={"retry_policy": retry_policy},
    )
    metadata = SimpleNamespace(
        kind="user_workflow",
        interaction_mode=["conversational"],
        playbook_code="managed_release",
    )
    return SimpleNamespace(
        playbook_json=playbook_json,
        playbook=SimpleNamespace(metadata=metadata),
    )


def test_execution_profile_retry_zero_is_projected_to_outer_handoff_step():
    playbook_run = _playbook_run(
        {
            "max_retries": 0,
            "retry_delay": 0,
            "exponential_backoff": False,
        }
    )

    plan = SimpleRuntime()._convert_to_handoff_plan(
        playbook_run,
        {"site_key": "yogacookie-app"},
    )

    assert plan.steps[0].retry_policy.max_retries == 0
    assert plan.steps[0].retry_policy.retry_delay == 0
    assert plan.steps[0].retry_policy.exponential_backoff is False


@pytest.mark.parametrize(
    "value",
    [
        {"max_retries": -1},
        {"max_retries": True},
        {"retry_delay": -0.1},
        {"exponential_backoff": "false"},
        {"retryable_errors": ["timeout", 1]},
    ],
)
def test_invalid_execution_profile_retry_policy_fails_closed(value):
    with pytest.raises(
        ValueError,
        match="playbook_execution_retry_policy_invalid",
    ):
        resolve_handoff_retry_policy(
            SimpleNamespace(
                execution_profile={"retry_policy": value}
            )
        )
