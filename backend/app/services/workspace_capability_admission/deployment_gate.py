"""Deployment-control intersection seam for root admission."""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.services.deployment_control.contracts import (
    EffectiveDeploymentCeiling,
)
from backend.app.services.deployment_control.facade import (
    DeploymentControlFacade,
)
from backend.app.services.workspace_product_configuration.contracts import (
    WorkspaceCapabilitySetSnapshot,
)


@dataclass(frozen=True)
class DeploymentGateOutcome:
    ceiling: EffectiveDeploymentCeiling
    permitted: bool


class DeploymentGate:
    def __init__(
        self,
        facade: DeploymentControlFacade | None = None,
    ) -> None:
        self.facade = facade or DeploymentControlFacade()

    def evaluate(
        self,
        *,
        wpcs: WorkspaceCapabilitySetSnapshot,
        pcs_id: str | None,
        pcs_version: str | None,
        product_surface_id: str,
    ) -> DeploymentGateOutcome:
        ceiling = self.facade.resolve_effective_ceiling(wpcs)
        if ceiling.mode == "unmanaged_local":
            return DeploymentGateOutcome(ceiling=ceiling, permitted=True)
        permitted = any(
            item.pcs_id == pcs_id
            and item.pcs_version == pcs_version
            and product_surface_id in item.allowed_surface_ids
            for item in ceiling.assignments
        )
        return DeploymentGateOutcome(
            ceiling=ceiling,
            permitted=permitted,
        )

