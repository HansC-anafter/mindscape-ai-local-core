"""Compatibility re-export for the canonical LAF-owned visual-stats contract."""

from __future__ import annotations

from importlib import import_module


def _load_visual_signal_module():
    for module_name in (
        "capabilities.layer_asset_forge.schema.visual_signal",
        "app.capabilities.layer_asset_forge.schema.visual_signal",
        "backend.app.capabilities.layer_asset_forge.schema.visual_signal",
    ):
        try:
            return import_module(module_name)
        except ModuleNotFoundError:
            continue
    raise ModuleNotFoundError("Could not resolve layer_asset_forge visual_signal module")


_visual_signal_module = _load_visual_signal_module()
__all__ = list(getattr(_visual_signal_module, "__all__", []))

for _name in __all__:
    globals()[_name] = getattr(_visual_signal_module, _name)
