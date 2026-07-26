"""Projection seam for the installed capability localization descriptor."""

from __future__ import annotations

from typing import Any


def project_installed_ui_localization(
    runtime_index: dict[str, Any],
) -> dict[str, Any] | None:
    localization = runtime_index.get("localization")
    if not isinstance(localization, dict):
        return None
    catalogs = localization.get("catalogs")
    if not isinstance(catalogs, dict):
        return None
    return localization
