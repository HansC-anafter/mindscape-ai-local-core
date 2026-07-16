"""Path-validated cleanup for an already committed install candidate."""

from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path
from typing import Any, Mapping


def _resolved(value: Any) -> Path:
    return Path(str(value or "")).resolve()


def finalize_committed_filesystem(
    *,
    local_core_root: Path,
    install_id: str,
    capability_code: str,
    manifest_hash: str,
    filesystem_receipt: Mapping[str, Any],
) -> None:
    if not install_id or any(item in install_id for item in ("/", "\\", "..")):
        raise ValueError("install_reconciliation_install_id_invalid")
    if not capability_code or any(
        item in capability_code for item in ("/", "\\", "..")
    ):
        raise ValueError("install_reconciliation_capability_code_invalid")
    capabilities_dir = (
        local_core_root.resolve() / "backend" / "app" / "capabilities"
    )
    expected_target = (capabilities_dir / capability_code).resolve()
    target = _resolved(filesystem_receipt.get("target_cap_dir"))
    if target != expected_target:
        raise RuntimeError("install_reconciliation_target_path_mismatch")
    manifest_path = target / "manifest.yaml"
    if not manifest_path.is_file():
        raise RuntimeError("install_reconciliation_target_manifest_missing")
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != manifest_hash:
        raise RuntimeError("install_reconciliation_target_manifest_hash_mismatch")

    expected_previous = (
        capabilities_dir.parent
        / ".capability-install-previous"
        / install_id
        / capability_code
    ).resolve()
    previous_cap = _resolved(filesystem_receipt.get("previous_cap_dir"))
    if previous_cap != expected_previous:
        raise RuntimeError("install_reconciliation_previous_path_mismatch")
    configured_staging = os.environ.get("MINDSCAPE_CAPABILITY_INSTALL_STAGING_ROOT")
    expected_staging = (
        Path(configured_staging).resolve() / install_id
        if configured_staging
        else capabilities_dir.parent / ".capability-install-staging" / install_id
    ).resolve()
    staging_root = _resolved(filesystem_receipt.get("staging_root"))
    if staging_root != expected_staging:
        raise RuntimeError("install_reconciliation_staging_path_mismatch")

    previous_root = expected_previous.parent
    if previous_root.exists():
        shutil.rmtree(previous_root)
    if staging_root.exists():
        shutil.rmtree(staging_root)
    for parent in (previous_root.parent, staging_root.parent):
        try:
            parent.rmdir()
        except OSError:
            pass
