"""Generic activation seam for capability-owned outcome adapters."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from backend.app.services.capability_backend_loader import (
    resolve_capability_backend_callable,
)

from .outcome_adapter_resolver import (
    CONTRACT_EXPORT_ID,
    PORT_ID,
    OutcomeAdapterSnapshot,
    materialize_outcome_adapter_snapshot,
)
from .outcome_runtime_trust import OutcomeRuntimeTrust

_TEMPLATE_FIELDS = {
    "descriptor_id",
    "port_id",
    "contract_export_id",
    "adapter_contract_version",
    "evaluator_version",
    "capability_identity",
    "selector",
    "input_schema_id",
    "output_schema_id",
    "evaluator_entrypoint",
    "review_lens",
    "authorized_lane",
}


def materialize_declared_outcome_adapter(
    capability_entry: dict[str, Any],
    *,
    capability_code: str,
    installed_manifest_sha256: str,
    installed_artifact_sha256: str,
    trust: OutcomeRuntimeTrust,
    runtime_active: bool,
) -> OutcomeAdapterSnapshot | None:
    """Materialize one declared adapter; undeclared packs remain unchanged."""

    manifest = capability_entry.get("manifest")
    capability_dir = capability_entry.get("directory")
    if not isinstance(manifest, Mapping):
        raise ValueError("outcome_adapter_manifest_missing")
    declaration = manifest.get("product_outcome_adapter")
    if declaration is None:
        return None
    if not isinstance(declaration, Mapping):
        raise ValueError("product_outcome_adapter_must_be_mapping")
    if not isinstance(capability_dir, Path):
        capability_dir = Path(capability_dir)

    contract_export = _find_contract_export(manifest)
    factory_path = str(declaration.get("descriptor_factory") or "").strip()
    owned_prefix = f"capabilities.{capability_code}.services."
    if not factory_path.startswith(owned_prefix) or ":" not in factory_path:
        raise ValueError("outcome_descriptor_factory_is_not_capability_owned")
    factory = resolve_capability_backend_callable(
        backend_path=factory_path,
        capability_dir=capability_dir,
    )
    template = factory()
    if not isinstance(template, dict):
        raise ValueError("outcome_descriptor_factory_must_return_mapping")
    unexpected = set(template).difference(_TEMPLATE_FIELDS)
    if unexpected:
        raise ValueError(
            "outcome_descriptor_template_has_unknown_fields:"
            + ",".join(sorted(unexpected))
        )
    if template.get("port_id") != PORT_ID:
        raise ValueError("outcome_descriptor_port_id_mismatch")
    if template.get("contract_export_id") != CONTRACT_EXPORT_ID:
        raise ValueError("outcome_descriptor_contract_export_id_mismatch")
    identity = template.get("capability_identity")
    if not isinstance(identity, Mapping):
        raise ValueError("outcome_descriptor_capability_identity_missing")
    if identity.get("capability_code") != capability_code:
        raise ValueError("outcome_descriptor_capability_code_mismatch")
    if identity.get("pack_version") != manifest.get("version"):
        raise ValueError("outcome_descriptor_pack_version_mismatch")
    if template.get("adapter_contract_version") != contract_export.get("version"):
        raise ValueError("outcome_descriptor_export_version_mismatch")
    if template.get("authorized_lane") != "runner:existing":
        raise ValueError("outcome_descriptor_authorized_lane_mismatch")

    descriptor = trust.sign_descriptor(
        template,
        manifest_sha256=installed_manifest_sha256,
        installed_artifact_sha256=installed_artifact_sha256,
    )
    return materialize_outcome_adapter_snapshot(
        capability_entry,
        capability_code=capability_code,
        contract_export=contract_export,
        descriptor=descriptor,
        installed_manifest_sha256=installed_manifest_sha256,
        installed_artifact_sha256=installed_artifact_sha256,
        verification_keys=trust.descriptor_verification_keys,
        capability_dir=capability_dir,
        runtime_active=runtime_active,
    )


def _find_contract_export(manifest: Mapping[str, Any]) -> dict[str, Any]:
    matches = [
        item
        for item in manifest.get("contract_exports", [])
        if isinstance(item, Mapping) and item.get("contract_id") == CONTRACT_EXPORT_ID
    ]
    if len(matches) != 1:
        raise ValueError("product_outcome_adapter_requires_one_contract_export")
    return dict(matches[0])


__all__ = ("materialize_declared_outcome_adapter",)
