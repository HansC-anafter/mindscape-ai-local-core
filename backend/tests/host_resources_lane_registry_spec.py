from backend.app.services.host_resources import lane_registry


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
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("LOCAL_CORE_HOST_RESOURCE_LANES_JSON", raising=False)
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
