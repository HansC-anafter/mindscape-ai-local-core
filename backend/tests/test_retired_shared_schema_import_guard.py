from pathlib import Path


LOCAL_CORE_ROOT = next(
    parent
    for parent in Path(__file__).resolve().parents
    if parent.name == "mindscape-ai-local-core"
)


def test_runtime_code_does_not_import_retired_shared_schema_contracts() -> None:
    retired_imports = (
        "from shared.schemas.pose_signal import",
        "from shared.schemas.visual_signal import",
        "from shared.schemas.storyboard import",
        "from shared.schemas.spatial_scheduling import",
        "from shared.schemas.motion_artifact_refs import",
        "from shared.schemas.motion_constraint_bundle import",
        "from shared.schemas.motion_generation_contract import",
        "from shared.schemas.motion_generation_receipt import",
        "from backend.shared.schemas.storyboard import",
        "from backend.shared.schemas.spatial_scheduling import",
        "from backend.shared.schemas.motion_artifact_refs import",
        "from backend.shared.schemas.motion_constraint_bundle import",
        "from backend.shared.schemas.motion_generation_contract import",
        "from backend.shared.schemas.motion_generation_receipt import",
        "backend.shared.schemas.storyboard",
        "backend.shared.schemas.spatial_scheduling",
        "backend.shared.schemas.motion_artifact_refs",
        "backend.shared.schemas.motion_constraint_bundle",
        "backend.shared.schemas.motion_generation_contract",
        "backend.shared.schemas.motion_generation_receipt",
    )
    offenders: list[str] = []
    for root in (
        LOCAL_CORE_ROOT / "backend" / "app",
        LOCAL_CORE_ROOT / "backend" / "features",
    ):
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if path.name.startswith("._"):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if any(pattern in text for pattern in retired_imports):
                offenders.append(str(path.relative_to(LOCAL_CORE_ROOT)))

    assert offenders == []
