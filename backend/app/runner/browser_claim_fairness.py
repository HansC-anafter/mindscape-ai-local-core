"""Commit browser fairness only after canonical task claim succeeds."""

from __future__ import annotations

import logging
from typing import Any

from backend.app.runner.browser_fair_candidate_scheduler import (
    normalize_browser_lane_key,
)
from backend.app.runner.browser_fairness_cursor import (
    write_browser_fairness_cursor,
)
from backend.app.runner.resource_pressure import is_browser_resource_profile


logger = logging.getLogger("backend.app.runner.worker")


async def commit_browser_fairness_after_claim(
    task: Any,
    queue_store: Any,
    *,
    runner_profile: Any,
) -> bool:
    """Commit the actual claimed browser lane without affecting claim truth."""

    if not is_browser_resource_profile(runner_profile):
        return False
    context = (
        task.execution_context
        if isinstance(getattr(task, "execution_context", None), dict)
        else {}
    )
    lane_key = normalize_browser_lane_key(
        getattr(task, "pack_id", None),
        context.get("playbook_code"),
    )
    queue_shard = str(
        getattr(queue_store, "pack_id", None)
        or getattr(task, "queue_shard", None)
        or ""
    ).strip()
    if not lane_key or not queue_shard:
        return False
    try:
        client = await queue_store._get_client()
        if client is None:
            raise RuntimeError("browser_fairness_redis_unavailable")
        return await write_browser_fairness_cursor(
            client,
            queue_shard=queue_shard,
            lane_key=lane_key,
        )
    except Exception as exc:
        logger.warning(
            "[Worker] Failed to commit browser fairness after claim "
            "task_id=%s queue=%s lane=%s: %s",
            getattr(task, "id", None),
            queue_shard,
            lane_key,
            exc,
        )
        return False


__all__ = ["commit_browser_fairness_after_claim"]
