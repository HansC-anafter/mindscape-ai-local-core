"""Compatibility re-export for the canonical LAF-owned pose contract."""

from __future__ import annotations

from importlib import import_module


def _load_pose_signal_module():
    for module_name in (
        "capabilities.layer_asset_forge.schema.pose_signal",
        "app.capabilities.layer_asset_forge.schema.pose_signal",
        "backend.app.capabilities.layer_asset_forge.schema.pose_signal",
    ):
        try:
            return import_module(module_name)
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError("Could not resolve layer_asset_forge pose_signal module")


_pose_signal_module = _load_pose_signal_module()
__all__ = list(getattr(_pose_signal_module, "__all__", []))

for _name in __all__:
    globals()[_name] = getattr(_pose_signal_module, _name)
