"""Draft artifact storage helpers for composition graph service."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi.encoders import jsonable_encoder

from backend.app.models.object_runtime import (
    CompositionGraphDraft,
    CompositionGraphEdge,
    CompositionGraphImportExportPayload,
    CompositionGraphNode,
    CompositionGraphViewport,
)
from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType
from backend.app.services.object_runtime.composition_graph_io import (
    sanitize_composition_graph_export_payload,
)
from backend.app.services.object_runtime.composition_graph_migrations import (
    upgrade_composition_graph_content,
)
from backend.app.services.object_runtime.composition_graph_service_core.constants import (
    COMPOSITION_GRAPH_DRAFT_KIND,
    COMPOSITION_GRAPH_SCHEMA_VERSION,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def create_artifact_for_draft(artifacts_store: Any, draft: CompositionGraphDraft) -> None:
    content, metadata = draft_storage_payload(draft)
    artifact = Artifact(
        id=draft.id,
        workspace_id=draft.workspace_id,
        intent_id=None,
        task_id=None,
        execution_id=None,
        thread_id=draft.thread_id,
        playbook_code="core.composition_graph",
        artifact_type=ArtifactType.DATA,
        title=draft.title,
        summary=f"Composition graph draft for {draft.title}",
        content=content,
        storage_ref=None,
        sync_state=None,
        primary_action_type=PrimaryActionType.EDIT,
        metadata=metadata,
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    artifacts_store.create_artifact(artifact)


def draft_storage_payload(
    draft: CompositionGraphDraft,
) -> tuple[Dict[str, Any], Dict[str, Any]]:
    content = {
        "schema_version": draft.schema_version,
        "nodes": [node.model_dump(mode="json") for node in draft.nodes],
        "edges": [edge.model_dump(mode="json") for edge in draft.edges],
        "viewport": draft.viewport.model_dump(mode="json"),
        "selected_primary_pack": draft.selected_primary_pack,
        "history": [entry.model_dump(mode="json") for entry in draft.history],
        "migrations": [entry.model_dump(mode="json") for entry in draft.migrations],
        "node_diagnostics": jsonable_encoder(draft.node_diagnostics),
        "edge_diagnostics": jsonable_encoder(draft.edge_diagnostics),
        "metadata": draft.metadata,
    }
    metadata = {
        "kind": COMPOSITION_GRAPH_DRAFT_KIND,
        "schema_version": draft.schema_version,
        "workspace_id": draft.workspace_id,
        "meeting_id": draft.meeting_id,
        "thread_id": draft.thread_id,
        "graph_id": draft.graph_id,
        "title": draft.title,
    }
    return content, metadata


def artifact_to_draft(artifact: Any) -> Optional[CompositionGraphDraft]:
    if artifact is None:
        return None
    metadata = dict(getattr(artifact, "metadata", {}) or {})
    if metadata.get("kind") != COMPOSITION_GRAPH_DRAFT_KIND:
        return None
    content = upgrade_composition_graph_content(dict(getattr(artifact, "content", {}) or {}))
    return CompositionGraphDraft(
        id=getattr(artifact, "id"),
        graph_id=str(metadata.get("graph_id") or getattr(artifact, "id")),
        workspace_id=str(metadata.get("workspace_id") or getattr(artifact, "workspace_id")),
        title=str(metadata.get("title") or getattr(artifact, "title", "Composition Graph")),
        schema_version=str(
            content.get("schema_version")
            or metadata.get("schema_version")
            or COMPOSITION_GRAPH_SCHEMA_VERSION
        ),
        meeting_id=metadata.get("meeting_id"),
        thread_id=metadata.get("thread_id") or getattr(artifact, "thread_id", None),
        selected_primary_pack=content.get("selected_primary_pack"),
        nodes=[
            CompositionGraphNode.model_validate(item)
            for item in list(content.get("nodes") or [])
        ],
        edges=[
            CompositionGraphEdge.model_validate(item)
            for item in list(content.get("edges") or [])
        ],
        viewport=CompositionGraphViewport.model_validate(content.get("viewport") or {}),
        history=list(content.get("history") or []),
        migrations=list(content.get("migrations") or []),
        node_diagnostics=dict(content.get("node_diagnostics") or {}),
        edge_diagnostics=dict(content.get("edge_diagnostics") or {}),
        metadata=dict(content.get("metadata") or {}),
    )


def draft_to_export_payload(
    draft: CompositionGraphDraft,
) -> CompositionGraphImportExportPayload:
    return sanitize_composition_graph_export_payload(
        CompositionGraphImportExportPayload(
            schema_version=draft.schema_version,
            graph_id=draft.graph_id,
            title=draft.title,
            selected_primary_pack=draft.selected_primary_pack,
            nodes=draft.nodes,
            edges=draft.edges,
            viewport=draft.viewport,
            metadata=dict(draft.metadata),
        )
    )


def checksum(payload: Dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
