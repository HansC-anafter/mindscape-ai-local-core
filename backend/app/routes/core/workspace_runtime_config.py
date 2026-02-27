"""
Workspace Runtime Config API

GET/PUT workspace-level runtime configuration overrides.
Supports scope: "workspace" (only this workspace) or "global" (all workspaces fallback).

Resolution: workspace override > global override > runtime.extra_metadata
"""

import uuid
import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database.session import get_db_postgres as get_db
from app.models.runtime_config_override import RuntimeConfigOverride
from app.models.runtime_environment import RuntimeEnvironment

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/runtime-config",
    tags=["workspace-runtime-config"],
)


class RuntimeConfigUpdate(BaseModel):
    scope: str = "workspace"  # "workspace" | "global"
    config_overrides: Dict[str, Any] = {}


def resolve_runtime_metadata(
    runtime: RuntimeEnvironment,
    workspace_id: str,
    db: Session,
) -> Dict[str, Any]:
    """
    Merge runtime metadata with workspace/global overrides.
    Priority: workspace override > global override > runtime.extra_metadata
    """
    base = dict(runtime.extra_metadata or {})

    # Global overrides (scope=global, any workspace)
    global_override = (
        db.query(RuntimeConfigOverride)
        .filter(
            RuntimeConfigOverride.runtime_id == runtime.id,
            RuntimeConfigOverride.scope == "global",
        )
        .first()
    )
    if global_override and global_override.config_overrides:
        base.update(global_override.config_overrides)

    # Workspace override (highest priority)
    ws_override = (
        db.query(RuntimeConfigOverride)
        .filter(
            RuntimeConfigOverride.runtime_id == runtime.id,
            RuntimeConfigOverride.workspace_id == workspace_id,
            RuntimeConfigOverride.scope == "workspace",
        )
        .first()
    )
    if ws_override and ws_override.config_overrides:
        base.update(ws_override.config_overrides)

    return base


@router.get("/{runtime_id}")
async def get_workspace_runtime_config(
    workspace_id: str,
    runtime_id: str,
    db: Session = Depends(get_db),
):
    """Get merged runtime config for a workspace (override + global + base)."""
    runtime = (
        db.query(RuntimeEnvironment).filter(RuntimeEnvironment.id == runtime_id).first()
    )
    if not runtime:
        raise HTTPException(status_code=404, detail=f"Runtime not found: {runtime_id}")

    merged = resolve_runtime_metadata(runtime, workspace_id, db)

    # Also return the raw override for editing
    override = (
        db.query(RuntimeConfigOverride)
        .filter(
            RuntimeConfigOverride.workspace_id == workspace_id,
            RuntimeConfigOverride.runtime_id == runtime_id,
        )
        .first()
    )

    return {
        "runtime_id": runtime_id,
        "workspace_id": workspace_id,
        "merged_metadata": merged,
        "override": override.to_dict() if override else None,
        "base_metadata": runtime.extra_metadata or {},
    }


@router.put("/{runtime_id}")
async def put_workspace_runtime_config(
    workspace_id: str,
    runtime_id: str,
    body: RuntimeConfigUpdate,
    db: Session = Depends(get_db),
):
    """Create or update workspace-level runtime config override."""
    runtime = (
        db.query(RuntimeEnvironment).filter(RuntimeEnvironment.id == runtime_id).first()
    )
    if not runtime:
        raise HTTPException(status_code=404, detail=f"Runtime not found: {runtime_id}")

    if body.scope not in ("workspace", "global"):
        raise HTTPException(
            status_code=400, detail="scope must be 'workspace' or 'global'"
        )

    override = (
        db.query(RuntimeConfigOverride)
        .filter(
            RuntimeConfigOverride.workspace_id == workspace_id,
            RuntimeConfigOverride.runtime_id == runtime_id,
        )
        .first()
    )

    if override:
        override.scope = body.scope
        override.config_overrides = body.config_overrides
    else:
        override = RuntimeConfigOverride(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            runtime_id=runtime_id,
            scope=body.scope,
            config_overrides=body.config_overrides,
        )
        db.add(override)

    db.commit()
    db.refresh(override)

    merged = resolve_runtime_metadata(runtime, workspace_id, db)

    return {
        "runtime_id": runtime_id,
        "workspace_id": workspace_id,
        "scope": override.scope,
        "config_overrides": override.config_overrides,
        "merged_metadata": merged,
    }
