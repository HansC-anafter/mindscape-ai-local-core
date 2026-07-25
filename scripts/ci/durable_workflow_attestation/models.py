"""Strict data models and provider constants for CI attestation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONTRACT_ID = "mindscape.durable-product-semantic-workflow.v1"
PROVIDER_ID = "aquasecurity.trivy.fs.v0.72.0"
PROVIDER_IMAGE = (
    "ghcr.io/aquasecurity/trivy@"
    "sha256:cffe3f5161a47a6823fbd23d985795b3ed72a4c806da4c4df16266c02accdd6f"
)
PROVIDER_IMAGE_DIGEST = (
    "sha256:cffe3f5161a47a6823fbd23d985795b3ed72a4c806da4c4df16266c02accdd6f"
)
PROVIDER_SOURCE_COMMIT = "8a32853686209a428179bb3a1688802b25691564"
REPO_IDS = ("mindscape-ai-cloud", "mindscape-ai-local-core")


class AttestationInputError(ValueError):
    """Raised when evidence cannot produce one exact fail-closed draft."""


@dataclass(frozen=True)
class RepositoryInput:
    repo_id: str
    path: Path


@dataclass(frozen=True)
class RepositoryEvidence:
    repo_id: str
    commit_sha: str
    tree_sha: str
    dirty: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "repo_id": self.repo_id,
            "commit_sha": self.commit_sha,
            "tree_sha": self.tree_sha,
            "dirty": self.dirty,
        }
