"""O(1) neutral outcome-adapter snapshot materialization and resolution."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from .canonical_json import encode, sha256_hex
from .contracts.v1.validator import validate_contract
from .signature import Ed25519Signer, verify

PORT_ID = "mindscape.product-outcome-adapter-port.v1"
CONTRACT_EXPORT_ID = "product_outcome_adapter"
SNAPSHOT_INDEX_KEY = "outcome_adapter_snapshots"


@dataclass(frozen=True)
class OutcomeAdapterSnapshot:
    provider_pack: str
    export_module: str
    export_version: str
    descriptor: Mapping[str, Any]
    capability_dir: object | None
    runtime_active: bool


@dataclass(frozen=True)
class ResolutionResult:
    snapshot: OutcomeAdapterSnapshot | None
    rejection: dict[str, Any] | None


def _freeze(value):
    if isinstance(value, dict):
        return MappingProxyType(
            {key: _freeze(child) for key, child in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze(child) for child in value)
    return value


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(child) for key, child in value.items()}
    if isinstance(value, tuple):
        return [_plain(child) for child in value]
    return value


def materialize_outcome_adapter_snapshot(
    capability_entry: dict[str, Any],
    *,
    capability_code: str,
    contract_export: dict[str, Any],
    descriptor: dict[str, Any],
    installed_manifest_sha256: str,
    installed_artifact_sha256: str,
    verification_keys: dict[str, Any],
    capability_dir: object | None = None,
    runtime_active: bool,
) -> OutcomeAdapterSnapshot:
    """Attach a verified immutable snapshot to an existing capability entry."""

    validate_contract("outcome_adapter_descriptor", descriptor)
    if contract_export.get("contract_id") != CONTRACT_EXPORT_ID:
        raise ValueError("outcome adapter contract export ID is invalid")
    export_version = str(contract_export.get("version") or "")
    export_module = str(contract_export.get("module") or "")
    owned_prefix = f"capabilities.{capability_code}."
    if not export_module.startswith(f"{owned_prefix}schema."):
        raise ValueError("outcome adapter export module is not capability-owned")
    if not descriptor["evaluator_entrypoint"].startswith(owned_prefix):
        raise ValueError("outcome evaluator entrypoint is not capability-owned")
    if descriptor["capability_identity"]["capability_code"] != capability_code:
        raise ValueError("outcome descriptor capability identity mismatch")
    if descriptor["adapter_contract_version"] != export_version:
        raise ValueError("outcome descriptor export version mismatch")
    if descriptor["authorized_lane"] != "runner:existing":
        raise ValueError("outcome descriptor authorized lane mismatch")
    if descriptor["manifest_sha256"] != installed_manifest_sha256:
        raise ValueError("outcome descriptor manifest hash mismatch")
    if descriptor["installed_artifact_sha256"] != installed_artifact_sha256:
        raise ValueError("outcome descriptor artifact hash mismatch")

    hash_input = {
        key: value
        for key, value in descriptor.items()
        if key not in {"descriptor_sha256", "signature"}
    }
    if descriptor["descriptor_sha256"] != sha256_hex(hash_input):
        raise ValueError("outcome descriptor canonical hash mismatch")
    public_key = verification_keys.get(descriptor["key_id"])
    if public_key is None:
        raise ValueError("outcome descriptor signing key is unavailable")
    verify(
        public_key,
        encode(
            {
                key: value
                for key, value in descriptor.items()
                if key != "signature"
            }
        ),
        descriptor["signature"],
    )

    snapshot = OutcomeAdapterSnapshot(
        provider_pack=capability_code,
        export_module=export_module,
        export_version=export_version,
        descriptor=_freeze(descriptor),
        capability_dir=capability_dir,
        runtime_active=runtime_active,
    )
    return attach_outcome_adapter_snapshot(capability_entry, snapshot)


def attach_outcome_adapter_snapshot(
    capability_entry: dict[str, Any],
    snapshot: OutcomeAdapterSnapshot,
) -> OutcomeAdapterSnapshot:
    """Attach exactly one immutable snapshot for an exact signed identity."""

    index = capability_entry.setdefault(SNAPSHOT_INDEX_KEY, {})
    key = (
        CONTRACT_EXPORT_ID,
        snapshot.export_version,
        snapshot.descriptor["descriptor_sha256"],
    )
    matches = tuple(index.get(key, ()))
    if matches:
        if len(matches) == 1 and matches[0] == snapshot:
            return matches[0]
        raise ValueError("outcome adapter snapshot identity conflict")
    index[key] = (snapshot,)
    return snapshot


class OutcomeAdapterResolver:
    """Exact capability-entry resolver; it owns no filesystem or cache."""

    def __init__(self, signer: Ed25519Signer) -> None:
        self._signer = signer

    def resolve(
        self,
        capability_entries: Mapping[str, dict[str, Any]],
        pin: dict[str, str],
    ) -> ResolutionResult:
        reason = self._pin_error(pin)
        if reason:
            return ResolutionResult(None, self.reject(pin, reason))
        entry = capability_entries.get(pin["capability_code"])
        if entry is None:
            return ResolutionResult(
                None, self.reject(pin, "capability_not_active")
            )
        key = (
            CONTRACT_EXPORT_ID,
            pin["adapter_contract_version"],
            pin["descriptor_sha256"],
        )
        matches = entry.get(SNAPSHOT_INDEX_KEY, {}).get(key, ())
        if len(matches) != 1:
            reason = "adapter_not_found" if not matches else "adapter_ambiguous"
            return ResolutionResult(None, self.reject(pin, reason))
        snapshot = matches[0]
        if not snapshot.runtime_active:
            return ResolutionResult(
                None, self.reject(pin, "capability_not_active")
            )
        descriptor = _plain(snapshot.descriptor)
        if descriptor["evaluator_version"] != pin["evaluator_version"]:
            return ResolutionResult(
                None, self.reject(pin, "evaluator_version_mismatch")
            )
        return ResolutionResult(snapshot, None)

    def reject(self, pin: dict[str, str], reason: str) -> dict[str, Any]:
        core = {
            "receipt_type": "adapter_resolution_rejected",
            "capability_code": str(pin.get("capability_code") or ""),
            "port_id": str(pin.get("port_id") or ""),
            "contract_export_id": str(pin.get("contract_export_id") or ""),
            "adapter_contract_version": str(
                pin.get("adapter_contract_version") or ""
            ),
            "descriptor_sha256": str(pin.get("descriptor_sha256") or ""),
            "evaluator_version": str(pin.get("evaluator_version") or ""),
            "reason": reason,
        }
        rejection_id = f"adapter-rejection:{sha256_hex(core)}"
        signed = {
            **core,
            "rejection_id": rejection_id,
            "key_id": self._signer.key_id,
        }
        signature = self._signer.sign(encode(signed))
        return {
            **signed,
            "signature": signature.value,
        }

    @staticmethod
    def _pin_error(pin: dict[str, str]) -> str | None:
        if pin.get("port_id") != PORT_ID:
            return "adapter_port_mismatch"
        if pin.get("contract_export_id") != CONTRACT_EXPORT_ID:
            return "contract_export_mismatch"
        required = (
            "capability_code",
            "adapter_contract_version",
            "descriptor_sha256",
            "evaluator_version",
        )
        return next(
            (f"missing_{field}" for field in required if not pin.get(field)),
            None,
        )
