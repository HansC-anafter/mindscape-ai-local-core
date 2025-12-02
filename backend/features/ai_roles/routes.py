"""
AI Role API Routes
Endpoints for managing AI role configurations
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional, Dict, Any
from datetime import datetime

from backend.app.models.ai_role import (
    AIRoleConfig,
    CreateAIRoleRequest,
    UpdateAIRoleRequest,
)
from backend.app.services.ai_role_store import AIRoleStore

router = APIRouter(tags=["ai-roles"])

# Initialize AI role store
ai_role_store = AIRoleStore()


@router.post("/", response_model=AIRoleConfig)
async def create_or_enable_role(request: CreateAIRoleRequest, profile_id: str = Query(...)):
    """
    Create or enable an AI role

    This endpoint is called when a user enables a built-in role
    or creates a custom role.
    """
    try:
        # Check if role already exists
        existing = ai_role_store.get_role_config(request.role_id, profile_id)

        if existing:
            # Update existing role
            existing.is_enabled = True
            existing.updated_at = datetime.utcnow()
            return ai_role_store.save_role_config(existing)

        # Create new role
        role = AIRoleConfig(
            id=request.role_id,
            profile_id=profile_id,
            name=request.name,
            description=request.description,
            agent_type=request.agent_type,
            icon=request.icon,
            playbooks=request.playbooks,
            suggested_tasks=request.suggested_tasks,
            tools=request.tools,
            mindscape_profile_override=request.mindscape_profile_override,
            is_custom=request.is_custom,
            is_enabled=True,
        )

        return ai_role_store.save_role_config(role)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create role: {str(e)}")


@router.get("/", response_model=List[AIRoleConfig])
async def list_roles(
    profile_id: str = Query(...),
    enabled_only: bool = Query(True, description="Return only enabled roles")
):
    """
    List all AI roles for a profile
    """
    try:
        if enabled_only:
            roles = ai_role_store.get_enabled_roles(profile_id)
        else:
            roles = ai_role_store.get_all_roles(profile_id)

        return roles

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list roles: {str(e)}")


@router.get("/{role_id}", response_model=AIRoleConfig)
async def get_role(role_id: str, profile_id: str = Query(...)):
    """
    Get a specific AI role configuration
    """
    try:
        role = ai_role_store.get_role_config(role_id, profile_id)

        if not role:
            raise HTTPException(status_code=404, detail=f"Role not found: {role_id}")

        return role

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get role: {str(e)}")


@router.patch("/{role_id}", response_model=AIRoleConfig)
async def update_role(
    role_id: str,
    request: UpdateAIRoleRequest,
    profile_id: str = Query(...)
):
    """
    Update an AI role configuration
    """
    try:
        role = ai_role_store.get_role_config(role_id, profile_id)

        if not role:
            raise HTTPException(status_code=404, detail=f"Role not found: {role_id}")

        # Update fields
        if request.name is not None:
            role.name = request.name
        if request.description is not None:
            role.description = request.description
        if request.icon is not None:
            role.icon = request.icon
        if request.playbooks is not None:
            role.playbooks = request.playbooks
        if request.suggested_tasks is not None:
            role.suggested_tasks = request.suggested_tasks
        if request.tools is not None:
            role.tools = request.tools
        if request.mindscape_profile_override is not None:
            role.mindscape_profile_override = request.mindscape_profile_override
        if request.is_enabled is not None:
            role.is_enabled = request.is_enabled

        role.updated_at = datetime.utcnow()

        return ai_role_store.save_role_config(role)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update role: {str(e)}")


@router.delete("/{role_id}")
async def delete_role(role_id: str, profile_id: str = Query(...)):
    """
    Delete an AI role configuration
    """
    try:
        deleted = ai_role_store.delete_role_config(role_id, profile_id)

        if not deleted:
            raise HTTPException(status_code=404, detail=f"Role not found: {role_id}")

        return {"success": True, "message": f"Role {role_id} deleted"}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete role: {str(e)}")


@router.post("/{role_id}/record-usage")
async def record_role_usage(
    role_id: str,
    profile_id: str = Query(...),
    execution_id: str = Query(...),
    task: str = Query(...),
):
    """
    Record that a role was used

    This should be called after each agent execution.
    """
    try:
        ai_role_store.record_role_usage(role_id, profile_id, execution_id, task)
        return {"success": True}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to record usage: {str(e)}")


@router.get("/{role_id}/statistics")
async def get_role_statistics(role_id: str, profile_id: str = Query(...)):
    """
    Get usage statistics for a role
    """
    try:
        role = ai_role_store.get_role_config(role_id, profile_id)

        if not role:
            raise HTTPException(status_code=404, detail=f"Role not found: {role_id}")

        return {
            "role_id": role.id,
            "role_name": role.name,
            "usage_count": role.usage_count,
            "last_used_at": role.last_used_at.isoformat() if role.last_used_at else None,
            "is_enabled": role.is_enabled,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get statistics: {str(e)}")


@router.get("/{role_id}/capabilities", response_model=List[Dict[str, Any]])
async def get_role_capabilities(role_id: str, profile_id: str = Query(...)):
    """Get all capabilities mapped to a specific role"""
    try:
        from backend.app.services.role_capability_mapper import get_role_capabilities as get_role_caps

        capabilities = get_role_caps(role_id, profile_id)
        return capabilities
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get role capabilities: {str(e)}")
