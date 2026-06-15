"""Projection and filter helpers for Postgres artifact rows."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from app.models.workspace import Artifact, ArtifactType, PrimaryActionType

DeserializeJson = Callable[[Any, Any], Any]


def build_artifact_filters(
    *,
    workspace_id: str,
    playbook_code: Optional[str] = None,
    intent_id: Optional[str] = None,
    platform: Optional[str] = None,
    kind: Optional[str] = None,
    artifact_types: Optional[List[str]] = None,
) -> tuple[str, Dict[str, Any]]:
    """Build reusable SQL WHERE clause and params for artifact listing/count."""
    clauses = ["workspace_id = :workspace_id"]
    params: Dict[str, Any] = {"workspace_id": workspace_id}

    if playbook_code:
        clauses.append("playbook_code = :playbook_code")
        params["playbook_code"] = playbook_code
    if intent_id:
        clauses.append("intent_id = :intent_id")
        params["intent_id"] = intent_id
    if platform:
        escaped_platform = re.escape(platform)
        clauses.append("metadata ~ :platform_regex")
        params["platform_regex"] = f'"platform"\\s*:\\s*"{escaped_platform}"'
    if kind:
        escaped_kind = re.escape(kind)
        clauses.append("metadata ~ :kind_regex")
        params["kind_regex"] = f'"kind"\\s*:\\s*"{escaped_kind}"'
    if artifact_types:
        clauses.append("artifact_type = ANY(:artifact_types)")
        params["artifact_types"] = artifact_types

    return " AND ".join(clauses), params


def normalize_artifact_type(artifact_type: Any) -> Any:
    return artifact_type.value if hasattr(artifact_type, "value") else artifact_type


def row_to_artifact(
    row: Any,
    *,
    deserialize_json: DeserializeJson,
    include_content: bool = True,
) -> Artifact:
    """Convert database row to Artifact model."""
    content = deserialize_json(row.content, {}) if include_content else {}

    return Artifact(
        id=row.id,
        workspace_id=row.workspace_id,
        intent_id=row.intent_id,
        task_id=row.task_id,
        execution_id=row.execution_id,
        thread_id=row.thread_id,
        playbook_code=row.playbook_code,
        artifact_type=ArtifactType(row.artifact_type),
        title=row.title,
        summary=row.summary if row.summary else "",
        content=content,
        storage_ref=row.storage_ref,
        sync_state=row.sync_state,
        primary_action_type=PrimaryActionType(row.primary_action_type),
        metadata=deserialize_json(row.metadata, {}),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
