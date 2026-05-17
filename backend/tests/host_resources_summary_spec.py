from backend.app.services.host_resources.summary import build_host_resource_summary


def _snapshot():
    return {
        "captured_at": "2026-05-16T00:00:00Z",
        "degraded": False,
        "host": {
            "memory_pressure": {
                "free_percent": 42,
            },
        },
        "capacity": {
            "memory_mb": 10240,
            "reserved_memory_mb": 7168,
        },
        "consumers": [
            {
                "consumer_id": "runner:small",
                "label": "Small Runner",
                "memory_mb": 512,
                "memory_source": "rss",
            },
            {
                "consumer_id": "mlx:qwen",
                "label": "MLX Qwen",
                "memory_mb": 7168,
                "memory_source": "declared",
            },
            {
                "consumer_id": "ollama:process:1",
                "label": "Ollama",
                "memory_mb": 2048,
                "memory_source": "rss",
            },
            {
                "consumer_id": "extra:process:2",
                "label": "Extra",
                "memory_mb": 1024,
                "memory_source": "rss",
            },
        ],
        "lanes": [
            {"lane_id": "lane:busy", "label": "Busy Lane", "state": "busy"},
            {"lane_id": "lane:paused", "label": "Paused Lane", "state": "paused"},
            {"lane_id": "lane:disabled", "label": "Disabled Lane", "state": "disabled"},
            {"lane_id": "lane:available", "label": "Available Lane", "state": "available"},
        ],
    }


def test_summary_contract_uses_stable_compact_fields():
    summary = build_host_resource_summary(_snapshot())

    assert summary == {
        "captured_at": "2026-05-16T00:00:00Z",
        "degraded": False,
        "pressure_state": "ok",
        "free_percent": 42,
        "headroom_mb": 10240,
        "reserved_mb": 7168,
        "lanes": {
            "busy": 1,
            "blocked": 2,
            "total": 4,
        },
        "heavy_consumers": [
            {
                "consumer_id": "mlx:qwen",
                "label": "MLX Qwen",
                "memory_mb": 7168,
                "memory_source": "declared",
            },
            {
                "consumer_id": "ollama:process:1",
                "label": "Ollama",
                "memory_mb": 2048,
                "memory_source": "rss",
            },
            {
                "consumer_id": "extra:process:2",
                "label": "Extra",
                "memory_mb": 1024,
                "memory_source": "rss",
            },
        ],
        "primary_blockers": [
            {
                "lane_id": "lane:paused",
                "label": "Paused Lane",
                "state": "paused",
                "reason": None,
            },
            {
                "lane_id": "lane:disabled",
                "label": "Disabled Lane",
                "state": "disabled",
                "reason": None,
            },
        ],
        "route_controls": {
            "active": 0,
            "draining": 0,
            "targets": [],
        },
        "alerts": [
            {
                "alert_id": "host_resource_lanes_blocked",
                "severity": "warning",
                "message": "2 host resource lane(s) blocked",
                "action_href": "/settings?tab=runtime&section=host-resources",
            }
        ],
        "dashboard_href": "/settings?tab=runtime&section=host-resources",
    }


def test_summary_handles_missing_memory_pressure_without_500():
    summary = build_host_resource_summary({"degraded": False, "host": {}, "capacity": {}, "lanes": []})

    assert summary["pressure_state"] == "unknown"
    assert summary["free_percent"] is None
    assert summary["headroom_mb"] == 0
    assert summary["lanes"] == {"busy": 0, "blocked": 0, "total": 0}
    assert summary["route_controls"] == {"active": 0, "draining": 0, "targets": []}
    assert summary["alerts"] == []


def test_summary_marks_degraded_snapshot_critical():
    summary = build_host_resource_summary({"degraded": True, "host": {"memory_pressure": {"free_percent": 99}}})

    assert summary["pressure_state"] == "critical"
    assert summary["alerts"][0] == {
        "alert_id": "memory_pressure_critical",
        "severity": "critical",
        "message": "Host memory pressure is critical",
        "action_href": "/settings?tab=runtime&section=host-resources",
    }


def test_summary_includes_compact_active_route_controls_without_history_details():
    summary = build_host_resource_summary(
        _snapshot(),
        active_reservations=[
            {
                "reservation_id": "res-1",
                "state": "reserved_waiting",
                "route_request": {
                    "target_lane": "comfyui_runtime:flux2",
                    "drain_policy": "drain_after_current",
                },
            },
            {
                "reservation_id": "res-2",
                "state": "permitted",
                "route_request": {
                    "target_lane": "mlx:qwen9b",
                    "drain_policy": "prefer_available",
                },
            },
            {
                "reservation_id": "res-3",
                "state": "reserved_waiting",
                "route_request": {
                    "target_lane": "comfyui_runtime:flux2",
                    "drain_policy": "drain_after_current",
                },
            },
        ],
    )

    assert summary["route_controls"] == {
        "active": 3,
        "draining": 2,
        "targets": ["comfyui_runtime:flux2", "mlx:qwen9b"],
    }
    assert summary["alerts"][-1] == {
        "alert_id": "route_drain_active",
        "severity": "info",
        "message": "2 route reservation(s) draining",
        "action_href": "/settings?tab=runtime&section=host-resources",
    }


def test_summary_omits_reservation_details():
    source = _snapshot()
    source["reservationHistory"] = [{"reservation_id": "res-1"}]
    source["reservationEvents"] = [{"event_id": "evt-1"}]
    source["candidates"] = [{"id": "candidate-1"}]

    summary = build_host_resource_summary(source)

    assert "reservationHistory" not in summary
    assert "reservationEvents" not in summary
    assert "candidates" not in summary
    assert "reservation_id" not in summary["route_controls"]
    assert len(summary["heavy_consumers"]) == 3
    assert len(summary["primary_blockers"]) <= 3
