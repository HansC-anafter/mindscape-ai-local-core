"""Candidate version and explicit backout admission policy."""

from __future__ import annotations

from dataclasses import dataclass

from packaging.version import InvalidVersion, Version


@dataclass(frozen=True)
class PackBackoutReceipt:
    backout_from_install_id: str
    artifact_sha256: str
    target_version: str
    schema_compatibility_receipt: str
    owner_approval: str

    def validate(self) -> None:
        missing = [
            name
            for name, value in self.__dict__.items()
            if not str(value).strip()
        ]
        if missing:
            raise ValueError(
                "pack_backout_receipt_missing:" + ",".join(sorted(missing))
            )


def validate_candidate_version(
    *,
    incoming_version: str,
    incoming_hash: str,
    committed_version: str | None,
    committed_hash: str | None,
    committed_install_id: str | None = None,
    live_version: str | None,
    live_hash: str | None,
    incoming_artifact_sha256: str | None = None,
    backout_receipt: PackBackoutReceipt | None = None,
) -> str:
    """Validate version order and split-truth conditions before prepare."""

    if committed_version is None:
        return "new_install"
    if live_version != committed_version or live_hash != committed_hash:
        raise RuntimeError("pack_live_runtime_does_not_match_committed_receipt")
    try:
        incoming = Version(str(incoming_version))
        committed = Version(str(committed_version))
    except InvalidVersion as exc:
        raise ValueError("pack_version_must_be_pep440_compatible") from exc
    if incoming == committed:
        if incoming_hash != committed_hash:
            raise RuntimeError("same_version_different_hash_conflict")
        return "idempotent"
    if incoming > committed:
        return "upgrade"
    if backout_receipt is None:
        raise RuntimeError("pack_downgrade_requires_explicit_backout_receipt")
    backout_receipt.validate()
    if committed_install_id and (
        backout_receipt.backout_from_install_id != committed_install_id
    ):
        raise RuntimeError("pack_backout_source_install_id_mismatch")
    if backout_receipt.target_version != incoming_version:
        raise RuntimeError("pack_backout_target_version_mismatch")
    if backout_receipt.artifact_sha256 != (
        incoming_artifact_sha256 or incoming_hash
    ):
        raise RuntimeError("pack_backout_artifact_hash_mismatch")
    return "authorized_backout"
