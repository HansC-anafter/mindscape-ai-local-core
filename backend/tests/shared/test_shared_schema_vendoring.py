import importlib


def test_storyboard_vendor_exposes_character_adapter_slot() -> None:
    module = importlib.import_module("backend.shared.schemas.storyboard")

    assert hasattr(module, "CharacterAdapterSlot")


def test_shared_pose_signal_vendor_is_importable() -> None:
    module = importlib.import_module("backend.shared.schemas.pose_signal")

    assert hasattr(module, "__all__")
