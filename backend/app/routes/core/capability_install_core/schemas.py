from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


@dataclass
class InstallPipelineResult:
    """Aggregated result from ``run_install_pipeline``."""

    success: bool = False
    capability_code: Optional[str] = None
    version: Optional[str] = None
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    restart_required: bool = False
    restart_triggered: bool = False
    restart_decision: Dict[str, Any] = field(default_factory=dict)
    hot_reload_result: Any = None
    webhook_result: Any = None
    pack_metadata: Dict[str, Any] = field(default_factory=dict)
    activation: Optional[Dict[str, Any]] = None
    validation: Optional[Dict[str, Any]] = None
    migration_receipts: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    install_commit_receipt: Dict[str, Any] = field(default_factory=dict)
    activation_candidate: Dict[str, Any] = field(default_factory=dict)
    install_commit_coordinator: Any = field(default=None, repr=False)


@dataclass
class InstallRegistrySyncState:
    contract_lane_changed: bool = False
    object_catalog_changed: bool = False


class PackBackoutRequest(BaseModel):
    """Exact authorization for installing a version below committed truth."""

    backout_from_install_id: str = Field(..., min_length=1)
    artifact_sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    target_version: str = Field(..., min_length=1)
    schema_compatibility_receipt: str = Field(..., min_length=1)
    owner_approval: str = Field(..., min_length=1)


class InstallFromCloudRequest(BaseModel):
    """Request model for installing pack from cloud provider"""

    pack_ref: str = Field(
        ..., description="Pack reference in format 'provider_id:code@version'"
    )
    provider_id: str = Field(..., description="Provider ID to download from")
    verify_checksum: bool = Field(True, description="Whether to verify SHA256 checksum")
    backout_receipt: Optional[PackBackoutRequest] = None
