import pytest

from backend.app.services.host_resources import queue_utilization_response
from backend.app.services.host_resources.queue_utilization_projection import (
    project_queue_utilization_detail,
    project_queue_utilization_summary,
)


def _snapshot():
    return {
        "source": "live_resource_console",
        "captured_at": "2026-06-21T04:04:40+00:00",
        "captured_at_by_queue_shard": {
            "browser_local": "2026-06-21T04:04:40+00:00",
            "vision_local": "2026-06-21T04:04:40+00:00",
        },
        "queue_depths": {
            "browser_local": {"pending": 0, "processing": 2},
            "vision_local": {"pending": 3, "processing": 1},
        },
        "capacity_by_queue_shard": {
            "browser_local": {"active_runner_count": 2},
            "vision_local": {"active_runner_count": 1},
        },
        "visible_lanes": {
            "browser_local": [{"lane_key": "ready:browser"}],
            "vision_local": [{"lane_key": "ready:vision"}],
        },
        "visible_lane_count": {"browser_local": 1, "vision_local": 1},
        "resource_lanes": {
            "browser_local": [{"lane_key": "resource:browser"}],
            "vision_local": [{"lane_key": "resource:vision"}],
        },
        "resource_lane_count": {"browser_local": 1, "vision_local": 1},
        "active_route_lanes": {
            "browser_local": [{"lane_key": "route:browser"}],
            "vision_local": [{"lane_key": "route:vision"}],
        },
        "active_route_lane_count": {"browser_local": 1, "vision_local": 1},
        "backlog_summary_by_queue_shard": {
            "browser_local": {
                "pending_total": 922,
                "running_total": 2,
                "blocked_total": 917,
                "ready_pending_total": 0,
                "cold_pending_total": 5,
                "unclassified_pending_total": 0,
                "by_blocked_reason": {
                    "concurrency_locked": 679,
                    "workspace_allocation_required": 238,
                },
                "by_pack": {"ig_analyze_following": {"pending": 679}},
            },
            "vision_local": {
                "pending_total": 12,
                "running_total": 1,
                "blocked_total": 9,
                "by_blocked_reason": {"model_capacity_locked": 9},
                "by_pack": {"ig_analyze_pinned_reference": {"pending": 9}},
            },
        },
        "backlog_by_queue_shard": {
            "browser_local": [{"pack_id": "ig_analyze_following"}],
            "vision_local": [{"pack_id": "ig_analyze_pinned_reference"}],
        },
        "freshness_by_queue_shard": {
            "browser_local": {"backlog_source": "postgres_tasks"},
            "vision_local": {"backlog_source": "postgres_tasks"},
        },
        "snapshot_fallback_by_queue_shard": {
            "browser_local": {"queue_depths": {"pending": 0}},
            "vision_local": {"queue_depths": {"pending": 3}},
        },
        "utilization_ratio_by_queue_shard": {
            "browser_local": 1 / 3,
            "vision_local": 1 / 3,
        },
    }


def test_summary_projection_strips_detail_maps_and_compacts_backlog():
    projected = project_queue_utilization_summary(_snapshot())

    assert projected["view"] == "summary"
    assert projected["visible_lanes"] == {}
    assert projected["resource_lanes"] == {}
    assert projected["active_route_lanes"] == {}
    assert projected["backlog_by_queue_shard"] == {}
    assert projected["snapshot_fallback_by_queue_shard"] == {}
    browser_summary = projected["backlog_summary_by_queue_shard"]["browser_local"]
    assert browser_summary["pending_total"] == 922
    assert browser_summary["by_blocked_reason"] == {
        "concurrency_locked": 679,
        "workspace_allocation_required": 238,
    }
    assert browser_summary["by_pack"] == {}


def test_detail_projection_scopes_all_queue_maps_to_one_queue():
    projected = project_queue_utilization_detail(
        _snapshot(),
        queue_shard="browser_local",
    )

    assert projected["view"] == "detail"
    assert projected["queue_shard"] == "browser_local"
    assert set(projected["queue_depths"]) == {"browser_local"}
    assert set(projected["resource_lanes"]) == {"browser_local"}
    assert set(projected["active_route_lanes"]) == {"browser_local"}
    assert set(projected["backlog_by_queue_shard"]) == {"browser_local"}
    assert projected["backlog_summary_by_queue_shard"]["browser_local"]["by_pack"] == {
        "ig_analyze_following": {"pending": 679},
    }


@pytest.mark.asyncio
async def test_response_builder_summary_uses_compact_query(monkeypatch):
    received = {}

    async def _latest(**kwargs):
        received.update(kwargs)
        return _snapshot()

    monkeypatch.setattr(
        queue_utilization_response,
        "get_latest_queue_utilization_snapshot_with_resource_lanes",
        _latest,
    )

    response = await queue_utilization_response.build_queue_utilization_response(
        view="summary",
    )

    assert response["view"] == "summary"
    assert received == {
        "include_backlog_breakdowns": False,
        "include_active_route_lanes": False,
    }


@pytest.mark.asyncio
async def test_response_builder_detail_limits_backlog_query_to_queue(monkeypatch):
    received = {}

    async def _latest(**kwargs):
        received.update(kwargs)
        return _snapshot()

    monkeypatch.setattr(
        queue_utilization_response,
        "get_latest_queue_utilization_snapshot_with_resource_lanes",
        _latest,
    )

    response = await queue_utilization_response.build_queue_utilization_response(
        view="detail",
        queue_shard="vision_local",
    )

    assert response["view"] == "detail"
    assert set(response["queue_depths"]) == {"vision_local"}
    assert received == {"backlog_queue_shards": ["vision_local"]}


@pytest.mark.asyncio
async def test_response_builder_rejects_missing_or_unknown_detail_queue(monkeypatch):
    async def _latest(**_kwargs):
        return _snapshot()

    monkeypatch.setattr(
        queue_utilization_response,
        "get_latest_queue_utilization_snapshot_with_resource_lanes",
        _latest,
    )

    with pytest.raises(ValueError, match="queue_shard_required"):
        await queue_utilization_response.build_queue_utilization_response(view="detail")

    with pytest.raises(ValueError, match="queue_shard_not_found"):
        await queue_utilization_response.build_queue_utilization_response(
            view="detail",
            queue_shard="missing_queue",
        )
