"""Runtime-owned signing boundary for neutral product outcome adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .canonical_json import encode, sha256_hex
from .signature import Ed25519Signer

DESCRIPTOR_SIGNING_KEY_FILE_ENV = "MINDSCAPE_OUTCOME_DESCRIPTOR_SIGNING_KEY_FILE"
OBSERVATION_SIGNING_KEY_FILE_ENV = "MINDSCAPE_OUTCOME_OBSERVATION_SIGNING_KEY_FILE"


@dataclass(frozen=True)
class OutcomeRuntimeTrust:
    """Keeps descriptor and observation authorities separate."""

    descriptor_signer: Ed25519Signer
    observation_signer: Ed25519Signer

    def __post_init__(self) -> None:
        if self.descriptor_signer.key_id == self.observation_signer.key_id:
            raise ValueError(
                "outcome descriptor and observation authorities must be distinct"
            )

    @classmethod
    def from_mounted_files(cls) -> "OutcomeRuntimeTrust":
        return cls(
            descriptor_signer=Ed25519Signer.from_mounted_file(
                env_var=DESCRIPTOR_SIGNING_KEY_FILE_ENV,
            ),
            observation_signer=Ed25519Signer.from_mounted_file(
                env_var=OBSERVATION_SIGNING_KEY_FILE_ENV,
            ),
        )

    @property
    def descriptor_verification_keys(self) -> dict[str, object]:
        signer = self.descriptor_signer
        return {signer.key_id: signer.public_key()}

    @property
    def observation_verification_keys(self) -> dict[str, object]:
        signer = self.observation_signer
        return {signer.key_id: signer.public_key()}

    def sign_descriptor(
        self,
        template: dict[str, Any],
        *,
        manifest_sha256: str,
        installed_artifact_sha256: str,
        activated_at: str | None = None,
    ) -> dict[str, Any]:
        runtime_fields = {
            "manifest_sha256",
            "installed_artifact_sha256",
            "activated_at",
            "descriptor_sha256",
            "key_id",
            "signature",
        }
        overlap = runtime_fields.intersection(template)
        if overlap:
            raise ValueError(
                "outcome descriptor template contains runtime-owned fields: "
                + ",".join(sorted(overlap))
            )
        core = {
            **template,
            "installed_artifact_sha256": installed_artifact_sha256,
            "manifest_sha256": manifest_sha256,
            "activated_at": activated_at or datetime.now(timezone.utc).isoformat(),
            "key_id": self.descriptor_signer.key_id,
        }
        hashed = {
            **core,
            "descriptor_sha256": sha256_hex(core),
        }
        signature = self.descriptor_signer.sign(encode(hashed))
        return {**hashed, "signature": signature.value}

    def sign_observation(
        self,
        unsigned: dict[str, Any],
    ) -> dict[str, Any]:
        if "signature" in unsigned or "key_id" in unsigned:
            raise ValueError(
                "outcome evaluator cannot set runtime-owned signature fields"
            )
        payload = {
            **unsigned,
            "key_id": self.observation_signer.key_id,
        }
        signature = self.observation_signer.sign(encode(payload))
        return {**payload, "signature": signature.value}


__all__ = (
    "DESCRIPTOR_SIGNING_KEY_FILE_ENV",
    "OBSERVATION_SIGNING_KEY_FILE_ENV",
    "OutcomeRuntimeTrust",
)
