"""Receipt-bound candidate version admission before install side effects."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, Optional

import yaml
from sqlalchemy import text

from backend.app.routes.core.capability_install_core.install_commit_coordinator import (
    PackBackoutReceipt,
    validate_candidate_version,
)
from backend.app.services.runtime_database_incident_gate import record_database_failure
from backend.app.services.stores.postgres_base import PostgresStoreBase


class PackInstallVersionTruthReader(PostgresStoreBase):
    def latest_commit(self, pack_id: str) -> Optional[dict[str, Any]]:
        with self.get_connection() as conn:
            row = (
                conn.execute(
                    text(
                        """
                        SELECT install_id, pack_id, version, manifest_hash,
                               artifact_sha256, committed_at
                        FROM pack_install_commit_receipts
                        WHERE pack_id = :pack_id
                        ORDER BY committed_at DESC
                        LIMIT 1
                        """
                    ),
                    {"pack_id": pack_id},
                )
                .mappings()
                .first()
            )
        return dict(row) if row else None


def _manifest_identity(path: Path) -> tuple[str, str]:
    manifest = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(manifest, dict):
        raise ValueError("pack_manifest_root_must_be_mapping")
    version = str(manifest.get("version") or "").strip()
    if not version:
        raise ValueError("pack_manifest_version_missing")
    return version, hashlib.sha256(path.read_bytes()).hexdigest()


def _backout_receipt(
    payload: Optional[Mapping[str, Any]],
) -> Optional[PackBackoutReceipt]:
    if not payload:
        return None
    return PackBackoutReceipt(
        backout_from_install_id=str(payload.get("backout_from_install_id") or ""),
        artifact_sha256=str(payload.get("artifact_sha256") or ""),
        target_version=str(payload.get("target_version") or ""),
        schema_compatibility_receipt=str(
            payload.get("schema_compatibility_receipt") or ""
        ),
        owner_approval=str(payload.get("owner_approval") or ""),
    )


def validate_existing_pack_version_truth(
    *,
    capability_code: str,
    candidate_manifest_path: Path,
    live_manifest_path: Path,
    artifact_sha256: Optional[str],
    backout: Optional[Mapping[str, Any]] = None,
    truth_reader: Optional[PackInstallVersionTruthReader] = None,
) -> str:
    """Reject unreceipted/split truth before playbook or runtime writes."""

    incoming_version, incoming_manifest_hash = _manifest_identity(
        candidate_manifest_path
    )
    live_version, live_manifest_hash = _manifest_identity(live_manifest_path)
    committed = (truth_reader or PackInstallVersionTruthReader()).latest_commit(
        capability_code
    )
    if committed is None:
        record_database_failure(
            "pack_committed_receipt_missing",
            evidence={"pack_id": capability_code},
        )
        raise RuntimeError("pack_committed_receipt_missing")
    try:
        return validate_candidate_version(
            incoming_version=incoming_version,
            incoming_hash=incoming_manifest_hash,
            incoming_artifact_sha256=artifact_sha256,
            committed_version=str(committed["version"]),
            committed_hash=str(committed["manifest_hash"]),
            committed_install_id=str(committed["install_id"]),
            live_version=live_version,
            live_hash=live_manifest_hash,
            backout_receipt=_backout_receipt(backout),
        )
    except Exception:
        record_database_failure(
            "pack_install_truth_preflight_failed",
            evidence={
                "pack_id": capability_code,
                "committed_install_id": str(committed["install_id"]),
            },
        )
        raise
