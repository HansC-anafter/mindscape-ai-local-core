"""Existing-lane dispatcher for neutral product outcome evaluation tasks."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from backend.app.services.capability_backend_loader import (
    resolve_capability_backend_callable,
)

from .compatibility import CompatibilityRegistry
from .facade import DurableWorkflowFacade
from .outcome_adapter_port import ProductOutcomeAdapterPort
from .outcome_adapter_resolver import materialize_outcome_adapter_snapshot
from .outcome_evidence_repository import OutcomeEvidenceRepository
from .outcome_runtime_trust import OutcomeRuntimeTrust
from .outcome_task_admission import verify_outcome_task_admission
from .product_iteration_contract import comparability_key
from .signature import Ed25519Signer


class OutcomeTaskDispatcher:
    """Executes one signed task without creating another queue or worker."""

    def execute(
        self,
        *,
        task_id: str,
        workspace_id: str,
        capability_code: str,
        params: dict[str, Any],
        admission: dict[str, Any],
        trust: OutcomeRuntimeTrust,
    ) -> dict[str, Any]:
        verified = verify_outcome_task_admission(
            admission,
            expected_task_id=task_id,
            expected_workspace_id=workspace_id,
            expected_params=params,
            verification_keys=trust.descriptor_verification_keys,
        )
        self._require_task_identity(
            verified,
            capability_code=capability_code,
            params=params,
        )
        from backend.app.database.engine import engine_postgres_core

        if engine_postgres_core is None:
            raise RuntimeError("outcome_task_core_database_unavailable")
        workflow_signer = Ed25519Signer.from_mounted_file()
        verification_keys = {
            workflow_signer.key_id: workflow_signer.public_key(),
            **trust.observation_verification_keys,
        }
        with engine_postgres_core.begin() as conn:
            terminal, enrollment = OutcomeEvidenceRepository().task_evidence(
                conn,
                terminal_receipt_id=params["terminal_receipt_id"],
                enrollment_id=params["enrollment_id"],
                iteration_id=params["iteration_id"],
                workspace_id=workspace_id,
            )
            snapshot = self._restore_snapshot(
                capability_code=capability_code,
                params=params,
                trust=trust,
            )
            definition = OutcomeEvidenceRepository().iteration_definition(
                conn,
                iteration_id=params["iteration_id"],
                workspace_id=workspace_id,
            )
            evidence_repository = OutcomeEvidenceRepository()
            observations = ProductOutcomeAdapterPort(
                load_callable=resolve_capability_backend_callable,
                observation_verification_keys=(trust.observation_verification_keys),
            ).evaluate(
                snapshot=snapshot,
                terminal_receipt=terminal,
                enrollment=enrollment,
                runtime_context={
                    "sign_observation": trust.sign_observation,
                    "comparability_key": (
                        lambda metric_id: comparability_key(
                            definition,
                            metric_id,
                        )
                    ),
                    "read_result_ref": (
                        lambda result_ref: evidence_repository.read_result_ref(
                            conn,
                            result_ref=result_ref,
                            workspace_id=workspace_id,
                        )
                    ),
                },
            )
            facade = DurableWorkflowFacade(
                signer=workflow_signer,
                compatibility=CompatibilityRegistry(),
                verification_keys=verification_keys,
            )
            accepted = []
            for observation in observations:
                current = facade.read_current(
                    conn,
                    params["iteration_id"],
                )
                event = facade.accept_outcome_observation(
                    conn,
                    workflow_id=params["iteration_id"],
                    expected_sequence=current["current_sequence"],
                    enrollment=enrollment,
                    observation=observation,
                    actor={
                        "actor_type": "service",
                        "actor_id": "product-outcome-runtime",
                    },
                    idempotency_key=(
                        f"outcome-observation:" f"{observation['observation_id']}"
                    ),
                )
                accepted.append(
                    {
                        "observation_id": observation["observation_id"],
                        "event_type": event["event_type"],
                        "sequence": event["sequence"],
                    }
                )
        return {
            "status": "succeeded",
            "task_type": "product_outcome_evaluation",
            "task_id": task_id,
            "iteration_id": params["iteration_id"],
            "terminal_receipt_id": params["terminal_receipt_id"],
            "observation_count": len(accepted),
            "observations": accepted,
        }

    @staticmethod
    def _require_task_identity(
        admission: dict[str, Any],
        *,
        capability_code: str,
        params: dict[str, Any],
    ) -> None:
        expected = {
            "terminal_receipt_id": params.get("terminal_receipt_id"),
            "enrollment_id": params.get("enrollment_id"),
            "iteration_id": params.get("iteration_id"),
            "descriptor_sha256": params.get("descriptor_sha256"),
        }
        for field, value in expected.items():
            if not isinstance(value, str) or not value:
                raise ValueError(f"outcome_task_{field}_required")
            if admission.get(field) != value:
                raise ValueError(f"outcome_task_{field}_mismatch")
        descriptor_snapshot = params.get("descriptor_snapshot")
        if not isinstance(descriptor_snapshot, dict):
            raise ValueError("outcome_task_descriptor_snapshot_required")
        if descriptor_snapshot.get("provider_pack") != capability_code:
            raise ValueError("outcome_task_provider_pack_mismatch")

    @staticmethod
    def _restore_snapshot(
        *,
        capability_code: str,
        params: dict[str, Any],
        trust: OutcomeRuntimeTrust,
    ):
        from backend.app.services.capability_registry import get_registry

        entry = get_registry().get_capability(capability_code)
        if not isinstance(entry, dict):
            raise ValueError("outcome_task_capability_not_active")
        manifest = entry.get("manifest")
        capability_dir = entry.get("directory")
        if not isinstance(manifest, dict) or not capability_dir:
            raise ValueError("outcome_task_capability_registry_invalid")
        capability_dir = Path(capability_dir)
        manifest_path = capability_dir / "manifest.yaml"
        manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        snapshot_payload = params["descriptor_snapshot"]
        descriptor = snapshot_payload.get("descriptor")
        if not isinstance(descriptor, dict):
            raise ValueError("outcome_task_descriptor_missing")
        exports = [
            item
            for item in manifest.get("contract_exports", [])
            if isinstance(item, dict)
            and item.get("contract_id") == "product_outcome_adapter"
        ]
        if len(exports) != 1:
            raise ValueError("outcome_task_contract_export_not_unique")
        if descriptor.get("descriptor_sha256") != params.get("descriptor_sha256"):
            raise ValueError("outcome_task_descriptor_pin_mismatch")
        if snapshot_payload.get("export_module") != exports[0].get(
            "module"
        ) or snapshot_payload.get("export_version") != exports[0].get("version"):
            raise ValueError("outcome_task_contract_export_mismatch")
        isolated_entry = {
            "manifest": manifest,
            "directory": capability_dir,
        }
        return materialize_outcome_adapter_snapshot(
            isolated_entry,
            capability_code=capability_code,
            contract_export=exports[0],
            descriptor=descriptor,
            installed_manifest_sha256=manifest_sha256,
            installed_artifact_sha256=descriptor["installed_artifact_sha256"],
            verification_keys=trust.descriptor_verification_keys,
            capability_dir=capability_dir,
            runtime_active=True,
        )


__all__ = ("OutcomeTaskDispatcher",)
