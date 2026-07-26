"""Production composition root for the single neutral policy implementation."""

from functools import lru_cache

from backend.app.core.ports.artifact_disclosure import ArtifactDisclosurePort
from backend.app.services.artifact_disclosure.policy_profile import (
    load_share_policy_profile,
)
from backend.app.services.artifact_disclosure.service import (
    LocalArtifactDisclosureService,
)


@lru_cache(maxsize=1)
def build_artifact_disclosure_port() -> ArtifactDisclosurePort:
    return LocalArtifactDisclosureService(load_share_policy_profile())


__all__ = ["build_artifact_disclosure_port"]
