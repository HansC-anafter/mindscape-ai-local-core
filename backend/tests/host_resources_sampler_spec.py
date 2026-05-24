import pytest

from backend.app.services.host_resources.route_intents import build_route_intent_preview
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
async def test_route_intent_preview_uses_manifest_declared_comfyui_lane(monkeypatch, tmp_path):
    import backend.app.services.host_resources.lane_registry as lane_registry
    import backend.app.services.host_resources.route_intents as route_intents

    async def _snapshot(refresh=False):
        return snapshot_from_probe(_probe_payload())

    async def _candidate_previews(reservations, scan_limit=25):
        return {
            "preview": {
                "matching_candidates": [
                    {
                        "task_id": "render-1",
                        "score": 100,
                    }
                ]
            }
        }

    capability_dir = tmp_path / "capabilities" / "comfyui_runtime"
    capability_dir.mkdir(parents=True)
    (capability_dir / "manifest.yaml").write_text(
        """
host_resource_lanes:
  comfyui_runtime:flux2_klein_true_v2_q6_local:
    label: Flux.2 Klein True V2 Q6 Local
    kind: generation_lane
    resource_flavor: local.mps.comfyui
    profile_id: vr_flux2_klein_true_v2_q6_local
    requirements:
      memory_mb: 18432
      memory_source: declared_manifest_model_footprint
      exclusive_groups:
        - apple_metal_heavy
        - comfyui_generation
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(route_intents, "get_host_resource_snapshot", _snapshot)
    monkeypatch.setattr(route_intents, "build_route_reservation_candidate_previews", _candidate_previews)
    monkeypatch.setattr(lane_registry, "_capabilities_dir", lambda: tmp_path / "capabilities")

    preview = await build_route_intent_preview(
        {
            "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
            "include_candidates": True,
            "refresh": True,
        }
    )
    intent = preview["route_intent"]
    route_preview = preview["route_intent_preview"]

    assert intent["resource_flavor"] == "local.mps.comfyui"
    assert intent["resource_groups"] == ["apple_metal_heavy", "comfyui_generation"]
    assert route_preview["decision"] == "preview_ready"
    assert route_preview["estimated_memory_mb"] == 18432
    assert route_preview["pressure_delta"]["headroom_after_mb"] == 3072
    assert route_preview["matching_candidates"][0]["task_id"] == "render-1"
    assert route_preview["reservation_payload"]["route_request"]["drain_policy"] == "drain_after_current"


@pytest.mark.asyncio
async def test_route_intent_preview_rejects_unknown_lane_without_reservation_payload():
    preview = await build_route_intent_preview({"target_lane": "unknown:lane"})

    route_preview = preview["route_intent_preview"]
    assert route_preview["decision"] == "unknown_lane"
    assert route_preview["reason"] == "target_lane_not_declared"
    assert route_preview["reservation_payload"] is None


@pytest.mark.asyncio
async def test_route_intent_preview_keeps_reservation_payload_when_candidate_scan_times_out(monkeypatch, tmp_path):
    import asyncio

    import backend.app.services.host_resources.lane_registry as lane_registry
    import backend.app.services.host_resources.route_intents as route_intents

    async def _snapshot(refresh=False):
        return snapshot_from_probe(_probe_payload())

    async def _slow_candidate_previews(reservations, scan_limit=25):
        await asyncio.sleep(0.3)
        return {}

    capability_dir = tmp_path / "capabilities" / "comfyui_runtime"
    capability_dir.mkdir(parents=True)
    (capability_dir / "manifest.yaml").write_text(
        """
host_resource_lanes:
  comfyui_runtime:flux2_klein_true_v2_q6_local:
    label: Flux.2 Klein True V2 Q6 Local
    kind: generation_lane
    resource_flavor: local.mps.comfyui
    profile_id: vr_flux2_klein_true_v2_q6_local
    requirements:
      memory_mb: 18432
      memory_source: declared_manifest_model_footprint
      exclusive_groups:
        - apple_metal_heavy
        - comfyui_generation
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(route_intents, "get_host_resource_snapshot", _snapshot)
    monkeypatch.setattr(route_intents, "build_route_reservation_candidate_previews", _slow_candidate_previews)
    monkeypatch.setattr(lane_registry, "_capabilities_dir", lambda: tmp_path / "capabilities")

    preview = await build_route_intent_preview(
        {
            "target_lane": "comfyui_runtime:flux2_klein_true_v2_q6_local",
            "include_candidates": True,
            "refresh": True,
            "candidate_preview_timeout_seconds": 0.01,
        }
    )

    route_preview = preview["route_intent_preview"]
    assert route_preview["decision"] == "preview_ready"
    assert route_preview["reservation_payload"]["route_request"]["target_lane"] == "comfyui_runtime:flux2_klein_true_v2_q6_local"
    assert route_preview["matching_candidates"] == []
    assert route_preview["preview_errors"][0]["source"] == "candidate_preview"
    assert route_preview["preview_errors"][0]["error"] == "TimeoutError"


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
