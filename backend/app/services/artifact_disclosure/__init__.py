"""Artifact-neutral disclosure policy implementation."""

from backend.app.services.artifact_disclosure.composition import (
    build_artifact_disclosure_port,
)

__all__ = ["build_artifact_disclosure_port"]
