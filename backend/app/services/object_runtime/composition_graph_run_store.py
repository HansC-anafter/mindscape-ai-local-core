"""Artifact-backed storage for executable composition graph runs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi.encoders import jsonable_encoder

from backend.app.models.object_runtime import CompositionGraphRun
from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType

COMPOSITION_GRAPH_RUN_KIND = "composition_graph_run"
COMPOSITION_GRAPH_RUN_SCHEMA_VERSION = "composition_graph_run.v1"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CompositionGraphRunStore:
    """Persist graph runs in the existing artifacts store."""

    def __init__(self, artifacts_store: Any) -> None:
        self.artifacts_store = artifacts_store

    def create_run(self, run: CompositionGraphRun) -> CompositionGraphRun:
        artifact = Artifact(
            id=run.id,
            workspace_id=run.workspace_id,
            intent_id=None,
            task_id=None,
            execution_id=run.id,
            thread_id=run.thread_id,
            playbook_code="core.composition_graph",
            artifact_type=ArtifactType.DATA,
            title=f"Composition graph run {run.id}",
            summary=f"Composition graph run status: {run.status}",
            content=self._run_content(run),
            storage_ref=None,
            sync_state=None,
            primary_action_type=PrimaryActionType.PREVIEW,
            metadata=self._run_metadata(run),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.artifacts_store.create_artifact(artifact)
        return run

    def get_run(self, workspace_id: str, graph_run_id: str) -> Optional[CompositionGraphRun]:
        artifact = self.artifacts_store.get_artifact(graph_run_id)
        if artifact is None or getattr(artifact, "workspace_id", None) != workspace_id:
            return None
        metadata = dict(getattr(artifact, "metadata", {}) or {})
        if metadata.get("kind") != COMPOSITION_GRAPH_RUN_KIND:
            return None
        content = dict(getattr(artifact, "content", {}) or {})
        payload = {
            **content,
            "id": getattr(artifact, "id"),
            "workspace_id": workspace_id,
            "graph_id": metadata.get("graph_id") or content.get("graph_id"),
            "draft_id": metadata.get("draft_id") or content.get("draft_id"),
            "meeting_id": metadata.get("meeting_id") or content.get("meeting_id"),
            "thread_id": metadata.get("thread_id") or getattr(artifact, "thread_id", None),
            "status": metadata.get("status") or content.get("status"),
            "schema_version": metadata.get("schema_version")
            or content.get("schema_version")
            or COMPOSITION_GRAPH_RUN_SCHEMA_VERSION,
        }
        return CompositionGraphRun.model_validate(payload)

    def update_run(self, run: CompositionGraphRun) -> CompositionGraphRun:
        updated = run.model_copy(update={"updated_at": utc_iso()})
        self.artifacts_store.update_artifact(
            updated.id,
            thread_id=updated.thread_id,
            title=f"Composition graph run {updated.id}",
            summary=f"Composition graph run status: {updated.status}",
            content=self._run_content(updated),
            metadata=self._run_metadata(updated),
        )
        return updated

    def _run_content(self, run: CompositionGraphRun) -> dict[str, Any]:
        payload = run.model_dump(mode="json")
        return jsonable_encoder(payload)

    def _run_metadata(self, run: CompositionGraphRun) -> dict[str, Any]:
        return {
            "kind": COMPOSITION_GRAPH_RUN_KIND,
            "schema_version": run.schema_version,
            "workspace_id": run.workspace_id,
            "graph_id": run.graph_id,
            "draft_id": run.draft_id,
            "meeting_id": run.meeting_id,
            "thread_id": run.thread_id,
            "status": run.status,
        }
