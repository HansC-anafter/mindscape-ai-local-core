"""Receipt-bound candidate version admission before install side effects."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
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

    def bootstrap_legacy_commit(
        self,
        *,
        pack_id: str,
        live_version: str,
        live_manifest_hash: str,
    ) -> Optional[dict[str, Any]]:
        """Materialize a receipt only from mutually matching legacy truth sources."""

        with self.transaction() as conn:
            conn.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"pack-install-legacy-bootstrap:{pack_id}"},
            )
            existing = (
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
            if existing is not None:
                return dict(existing)
            row = (
                conn.execute(
                    text(
                        """
                        SELECT
                            installed.pack_id,
                            installed.installed_at,
                            installed.enabled,
                            CAST(installed.metadata AS JSONB) AS installed_metadata,
                            job.install_id,
                            job.state AS job_state,
                            job.source_payload,
                            job.result_payload,
                            job.finished_at,
                            activation.manifest_hash AS activation_manifest_hash
                        FROM installed_packs AS installed
                        JOIN capability_install_jobs AS job
                          ON job.install_id = (
                              CAST(installed.metadata AS JSONB) ->> 'install_id'
                          )
                        LEFT JOIN pack_activation_state AS activation
                          ON activation.pack_id = installed.pack_id
                        WHERE installed.pack_id = :pack_id
                        """
                    ),
                    {"pack_id": pack_id},
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            legacy_row = dict(row)
            source_payload = _mapping(legacy_row.get("source_payload"))
            if not _valid_sha256(source_payload.get("archive_sha256") or ""):
                legacy_row["retained_artifact_sha256"] = (
                    _retained_legacy_artifact_sha256(
                        source_payload,
                        install_id=str(legacy_row.get("install_id") or ""),
                    )
                )
            bootstrap = _validated_legacy_bootstrap(
                legacy_row,
                pack_id=pack_id,
                live_version=live_version,
                live_manifest_hash=live_manifest_hash,
            )
            conn.execute(
                text(
                    """
                    INSERT INTO pack_install_commit_receipts (
                        install_id, pack_id, version, manifest_hash, artifact_sha256,
                        migration_receipt, commit_metadata, projection_state,
                        filesystem_cleanup_state, reconciled_at, committed_at
                    ) VALUES (
                        :install_id, :pack_id, :version, :manifest_hash,
                        :artifact_sha256, CAST(:migration_receipt AS JSONB),
                        CAST(:commit_metadata AS JSONB), 'succeeded', 'succeeded',
                        :committed_at, :committed_at
                    )
                    ON CONFLICT (install_id) DO NOTHING
                    """
                ),
                {
                    **bootstrap,
                    "migration_receipt": self.serialize_json(
                        {
                            "mode": "verified_legacy_install_bootstrap",
                            "historical_migration_details": "not_recorded",
                        }
                    ),
                    "commit_metadata": self.serialize_json(
                        {
                            "bootstrap_mode": "verified_legacy_install_bootstrap",
                            "source_install_id": bootstrap["install_id"],
                            "bootstrapped_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ),
                },
            )
            committed = (
                conn.execute(
                    text(
                        """
                        SELECT install_id, pack_id, version, manifest_hash,
                               artifact_sha256, committed_at
                        FROM pack_install_commit_receipts
                        WHERE install_id = :install_id
                        """
                    ),
                    {"install_id": bootstrap["install_id"]},
                )
                .mappings()
                .first()
            )
            return dict(committed) if committed is not None else None


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _valid_sha256(value: str) -> bool:
    normalized = str(value).strip().lower()
    return len(normalized) == 64 and all(
        character in "0123456789abcdef" for character in normalized
    )


def _retained_legacy_artifact_sha256(
    source_payload: Mapping[str, Any],
    *,
    install_id: str,
) -> str:
    """Hash only the canonical retained artifact for the same legacy install."""

    raw_path = str(source_payload.get("mindpack_path") or "").strip()
    if not raw_path or not install_id:
        return ""
    try:
        artifact_path = Path(raw_path).resolve(strict=True)
    except (OSError, RuntimeError):
        return ""
    if (
        artifact_path.name != "input.mindpack"
        or artifact_path.parent.name != install_id
        or artifact_path.parent.parent.name != "capability-install-jobs"
        or not artifact_path.is_file()
    ):
        return ""
    digest = hashlib.sha256()
    try:
        with artifact_path.open("rb") as artifact_file:
            for chunk in iter(lambda: artifact_file.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return digest.hexdigest()


def _validated_legacy_bootstrap(
    row: Mapping[str, Any],
    *,
    pack_id: str,
    live_version: str,
    live_manifest_hash: str,
) -> dict[str, Any]:
    installed_metadata = _mapping(row.get("installed_metadata"))
    source_payload = _mapping(row.get("source_payload"))
    result_payload = _mapping(row.get("result_payload"))
    activation = _mapping(result_payload.get("activation"))
    integrity = _mapping(result_payload.get("install_integrity"))
    install_id = str(installed_metadata.get("install_id") or "")
    artifact_sha256 = str(
        source_payload.get("archive_sha256")
        or row.get("retained_artifact_sha256")
        or ""
    ).lower()
    observed_hashes = {
        str(value)
        for value in (
            activation.get("manifest_hash"),
            integrity.get("manifest_hash"),
            row.get("activation_manifest_hash"),
        )
        if str(value or "").strip()
    }
    checks = {
        "pack_id": str(row.get("pack_id") or "") == pack_id,
        "enabled": row.get("enabled") is True,
        "install_id": bool(install_id) and install_id == str(row.get("install_id") or ""),
        "job_state": str(row.get("job_state") or "") == "succeeded",
        "installed_version": str(installed_metadata.get("version") or "")
        == live_version,
        "result_version": str(result_payload.get("version") or "") == live_version,
        "artifact_sha256": _valid_sha256(artifact_sha256),
        "manifest_hashes": bool(observed_hashes)
        and observed_hashes == {live_manifest_hash},
        "finished_at": row.get("finished_at") is not None,
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise RuntimeError(
            "legacy_pack_commit_bootstrap_evidence_mismatch:" + ",".join(failed)
        )
    return {
        "install_id": install_id,
        "pack_id": pack_id,
        "version": live_version,
        "manifest_hash": live_manifest_hash,
        "artifact_sha256": artifact_sha256,
        "committed_at": row["finished_at"],
    }


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
    reviewed_split_truth_repair: bool = False,
    truth_reader: Optional[PackInstallVersionTruthReader] = None,
) -> str:
    """Reject unreceipted/split truth before playbook or runtime writes."""

    incoming_version, incoming_manifest_hash = _manifest_identity(
        candidate_manifest_path
    )
    live_version, live_manifest_hash = _manifest_identity(live_manifest_path)
    reader = truth_reader or PackInstallVersionTruthReader()
    committed = reader.latest_commit(capability_code)
    if committed is None and hasattr(reader, "bootstrap_legacy_commit"):
        committed = reader.bootstrap_legacy_commit(
            pack_id=capability_code,
            live_version=live_version,
            live_manifest_hash=live_manifest_hash,
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
            reviewed_split_truth_repair=reviewed_split_truth_repair,
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
