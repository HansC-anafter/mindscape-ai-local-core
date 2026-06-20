"""Artifact persistence helpers for ``GovernanceEngine``."""

import logging
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


def register_project_artifact(
    *,
    project_id: str,
    artifact_id: str,
    artifact_path: str,
    artifact_type: str,
    created_by: str,
) -> Any:
    """Register landed artifacts in the project-scoped artifact registry."""
    try:
        from backend.app.services.mindscape_store import MindscapeStore
        from backend.app.services.project.artifact_registry_service import (
            ArtifactRegistryService,
        )

        registry = ArtifactRegistryService(MindscapeStore())
        existing = registry.get_artifact_sync(project_id, artifact_id)
        if existing:
            return existing

        return registry.register_artifact_sync(
            project_id=project_id,
            artifact_id=artifact_id,
            path=artifact_path,
            artifact_type=artifact_type,
            created_by=created_by,
        )
    except Exception as exc:
        logger.warning(
            "GovernanceEngine: artifact registry registration failed (non-fatal): %s",
            exc,
        )
        return None


def update_artifact_metadata(
    *,
    artifact_id: str,
    updater: Callable[[Dict[str, Any]], None],
) -> bool:
    """Load artifact metadata, apply update, and persist it."""
    from backend.app.services.stores.postgres.artifacts_store import (
        PostgresArtifactsStore,
    )

    store = PostgresArtifactsStore()
    artifact = store.get_artifact(artifact_id)
    if not artifact:
        logger.debug(
            "GovernanceEngine: artifact %s not found for metadata update",
            artifact_id,
        )
        return False

    existing_metadata = artifact.metadata if isinstance(artifact.metadata, dict) else {}
    updater(existing_metadata)
    store.update_artifact(artifact_id, metadata=existing_metadata)
    return True


def backfill_provenance(
    engine: Any,
    *,
    artifact_id: str,
    execution_id: str,
    playbook_code: Optional[str],
    parsed_output: Dict[str, Any],
) -> None:
    """Persist provenance sidecar into artifact metadata and handoff registry."""
    try:

        def _merge_provenance(metadata: Dict[str, Any]) -> None:
            provenance = (
                metadata.get("provenance")
                if isinstance(metadata.get("provenance"), dict)
                else {}
            )
            provenance.update(parsed_output)

            try:
                task = engine.tasks_store.get_task_by_execution_id(execution_id)
                if task:
                    ctx = getattr(task, "execution_context", None) or {}
                    msid = getattr(task, "meeting_session_id", None) or ctx.get(
                        "meeting_session_id"
                    )
                    if msid:
                        provenance.setdefault("meeting_session_id", msid)
                    pid = getattr(task, "project_id", None) or (
                        getattr(task, "params", None) or {}
                    ).get("project_id")
                    if pid:
                        provenance.setdefault("project_id", pid)
                    provenance.setdefault("source_task_id", task.id)
            except Exception:
                pass

            metadata["provenance"] = provenance

        updated = engine._update_artifact_metadata(
            artifact_id=artifact_id,
            updater=_merge_provenance,
        )
        if updated:
            logger.info(
                "GovernanceEngine: provenance backfilled artifact=%s hash=%s",
                artifact_id,
                parsed_output.get("output_hash", "")[:12]
                if parsed_output.get("output_hash")
                else "none",
            )
    except Exception as exc:
        logger.warning(
            "GovernanceEngine: artifact provenance backfill failed (non-fatal): %s",
            exc,
        )

    try:
        from backend.app.services.stores.handoff_registry_store import (
            HandoffRegistryStore,
        )

        task_ir_id = None
        try:
            task = engine.tasks_store.get_task_by_execution_id(execution_id)
            if task:
                ctx = getattr(task, "execution_context", None) or {}
                task_ir_id = ctx.get("task_ir_id")
        except Exception:
            pass

        if task_ir_id:
            registry = HandoffRegistryStore()
            registry.mark_completed(
                task_ir_id=task_ir_id,
                execution_id=execution_id,
                artifact_id=artifact_id,
            )
    except Exception as exc:
        logger.warning(
            "GovernanceEngine: handoff registry completion failed (non-fatal): %s",
            exc,
        )
