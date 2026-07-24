"""Legacy artifact-only fallback for rerun input recovery."""

from __future__ import annotations


def infer_ig_target_username(
    workspace_id: str,
    execution_id: str,
) -> str | None:
    try:
        from backend.app.services.stores.postgres.artifacts_store import (
            PostgresArtifactsStore,
        )

        artifacts = PostgresArtifactsStore().list_artifacts_by_workspace(
            workspace_id=workspace_id,
            limit=300,
        )
        for artifact in artifacts:
            if getattr(artifact, "execution_id", None) != execution_id:
                continue
            if getattr(artifact, "playbook_code", None) != "ig_analyze_following":
                continue
            metadata = (
                artifact.metadata
                if isinstance(artifact.metadata, dict)
                else {}
            )
            value = (
                metadata.get("target_username")
                or metadata.get("target_seed")
                or ""
            ).strip()
            if value:
                return value
            content = (
                artifact.content
                if isinstance(artifact.content, dict)
                else {}
            )
            nested = (
                content.get("metadata")
                if isinstance(content.get("metadata"), dict)
                else {}
            )
            nested_value = (
                nested.get("target_username")
                or nested.get("target_seed")
                or ""
            ).strip()
            if nested_value:
                return nested_value
    except Exception:
        return None
    return None

