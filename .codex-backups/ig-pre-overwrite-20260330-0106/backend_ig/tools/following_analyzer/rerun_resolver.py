"""Resolver helpers for ig_analyze_following reruns."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _normalize_username(value: Any) -> Optional[str]:
    if isinstance(value, str):
        normalized = value.strip()
        if normalized:
            return normalized
    return None


def _extract_target_username(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None

    for key in ("target_username", "target_seed", "seed", "handle"):
        normalized = _normalize_username(payload.get(key))
        if normalized:
            return normalized

    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        return _extract_target_username(metadata)

    return None


def _load_target_from_task(execution_id: str) -> Optional[str]:
    try:
        from backend.app.services.stores.tasks_store import TasksStore

        tasks_store = TasksStore()
        task = tasks_store.get_task_by_execution_id(execution_id)
        if not task:
            return None

        for candidate in (
            getattr(task, "execution_context", None),
            getattr(task, "params", None),
        ):
            target = _extract_target_username(candidate)
            if target:
                return target

            if isinstance(candidate, dict):
                nested_inputs = candidate.get("inputs")
                target = _extract_target_username(nested_inputs)
                if target:
                    return target
    except Exception as exc:
        logger.debug("rerun resolver task lookup failed: %s", exc)

    return None


def _load_target_from_artifacts(
    workspace_id: Optional[str], execution_id: str
) -> Optional[str]:
    if not _normalize_username(workspace_id):
        return None

    try:
        from backend.app.services.stores.postgres.artifacts_store import (
            PostgresArtifactsStore,
        )

        artifacts_store = PostgresArtifactsStore()
        arts = artifacts_store.list_artifacts_by_workspace(
            workspace_id=workspace_id, limit=300
        )
        for artifact in arts:
            if getattr(artifact, "execution_id", None) != execution_id:
                continue
            if getattr(artifact, "playbook_code", None) != "ig_analyze_following":
                continue

            for candidate in (
                getattr(artifact, "metadata", None),
                getattr(artifact, "content", None),
            ):
                target = _extract_target_username(candidate)
                if target:
                    return target
    except Exception as exc:
        logger.debug("rerun resolver artifact lookup failed: %s", exc)

    return None


def resolve_following_rerun_inputs(
    workspace_id: Optional[str],
    execution_id: str,
    original_inputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Resolve missing rerun inputs for ig_analyze_following."""
    for candidate in (
        original_inputs,
        _load_target_from_task(execution_id),
        _load_target_from_artifacts(workspace_id, execution_id),
    ):
        if isinstance(candidate, dict):
            target = _extract_target_username(candidate)
        else:
            target = _normalize_username(candidate)
        if target:
            return {"target_username": target}

    logger.warning(
        "resolve_following_rerun_inputs could not resolve target_username "
        "workspace_id=%s execution_id=%s",
        workspace_id,
        execution_id,
    )
    return {}
