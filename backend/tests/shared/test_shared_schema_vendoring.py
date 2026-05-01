from pathlib import Path


LOCAL_CORE_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "mindscape-ai-local-core"
)


def test_owner_pack_pose_and_visual_contracts_are_not_host_vendored() -> None:
    shared_schemas = LOCAL_CORE_ROOT / "backend" / "shared" / "schemas"

    assert not (shared_schemas / "pose_signal.py").exists()
    assert not (shared_schemas / "visual_signal.py").exists()


def test_creative_pipeline_contracts_are_not_host_vendored() -> None:
    shared_schemas = LOCAL_CORE_ROOT / "backend" / "shared" / "schemas"

    assert not (shared_schemas / "storyboard.py").exists()
    assert not (shared_schemas / "spatial_scheduling.py").exists()
    assert not (shared_schemas / "motion_artifact_refs.py").exists()
    assert not (shared_schemas / "motion_constraint_bundle.py").exists()
    assert not (shared_schemas / "motion_generation_contract.py").exists()
    assert not (shared_schemas / "motion_generation_receipt.py").exists()
