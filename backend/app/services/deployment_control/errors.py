"""Deployment-control failures with stable API codes."""


class DeploymentControlError(RuntimeError):
    code = "deployment_control_invalid"


class DeploymentControlStateRevisionConflict(DeploymentControlError):
    code = "deployment_control_state_revision_conflict"

    def __init__(self, expected_revision: int, actual_revision: int):
        super().__init__(self.code)
        self.expected_revision = expected_revision
        self.actual_revision = actual_revision


class DeploymentEnvelopeRevisionConflict(DeploymentControlError):
    code = "deployment_envelope_revision_conflict"

    def __init__(self, current_revision: int, requested_revision: int):
        super().__init__(self.code)
        self.current_revision = current_revision
        self.requested_revision = requested_revision


class DeploymentEnvelopeInvalid(DeploymentControlError):
    code = "deployment_envelope_invalid"


class DeploymentEnvelopeExpired(DeploymentControlError):
    code = "deployment_envelope_expired"


class DeploymentEnvelopeNotYetValid(DeploymentControlError):
    code = "deployment_envelope_not_yet_valid"


class DeploymentTrustRootMissing(DeploymentControlError):
    code = "deployment_trust_root_missing"


class DeploymentCatalogConflict(DeploymentControlError):
    code = "deployment_catalog_conflict"

    def __init__(self, expected_catalog_hash: str, current_catalog_hash: str):
        super().__init__(self.code)
        self.expected_catalog_hash = expected_catalog_hash
        self.current_catalog_hash = current_catalog_hash


class DeploymentManagedEnvelopeMissing(DeploymentControlError):
    code = "deployment_managed_envelope_missing"
