"""
Governance settings API endpoints

Handles system-level governance configuration:
- Node governance (whitelist, blacklist, risk labels, throttle)
- Cost governance (quotas, model price overrides)
- Policy service (role policies, data domain policies)
- Preflight settings (validation rules)
- Governance mode (strict mode, warning mode)
"""
from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from .shared import settings_store

router = APIRouter()


class NodeGovernanceSettings(BaseModel):
    """Node governance settings"""
    whitelist: List[str] = Field(default_factory=list, description="Allowed playbook codes")
    blacklist: List[str] = Field(default_factory=list, description="Blocked playbook codes")
    risk_labels: Dict[str, List[str]] = Field(default_factory=dict, description="Playbook risk labels")
    throttle: Dict[str, Any] = Field(
        default_factory=lambda: {
            "write_operation_limit": 10,
            "queue_strategy": "reject"
        },
        description="Throttle configuration"
    )


class CostGovernanceSettings(BaseModel):
    """Cost governance settings"""
    daily_quota: float = Field(default=10.0, description="Daily cost quota")
    single_execution_limit: float = Field(default=5.0, description="Single execution cost limit")
    risk_level_quotas: Dict[str, float] = Field(
        default_factory=lambda: {
            "read": 20.0,
            "write": 10.0,
            "publish": 5.0
        },
        description="Quotas by risk level"
    )
    model_price_overrides: Dict[str, float] = Field(
        default_factory=dict,
        description="Model price overrides (per 1K tokens)"
    )


class PolicyServiceSettings(BaseModel):
    """Policy service settings"""
    role_policies: Dict[str, List[str]] = Field(
        default_factory=lambda: {
            "admin": ["*"],
            "editor": ["read", "write"],
            "viewer": ["read"]
        },
        description="Role-based permissions"
    )
    data_domain_policies: Dict[str, Any] = Field(
        default_factory=lambda: {
            "sensitive_domains": [],
            "pii_handling_enabled": False,
            "forbidden_domains": []
        },
        description="Data domain access policies"
    )


class PreflightSettings(BaseModel):
    """Preflight settings"""
    required_inputs_validation: bool = Field(default=True, description="Validate required inputs")
    credential_validation: bool = Field(default=True, description="Validate credentials")
    environment_validation: bool = Field(default=True, description="Validate environment")


class GovernanceModeSettings(BaseModel):
    """Governance mode settings"""
    strict_mode: bool = Field(default=False, description="Strict mode: block execution on violations")
    warning_mode: bool = Field(default=True, description="Warning mode: show warnings but allow execution")


@router.get("/node", response_model=NodeGovernanceSettings)
async def get_node_governance_settings():
    """Get node governance settings"""
    try:
        settings = settings_store.get_setting("governance.node", default={})
        return NodeGovernanceSettings(**settings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get node governance settings: {str(e)}")


@router.put("/node", response_model=NodeGovernanceSettings)
async def update_node_governance_settings(settings: NodeGovernanceSettings):
    """Update node governance settings"""
    try:
        settings_store.set_setting("governance.node", settings.dict())
        return settings
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update node governance settings: {str(e)}")


@router.get("/cost", response_model=CostGovernanceSettings)
async def get_cost_governance_settings():
    """Get cost governance settings"""
    try:
        settings = settings_store.get_setting("governance.cost", default={})
        return CostGovernanceSettings(**settings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get cost governance settings: {str(e)}")


@router.put("/cost", response_model=CostGovernanceSettings)
async def update_cost_governance_settings(settings: CostGovernanceSettings):
    """Update cost governance settings"""
    try:
        settings_store.set_setting("governance.cost", settings.dict())
        return settings
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update cost governance settings: {str(e)}")


@router.get("/policy", response_model=PolicyServiceSettings)
async def get_policy_service_settings():
    """Get policy service settings"""
    try:
        settings = settings_store.get_setting("governance.policy", default={})
        return PolicyServiceSettings(**settings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get policy service settings: {str(e)}")


@router.put("/policy", response_model=PolicyServiceSettings)
async def update_policy_service_settings(settings: PolicyServiceSettings):
    """Update policy service settings"""
    try:
        settings_store.set_setting("governance.policy", settings.dict())
        return settings
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update policy service settings: {str(e)}")


@router.get("/preflight", response_model=PreflightSettings)
async def get_preflight_settings():
    """Get preflight settings"""
    try:
        settings = settings_store.get_setting("governance.preflight", default={})
        return PreflightSettings(**settings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get preflight settings: {str(e)}")


@router.put("/preflight", response_model=PreflightSettings)
async def update_preflight_settings(settings: PreflightSettings):
    """Update preflight settings"""
    try:
        settings_store.set_setting("governance.preflight", settings.dict())
        return settings
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update preflight settings: {str(e)}")


@router.get("/mode", response_model=GovernanceModeSettings)
async def get_governance_mode():
    """Get governance mode settings"""
    try:
        settings = settings_store.get_setting("governance.mode", default={
            "strict_mode": False,
            "warning_mode": True
        })
        return GovernanceModeSettings(**settings)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get governance mode: {str(e)}")


@router.put("/mode", response_model=GovernanceModeSettings)
async def update_governance_mode(settings: GovernanceModeSettings):
    """Update governance mode settings"""
    try:
        # Ensure strict_mode and warning_mode are mutually exclusive
        if settings.strict_mode and settings.warning_mode:
            settings.warning_mode = False

        settings_store.set_setting("governance.mode", settings.dict())
        return settings
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update governance mode: {str(e)}")

