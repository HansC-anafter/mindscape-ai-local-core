from backend.app.services.host_resources import lane_registry


def test_manifest_overlay_cache_reuses_unchanged_signature(monkeypatch, tmp_path):
    lane_registry.clear_lane_registry_cache()
    capability_dir = tmp_path / "capabilities" / "ig"
    capability_dir.mkdir(parents=True)
    (capability_dir / "manifest.yaml").write_text(
        """
host_resource_lanes:
  runner:vision_mlx_high:
    label: Vision MLX High
""",
        encoding="utf-8",
    )
    calls = {"count": 0}

    def _safe_load(raw):
        calls["count"] += 1
        return {
            "host_resource_lanes": {
                "runner:vision_mlx_high": {"label": "Vision MLX High"}
            }
        }

    monkeypatch.setattr(
        lane_registry,
        "_capabilities_dir",
        lambda: tmp_path / "capabilities",
    )
    monkeypatch.setattr(lane_registry.yaml, "safe_load", _safe_load)

    first = lane_registry._load_manifest_lane_overlays()
    second = lane_registry._load_manifest_lane_overlays()

    assert calls["count"] == 1
    assert first == second


def test_list_host_resource_lanes_uses_registry_when_snapshot_missing(monkeypatch):
    from backend.app.services.host_resources import manager

    monkeypatch.setattr(manager, "_cached_snapshot", None)
    monkeypatch.setattr(
        manager,
        "load_lane_registry",
        lambda: {"runner:test": {"lane_id": "runner:test"}},
    )
    monkeypatch.setattr(
        manager,
        "degraded_snapshot",
        lambda reason: (_ for _ in ()).throw(AssertionError(reason)),
    )

    assert manager.list_host_resource_lanes() == [{"lane_id": "runner:test"}]


def test_manifest_overlay_declares_flux2_klein_lane(monkeypatch, tmp_path):
    capability_dir = tmp_path / "capabilities" / "comfyui_runtime"
    capability_dir.mkdir(parents=True)
    (capability_dir / "manifest.yaml").write_text(
        """
host_resource_lanes:
  comfyui_runtime:flux2_klein_true_v2_q6_local:
    label: Flux.2 Klein True V2 Q6 Local
    kind: image_generation
    requirements:
      memory_mb: 18432
      memory_source: declared_manifest_model_footprint
      exclusive_groups:
        - apple_metal_heavy
    resource_flavor: local.mps.comfyui
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        lane_registry,
        "_capabilities_dir",
        lambda: tmp_path / "capabilities",
    )

    lanes = lane_registry.load_lane_registry()
    lane = lanes["comfyui_runtime:flux2_klein_true_v2_q6_local"]

    assert lane["requirements"]["memory_mb"] == 18432
    assert lane["requirements"]["memory_source"] == "declared_manifest_model_footprint"
    assert "apple_metal_heavy" in lane["requirements"]["exclusive_groups"]
    assert lane["resource_flavor"] == "local.mps.comfyui"


def test_default_registry_keeps_pack_specific_lanes_out_of_core(monkeypatch, tmp_path):
    monkeypatch.setattr(
        lane_registry,
        "_capabilities_dir",
        lambda: tmp_path / "capabilities",
    )

    lanes = lane_registry.load_lane_registry()

    assert "runner:default_local_browser" in lanes
    assert "runner:default_local" not in lanes
    assert "comfyui_runtime:flux2_klein_true_v2_q6_local" not in lanes
    assert "mlx:qwen9b_4bit_vision" not in lanes


def test_registry_merges_dynamic_lanes(monkeypatch, tmp_path):
    monkeypatch.setattr(
        lane_registry,
        "_capabilities_dir",
        lambda: tmp_path / "capabilities",
    )
    monkeypatch.setattr(
        lane_registry,
        "list_dynamic_lanes",
        lambda: [
            {
                "lane_id": "runner:vision_mlx_high",
                "label": "Vision MLX High",
                "kind": "vision_analyze",
                "queue_shard": "vision_mlx_high",
                "capability_scope": "ig",
            }
        ],
    )

    lanes = lane_registry.load_lane_registry()

    assert lanes["runner:vision_mlx_high"]["queue_shard"] == "vision_mlx_high"
