from pathlib import Path
import sys

LOCAL_CORE_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "mindscape-ai-local-core"
)
BACKEND_ROOT = LOCAL_CORE_ROOT / "backend"
for candidate in (LOCAL_CORE_ROOT, BACKEND_ROOT):
    candidate_str = str(candidate)
    if candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

from backend.app.capabilities.multi_media_studio.services.adapters.vr_adapter import (
    VRAdapter,
    _should_forward_comfy_address,
)
from shared.schemas.storyboard import (
    DirectionIR,
    ObjectAssetRef,
    ObjectUsageBinding,
    ObjectWorkloadSnapshot,
    RenderProfile,
    Scene,
    SceneIntent,
)


def test_should_not_forward_default_local_preview_comfy_addresses():
    assert _should_forward_comfy_address("") is False
    assert _should_forward_comfy_address("http://localhost:8188") is False
    assert _should_forward_comfy_address("http://localhost:8188/") is False
    assert _should_forward_comfy_address("http://127.0.0.1:8188") is False
    assert _should_forward_comfy_address("http://127.0.0.1:8188/") is False
    assert _should_forward_comfy_address("http://host.docker.internal:8188") is True


def test_object_asset_becomes_reference_image_for_preview_when_scene_has_no_explicit_reference():
    scene = Scene(
        scene_id="sc_object_preview",
        direction_ir=DirectionIR(
            intent=SceneIntent(),
            source_reference_ids=["ig_ref_scene"],
        ),
        object_assets=[
            ObjectAssetRef(
                asset_ref={"storage_key": "objects/dress_form.png"},
                object_target_id="dress_form",
                object_instance_id="obj_dress_form",
            )
        ],
    )
    profile = RenderProfile(profile_id="vr_preview_local")

    manifest = VRAdapter()._build_scene_manifest(scene, profile)

    assert manifest["primary_object_asset"] == {"storage_key": "objects/dress_form.png"}
    assert manifest["reference_image"] == {"storage_key": "objects/dress_form.png"}
    assert manifest["object_assets"][0]["object_instance_id"] == "obj_dress_form"


def test_explicit_scene_manifest_reference_image_is_not_overridden_by_object_asset():
    scene = Scene(
        scene_id="sc_object_preview_explicit_ref",
        scene_manifest={"reference_image": {"reference_id": "explicit_ref"}},
        object_assets=[
            ObjectAssetRef(
                asset_ref={"storage_key": "objects/dress_form.png"},
                object_target_id="dress_form",
                object_instance_id="obj_dress_form",
            )
        ],
    )
    profile = RenderProfile(profile_id="vr_preview_local")

    manifest = VRAdapter()._build_scene_manifest(scene, profile)

    assert manifest["primary_object_asset"] == {"storage_key": "objects/dress_form.png"}
    assert manifest["reference_image"] == {"reference_id": "explicit_ref"}


def test_object_workload_snapshot_is_forwarded_with_impact_region_metadata():
    scene = Scene(
        scene_id="sc_object_contract_forwarding",
        object_workload_snapshot=ObjectWorkloadSnapshot(
            source_scene_id="SC_SOURCE_01",
            usage_bindings=[ObjectUsageBinding(scene_id="A01")],
            impact_region_mode="contact_zone",
            impact_region_bbox={"x": 12, "y": 18, "width": 96, "height": 104},
            impact_region_confidence=0.71,
            affected_object_instance_ids=["obj_dress_form", "obj_person_main"],
            quality_gate_state="auto_approved",
        ),
    )
    profile = RenderProfile(profile_id="vr_preview_local")

    manifest = VRAdapter()._build_scene_manifest(scene, profile)

    snapshot = manifest["_object_contract"]["object_workload_snapshot"]
    assert snapshot["impact_region_mode"] == "contact_zone"
    assert snapshot["quality_gate_state"] == "auto_approved"
    assert snapshot["affected_object_instance_ids"] == [
        "obj_dress_form",
        "obj_person_main",
    ]
