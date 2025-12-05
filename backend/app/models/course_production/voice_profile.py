"""
Voice Profile Model

Voice model metadata definition
Stored in external database - metadata table
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field

from ..workspace import Workspace  # 參考現有模型結構


class VoiceProfileStatus(str, Enum):
    """Voice model status enumeration"""
    PENDING = "pending"           # Waiting for training
    TRAINING = "training"         # Currently training
    READY = "ready"               # Available for use
    DEPRECATED = "deprecated"      # Deprecated and no longer used
    FAILED = "failed"             # Training failed


class VoiceProfile(BaseModel):
    """
    Voice model metadata

    Stored in external database, actual model files stored in storage service
    """
    id: str = Field(..., description="Voice profile ID (UUID)")
    instructor_id: str = Field(..., description="Instructor ID")

    # Version management
    version: int = Field(1, description="Model version number")
    profile_name: str = Field(..., description="Profile name (e.g., 'My AI Voice v1')")

    # Status
    status: VoiceProfileStatus = Field(VoiceProfileStatus.PENDING, description="Current model status")

    # Training configuration
    sample_duration_seconds: Optional[float] = Field(None, description="Total sample duration in seconds")
    sample_count: int = Field(0, description="Number of training samples")
    sample_paths: List[str] = Field(default_factory=list, description="List of sample file paths")

    # Model storage
    model_storage_path: Optional[str] = Field(None, description="Model file storage path")
    model_storage_service: Optional[str] = Field(None, description="Storage service identifier")

    # Training job association
    training_job_id: Optional[str] = Field(None, description="Associated training job ID")

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    ready_at: Optional[datetime] = Field(None, description="Model ready timestamp")

    # Quality metrics (populated after training completion)
    quality_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Overall quality score")
    similarity_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Voice similarity score")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class CreateVoiceProfileRequest(BaseModel):
    """創建聲紋模型請求"""
    instructor_id: str = Field(..., description="講師 ID")
    profile_name: str = Field(..., description="模型名稱")
    version: Optional[int] = Field(1, description="版本號（默認 1）")


class UpdateVoiceProfileRequest(BaseModel):
    """更新聲紋模型請求"""
    profile_name: Optional[str] = Field(None, description="模型名稱")
    status: Optional[VoiceProfileStatus] = Field(None, description="狀態")
    quality_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="品質分數")
    similarity_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="相似度分數")


class StartTrainingRequest(BaseModel):
    """啟動訓練請求"""
    training_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="訓練配置（模型類型、參數等）"
    )
    priority: Optional[str] = Field("normal", description="優先級：low/normal/high")
