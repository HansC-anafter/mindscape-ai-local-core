import inspect
from types import SimpleNamespace

import pytest

from backend.app.runner.browser_claim_fairness import (
    commit_browser_fairness_after_claim,
)
from backend.app.runner.worker_claim_policy import (
    _dequeue_by_browser_fair_candidate_policy,
)
from backend.app.runner.worker_dispatch import _dispatch_claimed_task
from backend.tests.runner.worker_playbook_fairness_support import (
    FOLLOWING_PLAYBOOK,
    FakeFairQueue,
    browser_profile,
    compute_profile,
)


def _claimed_task():
    return SimpleNamespace(
        id="task-following",
        pack_id=FOLLOWING_PLAYBOOK,
        queue_shard="browser_local",
        execution_context={"playbook_code": FOLLOWING_PLAYBOOK},
    )


@pytest.mark.asyncio
async def test_successful_browser_claim_commits_actual_lane_once():
    queue = FakeFairQueue([])

    committed = await commit_browser_fairness_after_claim(
        _claimed_task(),
        queue,
        runner_profile=browser_profile(),
    )

    assert committed is True
    assert len(queue.client.setex_calls) == 1
    assert queue.client.setex_calls[0][2] == FOLLOWING_PLAYBOOK


@pytest.mark.asyncio
async def test_non_browser_claim_does_not_commit_lane_cursor():
    queue = FakeFairQueue([])

    committed = await commit_browser_fairness_after_claim(
        _claimed_task(),
        queue,
        runner_profile=compute_profile(),
    )

    assert committed is False
    assert queue.client.setex_calls == []


@pytest.mark.asyncio
async def test_cursor_write_failure_is_fail_soft_after_claim():
    queue = FakeFairQueue([])

    async def fail_setex(*args, **kwargs):
        raise RuntimeError("redis unavailable")

    queue.client.setex = fail_setex

    committed = await commit_browser_fairness_after_claim(
        _claimed_task(),
        queue,
        runner_profile=browser_profile(),
    )

    assert committed is False


def test_production_seams_commit_only_after_db_claim():
    selection_source = inspect.getsource(_dequeue_by_browser_fair_candidate_policy)
    dispatch_source = inspect.getsource(_dispatch_claimed_task)

    assert "write_browser_fairness_cursor" not in selection_source
    assert dispatch_source.index("tasks_store.try_claim_task") < dispatch_source.index(
        "commit_browser_fairness_after_claim"
    )
