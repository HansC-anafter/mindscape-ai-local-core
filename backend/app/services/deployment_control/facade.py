"""Single generic application seam for deployment-control state and ceiling."""

from __future__ import annotations

from datetime import datetime

from backend.app.services.workspace_product_configuration.contracts import (
    WorkspaceCapabilitySetSnapshot,
)
from backend.app.services.workspace_product_configuration.runtime_identity import (
    source_runtime_id,
)

from .contracts import (
    DeploymentControlReplaceResult,
    DeploymentControlState,
    EffectiveDeploymentCeiling,
    ReplaceDeploymentControlCommand,
)
from .effective_ceiling import intersect_effective_ceiling
from .envelope_verifier import DeploymentEnvelopeVerifier
from .state_repository import DeploymentControlStateRepository
from .trust_store import DeploymentTrustStore


class DeploymentControlFacade:
    def __init__(
        self,
        *,
        repository: DeploymentControlStateRepository | None = None,
        verifier: DeploymentEnvelopeVerifier | None = None,
        runtime_id: str | None = None,
        audience: str | None = None,
    ):
        self.repository = repository or DeploymentControlStateRepository()
        self.runtime_id = runtime_id or source_runtime_id()
        self.audience = audience or f"mindscape-local-core:{self.runtime_id}"
        self.verifier = verifier or DeploymentEnvelopeVerifier(
            DeploymentTrustStore.from_environment()
        )

    def get_state(self) -> DeploymentControlState:
        return self.repository.get_state()

    def replace(
        self,
        command: ReplaceDeploymentControlCommand,
        *,
        actor_user_id: str,
        now: datetime | None = None,
    ) -> DeploymentControlReplaceResult:
        envelope_hash = None
        if command.signed_envelope is not None:
            catalog_hash = self.repository.get_active_catalog_hash()
            envelope_hash = self.verifier.verify(
                command.signed_envelope,
                expected_audience=self.audience,
                expected_source_runtime_id=self.runtime_id,
                expected_catalog_hash=catalog_hash,
                now=now,
            )
        state, replaced = self.repository.replace(
            expected_state_revision=command.expected_state_revision,
            mode=command.mode,
            provider_code=command.provider_code,
            envelope=command.signed_envelope,
            envelope_hash=envelope_hash,
            actor_user_id=actor_user_id,
        )
        return DeploymentControlReplaceResult(
            state=state,
            replaced=replaced,
        )

    def resolve_effective_ceiling(
        self,
        wpcs: WorkspaceCapabilitySetSnapshot,
        *,
        now: datetime | None = None,
    ) -> EffectiveDeploymentCeiling:
        state = self.repository.get_state()
        if state.signed_envelope is not None:
            self.verifier.verify(
                state.signed_envelope,
                expected_audience=self.audience,
                expected_source_runtime_id=self.runtime_id,
                expected_catalog_hash=wpcs.catalog_hash,
                now=now,
            )
        return intersect_effective_ceiling(wpcs, state)
