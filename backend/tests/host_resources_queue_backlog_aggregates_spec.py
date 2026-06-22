import pytest

from backend.app.services.host_resources import queue_utilization
from backend.app.services.host_resources.queue_backlog_aggregates import (
    backlog_rows_to_response,
)


def test_backlog_rows_group_task_backlog_without_queue_depth_semantics():
    response = backlog_rows_to_response(
        [
            {
                "queue_shard": "browser_local",
                "pack_id": "ig_analyze_following",
                "status": "pending",
                "frontier_state": "cold",
                "blocked_reason": "concurrency_locked",
                "concurrency_key": "concurrency:profile:a",
                "task_count": 713,
            },
            {
                "queue_shard": "browser_local",
                "pack_id": "ig_pin_post_detail",
                "status": "pending",
                "frontier_state": "",
                "blocked_reason": "",
                "concurrency_key": "",
                "task_count": 5,
            },
            {
                "queue_shard": "browser_local",
                "pack_id": "ig_pin_post_detail",
                "status": "running",
                "frontier_state": "running",
                "blocked_reason": "",
                "concurrency_key": "concurrency:profile:b",
                "task_count": 1,
            },
        ]
    )

    summary = response["backlog_summary_by_queue_shard"]["browser_local"]
    assert summary["pending_total"] == 718
    assert summary["running_total"] == 1
    assert summary["blocked_total"] == 713
    assert summary["unclassified_pending_total"] == 5
    assert summary["by_blocked_reason"] == {"concurrency_locked": 713}
    assert summary["by_pack"]["ig_analyze_following"]["pending"] == 713
    assert summary["by_pack"]["ig_pin_post_detail"] == {"pending": 5, "running": 1}
    assert response["active_route_lane_count"]["browser_local"] == 3


@pytest.mark.asyncio
async def test_resource_console_response_is_live_first_with_db_backlog(monkeypatch):
    async def _fake_live():
        return {
            "source": "live_redis_bounded",
            "captured_at": "2026-06-21T00:00:05+00:00",
            "captured_at_by_queue_shard": {"browser_local": "2026-06-21T00:00:05+00:00"},
            "queue_depths": {
                "browser_local": {"pending": 0, "processing": 2, "delayed": 0, "deadletter": 4},
            },
            "capacity_by_queue_shard": {
                "browser_local": {
                    "active_runner_count": 2,
                    "claimable_runner_count": 2,
                    "claim_blocked_runner_count": 0,
                    "max_inflight_total": 6,
                    "inflight_total": 2,
                    "available_slots_total": 4,
                    "claimable_available_slots_total": 4,
                    "utilization_ratio": 1 / 3,
                    "runner_ids": ["runner-a", "runner-b"],
                },
            },
            "visible_lanes": {"browser_local": []},
            "visible_lane_count": {"browser_local": 0},
            "resource_lanes": {
                "browser_local": [
                    {
                        "lane_key": "runner_profile:browser_local",
                        "lane_type": "runner_profile",
                        "lane_value": "browser_local",
                        "count": 2,
                    }
                ],
            },
            "resource_lane_count": {"browser_local": 1},
            "utilization_ratio_by_queue_shard": {"browser_local": 1 / 3},
            "degraded": False,
            "errors": [],
        }

    def _fake_snapshot(store=None):
        return {
            "source": "postgres_snapshot",
            "captured_at": "2026-06-21T00:00:00+00:00",
            "captured_at_by_queue_shard": {"browser_local": "2026-06-21T00:00:00+00:00"},
            "queue_depths": {
                "browser_local": {"pending": 91, "processing": 3, "delayed": 1, "deadletter": 5},
            },
            "capacity_by_queue_shard": {
                "browser_local": {
                    "active_runner_count": 1,
                    "max_inflight_total": 3,
                    "inflight_total": 3,
                    "available_slots_total": 0,
                    "utilization_ratio": 1,
                    "runner_ids": [],
                },
            },
            "visible_lanes": {"browser_local": []},
            "visible_lane_count": {"browser_local": 0},
            "utilization_ratio_by_queue_shard": {"browser_local": 1},
            "degraded": False,
            "errors": [],
        }

    def _fake_backlog(
        queue_shards=None,
        include_breakdowns=True,
        include_active_routes=True,
    ):
        assert queue_shards == ["browser_local"]
        assert include_breakdowns is True
        assert include_active_routes is True
        return backlog_rows_to_response(
            [
                {
                    "queue_shard": "browser_local",
                    "pack_id": "ig_analyze_following",
                    "status": "pending",
                    "frontier_state": "cold",
                    "blocked_reason": "concurrency_locked",
                    "concurrency_key": "concurrency:profile:a",
                    "task_count": 956,
                }
            ]
        ) | {"errors": []}

    monkeypatch.setattr(queue_utilization, "build_live_queue_utilization", _fake_live)
    monkeypatch.setattr(
        queue_utilization,
        "get_latest_queue_utilization_snapshot",
        _fake_snapshot,
    )
    monkeypatch.setattr(
        queue_utilization,
        "get_queue_backlog_aggregates",
        _fake_backlog,
    )

    response = await queue_utilization.get_latest_queue_utilization_snapshot_with_resource_lanes()

    assert response["source"] == "live_resource_console"
    assert response["queue_depths"]["browser_local"] == {
        "pending": 0,
        "processing": 2,
        "delayed": 0,
        "deadletter": 4,
    }
    assert response["backlog_summary_by_queue_shard"]["browser_local"]["pending_total"] == 956
    assert response["capacity_by_queue_shard"]["browser_local"]["max_inflight_total"] == 6
    assert response["freshness_by_queue_shard"]["browser_local"]["queue_depths_source"] == "live_redis"
    assert response["snapshot_fallback_by_queue_shard"]["browser_local"]["queue_depths"]["pending"] == 91
