"""Compatibility shim for the canonical artifact extractor service."""

from backend.app.services.artifact_extractor import ArtifactExtractor, _utc_now

__all__ = ["ArtifactExtractor", "_utc_now"]
