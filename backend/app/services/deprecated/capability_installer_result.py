"""Legacy result helpers for the deprecated capability installer."""

from __future__ import annotations

from typing import Dict, Optional, Tuple, Union

from ..install_result import InstallResult

LegacyResult = Union[Dict, InstallResult]


class CapabilityInstallerResultMixin:
    @staticmethod
    def _create_result() -> InstallResult:
        """Create the legacy-compatible install result shape."""
        return InstallResult(
            installed={
                "playbooks": [],
                "tools": [],
                "services": [],
                "api_endpoints": [],
                "schema_modules": [],
                "database_models": [],
                "migrations": [],
                "ui_components": [],
                "bundles": [],
            }
        )

    @staticmethod
    def _coerce_result(result: LegacyResult) -> Tuple[InstallResult, Optional[Dict]]:
        """Normalize legacy dict results to InstallResult while preserving callers."""
        if isinstance(result, InstallResult):
            return result, None
        return InstallResult.from_dict(result), result

    @staticmethod
    def _sync_legacy_result(result: InstallResult, legacy_result: Optional[Dict]) -> None:
        """Write the InstallResult back into a legacy dict when needed."""
        if legacy_result is None:
            return
        legacy_result.clear()
        legacy_result.update(result.to_dict())
