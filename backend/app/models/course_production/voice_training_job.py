"""
Voice Training Job Model

Voice training job definition
Stored in external database - job tracking table
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class TrainingJobStatus(str, Enum):
    """Training job status enumeration"""
    QUEUED = "queued"             # Queued for processing
    PREPARING = "preparing"       # Preparing training samples
    TRAINING = "training"         # Currently training
    VALIDATING = "validating"     # Validating training results
    COMPLETED = "completed"       # Training completed successfully
    FAILED = "failed"             # Training failed
    CANCELLED = "cancelled"       # Job was cancelled


class TrainingJobPriority(str, Enum):
    """任務優先級"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class VoiceTrainingJob(BaseModel):
    """
    Voice training job

    Stored in external database, responsible for actual training execution
    """
    id: str = Field(..., description="Training job ID (UUID)")
    voice_profile_id: str = Field(..., description="Associated voice profile ID")
    instructor_id: str = Field(..., description="Instructor ID")

    # Job status
    status: TrainingJobStatus = Field(TrainingJobStatus.QUEUED, description="Current job status")
    priority: TrainingJobPriority = Field(TrainingJobPriority.NORMAL, description="Job priority level")

    # Training configuration
    training_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Training configuration (model type, parameters, etc.)"
    )

    # Sample information
    sample_file_paths: List[str] = Field(default_factory=list, description="Training sample file paths")
    sample_metadata: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Sample metadata (duration, quality, etc.)"
    )

    # Execution information
    started_at: Optional[datetime] = Field(None, description="Job start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Job completion timestamp")
    estimated_duration_seconds: Optional[int] = Field(None, description="Estimated duration in seconds")
    actual_duration_seconds: Optional[int] = Field(None, description="Actual duration in seconds")

    # Results
    result_model_path: Optional[str] = Field(None, description="Generated model file path")
    result_metrics: Optional[Dict[str, Any]] = Field(None, description="Training performance metrics")
    error_message: Optional[str] = Field(None, description="Error message if job failed")
    error_stack: Optional[str] = Field(None, description="Error stack trace")

    # Resource usage
    gpu_used: Optional[str] = Field(None, description="GPU resources used")
    compute_cost: Optional[float] = Field(None, description="Compute cost if trackable")

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # 日誌
    log_path: Optional[str] = Field(None, description="訓練日誌文件路徑")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
