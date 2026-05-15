import pytest

from backend.app.services.host_resources.advisor import build_admission_preview
from backend.app.services.host_resources.samplers import degraded_snapshot, snapshot_from_probe


def _probe_payload():
    return {
        "sampled_at": "2026-05-12T00:00:00Z",
        "platform": "darwin",
        "host": {
            "total_memory_bytes": 38654705664,
            "cpu_count": 10,
        },
        "probes": {
            "memory_pressure": {
                "ok": True,
                "parsed": {
                    "free_percent": 35,
                    "swapins": 1,
                    "swapouts": 2,
                },
            },
            "process_census": {
                "ok": True,
                "parsed": [
                    {
                        "pid": 79870,
                        "ppid": 79004,
                        "cpu_percent": 1.0,
                        "memory_percent": 0.1,
                        "rss_kb": 52800,
                        "vsz_kb": 420933568,
                        "command": "/opt/miniconda3/bin/python",
                        "args": "/opt/miniconda3/bin/python -m mlx_vlm.server --port 8210 --host 0.0.0.0",
                    }
                ],
            },
        },
    }


def test_snapshot_marks_mlx_consumer_as_declared_unified_memory_reservation():
    snapshot = snapshot_from_probe(_probe_payload())

    assert snapshot["degraded"] is False
    assert snapshot["host"]["memory_pressure"]["free_percent"] == 35
    assert snapshot["consumers"][0]["consumer_id"] == "mlx:qwen9b_4bit_vision"
    assert snapshot["consumers"][0]["memory_mb"] == 7168
    assert snapshot["consumers"][0]["memory_source"] == "declared"


def test_degraded_snapshot_marks_lanes_degraded():
    snapshot = degraded_snapshot("bridge unavailable")

    assert snapshot["degraded"] is True
    assert snapshot["lanes"]
    assert {lane["state"] for lane in snapshot["lanes"]} == {"degraded"}


@pytest.mark.asyncio
async def test_admission_preview_defers_declared_comfyui_lane_when_mlx_group_busy(monkeypatch):
    import backend.app.services.host_resources.advisor as advisor

    async def _snapshot(refresh=False):
        return snapshot_from_probe(_probe_payload())

    monkeypatch.setattr(advisor, "get_host_resource_snapshot", _snapshot)
    monkeypatch.delenv("LOCAL_CORE_HOST_RESOURCE_LANES_JSON", raising=False)

    preview = await build_admission_preview(
        lane_id="comfyui_runtime:flux2_klein_true_v2_q6_local"
    )

    assert preview["allow"] is False
    assert preview["decision"] == "defer"
    assert preview["reason"] == "exclusive_group_busy"
    assert preview["required"]["memory_mb"] == 18432


@pytest.mark.asyncio
async def test_admission_preview_does_not_allow_unknown_lane_requirements_from_override(monkeypatch):
    import json

    import backend.app.services.host_resources.advisor as advisor

    async def _snapshot(refresh=False):
        return snapshot_from_probe(_probe_payload())

    monkeypatch.setattr(advisor, "get_host_resource_snapshot", _snapshot)
    monkeypatch.setenv(
        "LOCAL_CORE_HOST_RESOURCE_LANES_JSON",
        json.dumps(
            {
                "comfyui_runtime:flux2_klein_true_v2_q6_local": {
                    "requirements": {
                        "memory_mb": None,
                        "memory_source": "unknown",
                    }
                }
            }
        ),
    )

    preview = await build_admission_preview(
        lane_id="comfyui_runtime:flux2_klein_true_v2_q6_local"
    )

    assert preview["allow"] is False
    assert preview["decision"] == "unknown_requirements"
    assert preview["reason"] == "memory_requirement_unknown"


def test_route_reservation_normalizes_flat_payload_and_cancels_persisted(monkeypatch):
    import backend.app.services.host_resources.manager as manager

    persisted: dict[str, dict] = {}
    manager._route_reservations.clear()
    monkeypatch.setattr(manager, "_read_json_map", lambda key: dict(persisted))
    monkeypatch.setattr(
        manager,
        "_write_json_map",
        lambda key, value: (persisted.clear(), persisted.update(value)),
    )

    reservation = manager.create_route_reservation(
        {
            "lane_id": "mlx:qwen9b_4bit_vision",
            "resource_groups": ["mlx_vision_llm"],
            "note": "operator selected",
        }
    )

    assert reservation["route_request"]["target_lane"] == "mlx:qwen9b_4bit_vision"
    assert reservation["route_request"]["resource_groups"] == ["mlx_vision_llm"]

    manager._route_reservations.clear()
    cancelled = manager.cancel_route_reservation(reservation["reservation_id"])

    assert cancelled["state"] == "cancelled"
    assert persisted[reservation["reservation_id"]]["state"] == "cancelled"
