"""Non-expanding intersection between WPCS intent and deployment ceiling."""

from __future__ import annotations

from backend.app.services.workspace_product_configuration.contracts import (
    WorkspaceCapabilitySetSnapshot,
)

from .contracts import (
    CeilingAssignment,
    DeploymentControlState,
    EffectiveDeploymentCeiling,
)
from .errors import DeploymentManagedEnvelopeMissing


def intersect_effective_ceiling(
    wpcs: WorkspaceCapabilitySetSnapshot,
    state: DeploymentControlState,
) -> EffectiveDeploymentCeiling:
    if state.mode == "unmanaged_local":
        return EffectiveDeploymentCeiling(
            mode=state.mode,
            provider_code=None,
            state_revision=state.state_revision,
            envelope_revision=None,
            envelope_hash=None,
            assignments=[
                CeilingAssignment(
                    pcs_id=item.pcs_id,
                    pcs_version=item.pcs_version,
                    allowed_surface_ids=sorted(set(item.product_surface_ids)),
                )
                for item in wpcs.effective_assignments
            ],
        )
    if state.signed_envelope is None:
        raise DeploymentManagedEnvelopeMissing()
    grants = {
        (grant.pcs_id, grant.pcs_version): set(grant.surface_ids)
        for grant in state.signed_envelope.claims.allowed_products
    }
    assignments: list[CeilingAssignment] = []
    for assignment in wpcs.effective_assignments:
        allowed = grants.get((assignment.pcs_id, assignment.pcs_version))
        if allowed is None:
            continue
        surfaces = sorted(allowed.intersection(assignment.product_surface_ids))
        if not surfaces:
            continue
        assignments.append(
            CeilingAssignment(
                pcs_id=assignment.pcs_id,
                pcs_version=assignment.pcs_version,
                allowed_surface_ids=surfaces,
            )
        )
    return EffectiveDeploymentCeiling(
        mode=state.mode,
        provider_code=state.provider_code,
        state_revision=state.state_revision,
        envelope_revision=state.envelope_revision,
        envelope_hash=state.envelope_hash,
        assignments=assignments,
    )
