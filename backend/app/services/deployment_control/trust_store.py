"""Operator-owned Ed25519 trust roots with bounded rotation overlap."""

from __future__ import annotations

from datetime import datetime
import json
import os

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import DeploymentTrustRootMissing


class DeploymentTrustRoot(BaseModel):
    issuer: str = Field(min_length=2, max_length=128)
    kid: str = Field(min_length=2, max_length=128)
    alg: str = Field(pattern="^EdDSA$")
    public_key: str = Field(min_length=40, max_length=128)
    not_before: datetime | None = None
    not_after: datetime | None = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_window(self):
        for value in (self.not_before, self.not_after):
            if value is not None and value.tzinfo is None:
                raise ValueError("deployment_trust_root_requires_timezone")
        if (
            self.not_before is not None
            and self.not_after is not None
            and self.not_before >= self.not_after
        ):
            raise ValueError("deployment_trust_root_window_invalid")
        return self


class DeploymentTrustStore:
    """Resolve only explicitly configured issuer/kid/algorithm tuples."""

    ENV_NAME = "MINDSCAPE_DEPLOYMENT_CONTROL_TRUST_ROOTS_JSON"

    def __init__(self, roots: list[DeploymentTrustRoot]):
        identities = [(root.issuer, root.kid, root.alg) for root in roots]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate_deployment_trust_root")
        self._roots = {
            (root.issuer, root.kid, root.alg): root for root in roots
        }

    @classmethod
    def from_environment(cls) -> "DeploymentTrustStore":
        raw = os.getenv(cls.ENV_NAME, "[]")
        try:
            payload = json.loads(raw)
            if not isinstance(payload, list):
                raise ValueError("trust root payload must be a list")
            roots = [DeploymentTrustRoot.model_validate(item) for item in payload]
        except (TypeError, ValueError) as exc:
            raise DeploymentTrustRootMissing(
                "deployment_trust_root_configuration_invalid"
            ) from exc
        return cls(roots)

    def resolve(
        self,
        *,
        issuer: str,
        kid: str,
        alg: str,
        now: datetime,
    ) -> DeploymentTrustRoot:
        root = self._roots.get((issuer, kid, alg))
        if root is None:
            raise DeploymentTrustRootMissing("deployment_trust_root_unknown")
        if root.not_before is not None and now < root.not_before:
            raise DeploymentTrustRootMissing(
                "deployment_trust_root_not_yet_valid"
            )
        if root.not_after is not None and now >= root.not_after:
            raise DeploymentTrustRootMissing("deployment_trust_root_expired")
        return root
