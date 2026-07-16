"""Deprecated inbound adapter for the durable capability install job path."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple


class CapabilityInstaller:
    """Preserve the legacy entrypoint without retaining a second installer."""

    def __init__(
        self,
        local_core_root: Path,
        capabilities_dir: Optional[Path] = None,
        specs_dir: Optional[Path] = None,
        i18n_dir: Optional[Path] = None,
        tools_dir: Optional[Path] = None,
        services_dir: Optional[Path] = None,
    ) -> None:
        self.local_core_root = Path(local_core_root)
        self.capabilities_dir = capabilities_dir
        self.specs_dir = specs_dir
        self.i18n_base_dir = i18n_dir
        self.tools_base_dir = tools_dir
        self.services_base_dir = services_dir

    def install_from_mindpack(
        self,
        mindpack_path: Path,
        validate: bool = True,
    ) -> Tuple[bool, Dict]:
        """Create the one durable job; `True` means accepted, not completed."""
        path = Path(mindpack_path)
        if not path.is_file():
            return False, {"errors": [f"Mindpack file not found: {path}"]}

        from backend.app.services.capability_install_jobs import (
            CapabilityInstallJobService,
        )

        job = CapabilityInstallJobService().create_file_upload_job(
            filename=path.name,
            content=path.read_bytes(),
            allow_overwrite=False,
            overwrite_review_confirmation="",
            profile_id="legacy-capability-installer-adapter",
        )
        return True, {
            "accepted": True,
            "state": job.get("state") or "queued",
            "install_id": job["install_id"],
            "status_url": job["status_url"],
            "validation_requested": bool(validate),
        }

    def _install_capability(self, *_args, **_kwargs) -> bool:
        raise RuntimeError("legacy_direct_capability_install_forbidden")
