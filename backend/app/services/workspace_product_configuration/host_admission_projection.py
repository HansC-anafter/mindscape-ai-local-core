"""Project strict host admission details from the WPC bounded aggregate."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.app.services.host_runtime_bindings.effective_admission import (
    evaluate_effective_host_admission,
)
from backend.app.services.host_runtime_bindings.projection import (
    binding_from_record,
    grant_from_record,
)

from .contracts import ProductHostAdmissionDetail


def product_host_admission(
    *,
    product: dict[str, Any],
    host_readiness: list[dict[str, Any]],
    workspace_id: str,
    now: datetime | None = None,
) -> list[ProductHostAdmissionDetail]:
    """Return one deterministic detail per declared host operation."""
    required = _required_operations(product)
    rows = {
        (
            row.get("pack_code"),
            row.get("requirement_code"),
            row.get("operation"),
        ): row
        for row in host_readiness
        if isinstance(row, dict)
    }
    result: list[ProductHostAdmissionDetail] = []
    observed_now = now or datetime.now(timezone.utc)
    for pack_code, requirement_code, operation in required:
        row = rows.get((pack_code, requirement_code, operation))
        try:
            binding_record = row.get("binding") if row else None
            attestation = row.get("attestation") if row else None
            if isinstance(binding_record, dict) and isinstance(attestation, dict):
                binding_record = {
                    **binding_record,
                    "attestation": attestation,
                }
            binding = (
                binding_from_record(binding_record)
                if isinstance(binding_record, dict)
                else None
            )
            grant_record = row.get("grant") if row else None
            grant = (
                grant_from_record(grant_record, now=observed_now)
                if isinstance(grant_record, dict)
                else None
            )
            admission = evaluate_effective_host_admission(
                workspace_id=workspace_id,
                operation=operation,
                binding=binding,
                grant=grant,
                now=observed_now,
            )
            result.append(
                ProductHostAdmissionDetail(
                    pack_code=pack_code,
                    requirement_code=requirement_code,
                    operation=operation,
                    admitted=admission.admitted,
                    binding_id=admission.binding_id,
                    binding_generation=admission.binding_generation,
                    grant_id=admission.grant_id,
                    attestation_revision=admission.attestation_revision,
                    policy_revision=admission.policy_revision,
                    blockers=admission.blockers,
                )
            )
        except (KeyError, TypeError, ValueError):
            result.append(
                ProductHostAdmissionDetail(
                    pack_code=pack_code,
                    requirement_code=requirement_code,
                    operation=operation,
                    admitted=False,
                    blockers=["host_projection_invalid"],
                )
            )
    return result


def _required_operations(
    product: dict[str, Any],
) -> list[tuple[str, str, str]]:
    values: set[tuple[str, str, str]] = set()
    for pack in product.get("pack_closure", []):
        if not isinstance(pack, dict) or not isinstance(pack.get("code"), str):
            continue
        for requirement in pack.get("host_requirements", []):
            if (
                not isinstance(requirement, dict)
                or not isinstance(requirement.get("requirement_code"), str)
                or not isinstance(requirement.get("operations"), list)
            ):
                continue
            for operation in requirement["operations"]:
                if isinstance(operation, str):
                    values.add(
                        (
                            pack["code"],
                            requirement["requirement_code"],
                            operation,
                        )
                    )
    return sorted(values)
